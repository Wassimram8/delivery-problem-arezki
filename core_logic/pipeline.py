from . import graph_operations, routing_algorithms, visualization, utils # Assurez-vous que utils est importé
import os
import random
import networkx as nx
import osmnx as ox

@utils.timing_decorator # Le décorateur est appliqué à cette fonction aussi
def execute_main_pipeline(city_name: str, network_type: str, output_folder: str,
                          num_delivery_points_config: str,
                          packages_per_point_config: str,
                          truck_capacity: int,
                          cluster_range_input: list = None,
                          animation_interval: int = 500) -> dict:
    os.makedirs(output_folder, exist_ok=True)
    if cluster_range_input is None: cluster_range_input = [2, 3, 4]

    # 1. Charger le graphe
    G_initial = graph_operations.load_or_download_graph_timed(city_name, network_type, output_folder)
    if not G_initial:
        return {"error": f"Impossible de charger le graphe pour {city_name}.", "mp4_path": None, "graph_path": None, "stats": {}, "profiling_data": utils.PROF_DATA.copy()}

    # 2. Preparer les données de livraison (modifie G_initial ou une copie, et retourne la référence)
    G_prepared, delivery_nodes_ids = graph_operations.prepare_graph_data_timed(
        G_initial,
        num_delivery_points_config=num_delivery_points_config,
        packages_per_point_config=packages_per_point_config,
        truck_capacity=truck_capacity
    )
    if not delivery_nodes_ids:
        return {"error": "Aucun point de livraison sélectionné/configuré.", "mp4_path": None, "graph_path": None, "stats": {}, "profiling_data": utils.PROF_DATA.copy()}

    # 3. Clustering
    X_coords, delivery_node_ids_for_clustering = graph_operations.extract_delivery_node_coords(G_prepared)
    if X_coords.shape[0] == 0:
        return {"error": "Les points de livraison n'ont pas de coordonnées pour le clustering.", "mp4_path": None, "graph_path": None, "stats": {}, "profiling_data": utils.PROF_DATA.copy()}

    valid_cr = [n for n in cluster_range_input if 1 < n < X_coords.shape[0]]
    best_n_clusters = routing_algorithms.perform_silhouette_analysis_timed(X_coords, valid_cr) if valid_cr else (2 if X_coords.shape[0]>=2 else 1)

    G_clustered, cluster_centers_xy, warehouse_node_ids = routing_algorithms.cluster_deliveries_and_assign_warehouses_timed(
        G_prepared, best_n_clusters, delivery_node_ids_for_clustering, X_coords
    )

    # 4. Definir le nœud de départ
    start_node_osmid = None
    if not warehouse_node_ids and delivery_nodes_ids:
        start_node_osmid = random.choice(delivery_nodes_ids)
        if start_node_osmid not in G_clustered.nodes:
            G_clustered.add_node(start_node_osmid) # Minimal add, copy attributes if needed from G_initial
            if G_initial.has_node(start_node_osmid): # Copy attributes if source node exists in G_initial
                for k, v in G_initial.nodes[start_node_osmid].items():
                    G_clustered.nodes[start_node_osmid][k] = v
        G_clustered.nodes[start_node_osmid].update({'delivery_type':'warehouse', 'cluster_id':0, 'status':'warehouse_active'})
        warehouse_node_ids = [start_node_osmid]
    elif not warehouse_node_ids:
        return {"error": "Aucun entrepôt ou point de livraison pour démarrer la route.", "mp4_path": None, "graph_path": None, "stats": {}, "profiling_data": utils.PROF_DATA.copy()}
    else:
        start_node_osmid = random.choice(warehouse_node_ids)

    for dn_id in delivery_nodes_ids:
        if dn_id in G_clustered.nodes and G_clustered.nodes[dn_id].get('delivery_type') == 'delivery':
            G_clustered.nodes[dn_id]['status'] = 'pending'

    # 5. Calcul de la route
    route_nodes, total_distance_m = routing_algorithms.compute_zone_based_route_timed(
        G_clustered, warehouse_node_ids, delivery_nodes_ids, truck_capacity
    )
    if not route_nodes:
        return {"error": "Le calcul de la route a échoué.", "mp4_path": None, "graph_path": None, "stats": {}, "profiling_data": utils.PROF_DATA.copy()}

    G_final_state = G_clustered

    # 6. Visualisation
    map_file_basename = os.path.join(output_folder, f"{utils.normalize_city_name(city_name)}_{network_type}")
    mp4_filepath = visualization.visualize_route_matplotlib_timed(
        G_final_state, route_nodes, start_node_osmid,
        map_filename_base=map_file_basename,
        animation_interval=animation_interval
    )

    # 7. Sauvegarde du graphe final
    graphml_filename = f"{utils.normalize_city_name(city_name)}_{network_type}_final_data.graphml"
    graphml_filepath = os.path.join(output_folder, graphml_filename)

    G_to_save = G_final_state.copy()
    for key, value in list(G_to_save.graph.items()):
        if key == 'crs' and not isinstance(value, str):
            try: G_to_save.graph[key] = str(value)
            except: del G_to_save.graph[key]
        elif not isinstance(value, (int, float, str, bool, type(None))):
            try: G_to_save.graph[key] = str(value)
            except: del G_to_save.graph[key]
    for _, data_node in G_to_save.nodes(data=True):
        for key, value in list(data_node.items()):
            if isinstance(value, (list, set, dict)):
                try: data_node[key] = str(value)
                except: del data_node[key]
            elif not isinstance(value, (int, float, str, bool, type(None))):
                try: data_node[key] = str(value)
                except: del data_node[key]
    for u, v, key_edge, data_edge in G_to_save.edges(data=True, keys=True):
        for key_attr, value in list(data_edge.items()):
            if isinstance(value, (list, set, dict)):
                try: data_edge[key_attr] = str(value)
                except: del data_edge[key_attr]
            elif not isinstance(value, (int, float, str, bool, type(None))):
                try: data_edge[key_attr] = str(value)
                except: del data_edge[key_attr]

    saved_graph_path = None
    try:
        ox.save_graphml(G_to_save, filepath=graphml_filepath)
        saved_graph_path = graphml_filepath
    except Exception:
        try:
            nx.write_graphml(G_to_save, graphml_filepath)
            saved_graph_path = graphml_filepath
        except Exception:
            print(f"Échec de la sauvegarde du graphe: {graphml_filepath}")


    results = {
        "message": "Pipeline exécuté." if saved_graph_path else "Pipeline exécuté, mais sauvegarde du graphe échouée.",
        "mp4_path": mp4_filepath,
        "graph_path": saved_graph_path,
        "stats": {
            "city": city_name,
            "num_deliveries_requested_config": str(num_delivery_points_config),
            "num_deliveries_actual": len(delivery_nodes_ids),
            "packages_per_point_config": str(packages_per_point_config),
            "num_clusters": best_n_clusters,
            "route_steps": len(route_nodes),
            "total_distance_km": round(total_distance_m / 1000, 2),
            "truck_capacity": truck_capacity
        },
        "profiling_data": utils.PROF_DATA.copy() # Copier les données de profiling actuelles
    }
    # Ne PAS effacer utils.PROF_DATA ici. Ce sera fait par l'appelant (Flask app).
    return results