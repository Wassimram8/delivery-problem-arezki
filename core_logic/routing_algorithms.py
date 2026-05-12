import time
import random # Pour compute_zone_based_route_timed
import numpy as np
import networkx as nx
import osmnx as ox # Pour ox.distance.nearest_nodes dans cluster_deliveries...

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score # Pour perform_silhouette_analysis_timed

# Importer depuis le module utils dans le même package core_logic
from . import utils # On importe le module utils entier pour accéder à utils.timing_decorator

@utils.timing_decorator
def perform_silhouette_analysis_timed(X: np.ndarray, range_n_clusters: list) -> int:
    """
    Effectue une analyse de silhouette pour déterminer le meilleur nombre de clusters.
    Retourne le meilleur nombre de clusters (int).
    """
    if X.shape[0] < 2:
        # print(f"Not enough samples ({X.shape[0]}) for silhouette. Min 2. Defaulting to 1 cluster.")
        return 1

    # S'assurer que n_clusters est valable (entre 2 et n_samples - 1)
    valid_range_n_clusters = [n for n in range_n_clusters if 1 < n < X.shape[0]]

    if not valid_range_n_clusters:
        if X.shape[0] >= 2 : # Si on a au moins 2 points, on peut toujours essayer 2 clusters
            # print(f"Cluster range {range_n_clusters} invalid for {X.shape[0]} samples. Trying 2 clusters.")
            best_n_clusters_candidate = 2
            if 1 < best_n_clusters_candidate < X.shape[0]:
                valid_range_n_clusters = [best_n_clusters_candidate]
            else: # Ne devrait pas arriver si X.shape[0] >=2
                # print("Cannot even form 2 clusters. Defaulting to 1 cluster.")
                return 1
        else: # Moins de 2 points
            # print(f"Not enough samples ({X.shape[0]}) for any valid cluster range. Defaulting to 1 cluster.")
            return 1

    if not valid_range_n_clusters: # Au cas où, après la tentative de fallback
        return 1


    best_n_clusters = valid_range_n_clusters[0] # Initialiser avec le premier valide
    best_score = -1 # Le score de silhouette va de -1 à 1

    for n_clusters in valid_range_n_clusters:
        clusterer = KMeans(n_clusters=n_clusters, random_state=10, n_init='auto')
        try:
            cluster_labels = clusterer.fit_predict(X)
        except ValueError as e:
            # print(f"Error fitting KMeans for {n_clusters} clusters: {e}. Skipping.")
            continue # Passer au n_clusters suivant

        # Le score de silhouette ne peut être calculé que s'il y a plus d'1 label unique
        if len(set(cluster_labels)) > 1:
            silhouette_avg = silhouette_score(X, cluster_labels)
            # print(f"For n_clusters = {n_clusters}, avg silhouette_score: {silhouette_avg:.4f}")
            if silhouette_avg > best_score:
                best_score = silhouette_avg
                best_n_clusters = n_clusters
        # else:
        # print(f"For n_clusters = {n_clusters}, only one cluster found. Silhouette not applicable.")

    if best_score == -1 and X.shape[0] > 0: # Aucun score valide trouvé
        # print(f"No valid silhouette scores. Defaulting to 1 cluster (or min valid if available).")
        return min(valid_range_n_clusters) if valid_range_n_clusters else 1
    # elif best_score != -1:
    # print(f"✅ Best n_clusters (silhouette): {best_n_clusters} (score: {best_score:.4f})")
    # else: # X.shape[0] == 0, déjà géré ou best_score est resté -1
    # print("✅ No clusters determined (insufficient data or scores). Defaulting to 1.")

    return best_n_clusters if best_score != -1 else (min(valid_range_n_clusters) if valid_range_n_clusters else 1)


@utils.timing_decorator
def cluster_deliveries_and_assign_warehouses_timed(G: nx.MultiDiGraph, best_n_clusters: int,
                                                   delivery_node_ids_original: list, X_coords: np.ndarray) -> tuple[nx.MultiDiGraph, list, list]:
    """
    Clusterise les points de livraison et assigne des entrepôts.
    Retourne le Graphe modifié, les coordonnées des centres de cluster, et les IDs des nœuds d'entrepôt.
    """
    if X_coords.shape[0] == 0 or best_n_clusters == 0:
        # print("No delivery coordinates or zero clusters, skipping clustering.")
        return G, [], [] # G non modifié, listes vides

    # Ajuster best_n_clusters si plus grand que le nombre de points
    if X_coords.shape[0] < best_n_clusters:
        # print(f"Warning: Samples ({X_coords.shape[0]}) < n_clusters ({best_n_clusters}). Adjusting.")
        best_n_clusters = X_coords.shape[0] if X_coords.shape[0] > 0 else 1 # Assurer au moins 1 si points existent
        if best_n_clusters == 0: # Si X_coords.shape[0] était 0
            return G, [], []

    clusterer = KMeans(n_clusters=best_n_clusters, random_state=10, n_init='auto').fit(X_coords)
    cluster_centers_coords_xy = clusterer.cluster_centers_ # Coordonnées X,Y des centres géométriques

    warehouse_node_ids = []
    for i, (x_center, y_center) in enumerate(cluster_centers_coords_xy):
        # Trouver le nœud du graphe le plus proche du centre géométrique du cluster
        # G doit être projeté pour que ox.distance.nearest_nodes fonctionne avec x,y
        nearest_node_id = ox.distance.nearest_nodes(G, X=x_center, Y=y_center)
        G.nodes[nearest_node_id]['delivery_type'] = "warehouse"
        G.nodes[nearest_node_id]['cluster_id'] = i # ID du cluster/zone
        G.nodes[nearest_node_id]['delivery_info'] = {'capacity': 1000} # Capacité d'exemple
        G.nodes[nearest_node_id]['status'] = 'warehouse_active' # Statut spécifique
        warehouse_node_ids.append(nearest_node_id)

    # Assigner chaque point de livraison au cluster (et donc à l'entrepôt) correspondant
    cluster_labels = clusterer.labels_ # Pour chaque point dans X_coords, le label du cluster auquel il appartient
    for original_node_idx, delivery_node_id in enumerate(delivery_node_ids_original):
        if delivery_node_id in G.nodes: # S'assurer que le nœud existe toujours
            assigned_cluster_label = cluster_labels[original_node_idx]
            G.nodes[delivery_node_id]['assigned_warehouse'] = warehouse_node_ids[assigned_cluster_label]
            G.nodes[delivery_node_id]['cluster_id'] = assigned_cluster_label
        # else:
        # print(f"Warning: Node ID {delivery_node_id} from clustering input not found in G during assignment.")

    # print(f"Assigned {len(delivery_node_ids_original)} deliveries to {best_n_clusters} warehouses.")
    return G, cluster_centers_coords_xy, warehouse_node_ids


@utils.timing_decorator
def compute_zone_based_route_timed(G: nx.MultiDiGraph, cluster_center_nodes: list, # Devrait être warehouse_node_ids
                                   delivery_nodes_all: list, package_capacity: int) -> tuple[list, float, dict]:
    """
    Calcule une route optimisée basée sur les zones (clusters) et la capacité du camion.
    Retourne la liste des nœuds de la route, la distance totale, et les données de profiling local.
    """
    # La logique de cette fonction est assez complexe et a été testée.
    # Les changements principaux ici sont les imports et l'utilisation de utils.timing_decorator.
    # Je vais recopier la version compactée de la logique que vous aviez fournie précédemment pour la garder cohérente.

    local_prof_data = { "find_nearest_in_zone": 0, "calc_sp_to_delivery": 0, "find_nearest_warehouse": 0, "calc_sp_to_warehouse": 0, "calc_sp_return_to_warehouse": 0 }
    total_distance_meters = 0.0

    # Initialisation start_node
    start_node = None

    if not cluster_center_nodes: # Si pas d'entrepôts définis via clustering
        if delivery_nodes_all:
            # print("No warehouses defined. Using first delivery as pseudo-warehouse.")
            start_node = delivery_nodes_all[0]
            G.nodes[start_node]['delivery_type'] = 'warehouse'; G.nodes[start_node]['cluster_id'] = 0
            G.nodes[start_node]['status'] = 'warehouse_active'
            cluster_center_nodes_map = {0: start_node} # Créer une map avec ce pseudo-entrepôt
            # S'assurer que tous les delivery_nodes_all sont dans ce pseudo-cluster 0 s'ils n'ont pas de cluster_id
            for dn_id in delivery_nodes_all:
                if 'cluster_id' not in G.nodes[dn_id]:
                    G.nodes[dn_id]['cluster_id'] = 0
        else:
            return [], 0.0, {"__local_prof__": local_prof_data} # Pas de livraisons, pas de route
    else: # Des entrepôts existent
        cluster_center_nodes_map = {}
        for wh_node_id in cluster_center_nodes:
            if wh_node_id in G.nodes and 'cluster_id' in G.nodes[wh_node_id]:
                cluster_center_nodes_map[G.nodes[wh_node_id]['cluster_id']] = wh_node_id
            # else:
            # print(f"Warning: Warehouse {wh_node_id} missing or no cluster_id. Ignored.")

    if not cluster_center_nodes_map: # Si toujours vide après la tentative ci-dessus
        # print("Critical: No valid warehouse map. Attempting fallback with first delivery point.")
        if delivery_nodes_all:
            start_node = delivery_nodes_all[0] # Fallback
            G.nodes[start_node]['delivery_type'] = 'warehouse'; G.nodes[start_node]['cluster_id'] = 0
            G.nodes[start_node]['status'] = 'warehouse_active'
            cluster_center_nodes_map = {0: start_node}
            for dn_id in delivery_nodes_all:
                if 'cluster_id' not in G.nodes[dn_id]: G.nodes[dn_id]['cluster_id'] = 0
        else:
            return [], 0.0, {"__local_prof__": local_prof_data}

    deliveries_by_zone = {}
    for node_id in delivery_nodes_all:
        data = G.nodes[node_id]
        if data.get("delivery_type") == "delivery" and data.get("status") == "pending" and 'cluster_id' in data:
            deliveries_by_zone.setdefault(data["cluster_id"], []).append(node_id)

    if not deliveries_by_zone:
        # print("No pending deliveries to process.")
        if cluster_center_nodes_map: # Retourner à un entrepôt si aucun delivery
            first_wh_zone = list(cluster_center_nodes_map.keys())[0]
            return [cluster_center_nodes_map[first_wh_zone]], 0.0, {"__local_prof__": local_prof_data}
        return [], 0.0, {"__local_prof__": local_prof_data}

    # Déterminer le point de départ (un entrepôt dans une zone avec des livraisons)
    start_zone_candidates = [zid for zid in cluster_center_nodes_map if zid in deliveries_by_zone and deliveries_by_zone[zid]]
    if not start_zone_candidates: # Si aucun entrepôt n'est dans une zone avec des livraisons en attente
        # print("Warning: No WH in zones with pending deliveries. Fallback to first WH in map.")
        if not cluster_center_nodes_map: # S'il n'y a vraiment aucun entrepôt
            return [], 0.0, {"__local_prof__": local_prof_data}
        current_zone = list(cluster_center_nodes_map.keys())[0]
        start_node = cluster_center_nodes_map[current_zone]
    else:
        current_zone = random.choice(start_zone_candidates)
        start_node = cluster_center_nodes_map[current_zone]

    # --- Début de la logique de routage principale ---
    current_warehouse_node = start_node
    current_node = start_node
    route = [current_node]
    remaining_capacity = package_capacity
    active_deliveries_by_zone = {zone: list(nodes) for zone, nodes in deliveries_by_zone.items()}
    zones_to_visit_with_deliveries = {zone for zone, nodes in active_deliveries_by_zone.items() if nodes}

    while zones_to_visit_with_deliveries:
        # Si la zone actuelle est vide ou n'existe plus
        if current_zone not in active_deliveries_by_zone or not active_deliveries_by_zone.get(current_zone):
            zones_to_visit_with_deliveries.discard(current_zone)
            if not zones_to_visit_with_deliveries: break # Plus de zones avec livraisons

            # Choisir la prochaine zone (entrepôt le plus proche dans une zone avec livraisons)
            t_s = time.perf_counter()
            try:
                valid_target_zones = [z_id for z_id in zones_to_visit_with_deliveries if z_id in cluster_center_nodes_map]
                if not valid_target_zones: break # Plus de zones valides avec entrepôts

                # Filtrer les zones dont l'entrepôt est accessible depuis current_node
                reachable_target_zones = []
                for z_id in valid_target_zones:
                    target_wh_for_zone = cluster_center_nodes_map[z_id]
                    if nx.has_path(G, source=current_node, target=target_wh_for_zone):
                        reachable_target_zones.append(z_id)

                if not reachable_target_zones: break # Aucun entrepôt de zone atteignable

                next_best_zone = min(
                    reachable_target_zones,
                    key=lambda z_id: nx.shortest_path_length(G, source=current_node, target=cluster_center_nodes_map[z_id], weight="length")
                )
            except (nx.NetworkXNoPath, ValueError): break # Erreur de chemin ou min sur séquence vide
            local_prof_data["find_nearest_warehouse"] += (time.perf_counter() - t_s)

            target_warehouse_node = cluster_center_nodes_map[next_best_zone]
            t_s = time.perf_counter()
            try:
                sp_to_wh = nx.shortest_path(G, source=current_node, target=target_warehouse_node, weight="length")
            except nx.NetworkXNoPath: # Ne devrait pas arriver si has_path a été vérifié
                zones_to_visit_with_deliveries.remove(next_best_zone)
                active_deliveries_by_zone.pop(next_best_zone, None)
                continue # Essayer une autre zone
            local_prof_data["calc_sp_to_warehouse"] += (time.perf_counter() - t_s)

            path_dist_to_wh = sum(G.edges[u,v,0]['length'] for u,v in zip(sp_to_wh[:-1],sp_to_wh[1:]))
            total_distance_meters += path_dist_to_wh
            route.extend(sp_to_wh[1:])
            current_node = target_warehouse_node
            current_warehouse_node = target_warehouse_node # Mettre à jour l'entrepôt de la zone actuelle
            current_zone = next_best_zone
            remaining_capacity = package_capacity # Recharger à l'entrepôt
            G.nodes[current_node]['status'] = 'truck_at_warehouse'
            # print(f"Moved to new zone {current_zone} (WH: {current_warehouse_node}). Capacity refilled.")

        # Servir les livraisons dans la zone actuelle
        # Utiliser une copie car la liste peut être modifiée
        deliveries_in_current_zone_snapshot = list(active_deliveries_by_zone.get(current_zone, []))

        for _ in range(len(deliveries_in_current_zone_snapshot)): # Max une itération par livraison initialement dans la zone
            if not active_deliveries_by_zone.get(current_zone): break # Zone vidée

            if remaining_capacity <= 0:
                # print(f"Capacity depleted in zone {current_zone}. Returning to WH {current_warehouse_node}.")
                if current_node != current_warehouse_node:
                    t_s = time.perf_counter()
                    try:
                        sp_to_refill = nx.shortest_path(G, source=current_node, target=current_warehouse_node, weight="length")
                    except nx.NetworkXNoPath:
                        # Problème critique si on ne peut pas retourner à son propre entrepôt
                        return route, total_distance_meters, {"__local_prof__": local_prof_data}
                    local_prof_data["calc_sp_return_to_warehouse"] += (time.perf_counter() - t_s)
                    total_distance_meters += sum(G.edges[u,v,0]['length'] for u,v in zip(sp_to_refill[:-1],sp_to_refill[1:]))
                    route.extend(sp_to_refill[1:])
                    current_node = current_warehouse_node
                remaining_capacity = package_capacity
                G.nodes[current_node]['status'] = 'truck_refilling'
                # print(f"Refilled capacity at WH {current_warehouse_node}.")

            # Trouver la livraison la plus proche dans la zone actuelle
            t_s = time.perf_counter()
            # Filtrer seulement les "pending" et accessibles
            pending_and_reachable_in_zone = [
                n for n in active_deliveries_by_zone.get(current_zone, [])
                if G.nodes[n].get('status') == 'pending' and nx.has_path(G, source=current_node, target=n)
            ]
            if not pending_and_reachable_in_zone: break # Plus de livraisons faisables dans la zone

            try:
                nearest_delivery_node_id = min(pending_and_reachable_in_zone,
                                               key=lambda n: nx.shortest_path_length(G, source=current_node, target=n, weight="length"))
            except ValueError: break # Si min sur liste vide
            local_prof_data["find_nearest_in_zone"] += (time.perf_counter() - t_s)

            if 'delivery_info' not in G.nodes[nearest_delivery_node_id] or 'packages' not in G.nodes[nearest_delivery_node_id]['delivery_info']:
                # print(f"Warning: Node {nearest_delivery_node_id} missing package info. Removing from zone.")
                active_deliveries_by_zone.get(current_zone, []).remove(nearest_delivery_node_id)
                continue # Passer à la prochaine livraison potentielle

            packages_at_node = G.nodes[nearest_delivery_node_id]['delivery_info']['packages']

            if remaining_capacity >= packages_at_node:
                t_s = time.perf_counter()
                try:
                    sp_to_delivery = nx.shortest_path(G, source=current_node, target=nearest_delivery_node_id, weight="length")
                except nx.NetworkXNoPath: # Ne devrait pas arriver si has_path a été vérifié
                    active_deliveries_by_zone.get(current_zone, []).remove(nearest_delivery_node_id)
                    continue
                local_prof_data["calc_sp_to_delivery"] += (time.perf_counter() - t_s)

                total_distance_meters += sum(G.edges[u,v,0]['length'] for u,v in zip(sp_to_delivery[:-1],sp_to_delivery[1:]))
                route.extend(sp_to_delivery[1:])
                current_node = nearest_delivery_node_id
                remaining_capacity -= packages_at_node
                G.nodes[current_node]['status'] = 'serviced' # MARQUER COMME LIVRÉ
                # print(f"Delivered to {current_node}. Capacity: {remaining_capacity}. Status: {G.nodes[current_node]['status']}")

                # Retirer de la liste active de la zone
                if current_zone in active_deliveries_by_zone and nearest_delivery_node_id in active_deliveries_by_zone[current_zone]:
                    active_deliveries_by_zone[current_zone].remove(nearest_delivery_node_id)
            else: # Pas assez de capacité
                # print(f"Not enough capacity ({remaining_capacity}) for {nearest_delivery_node_id} ({packages_at_node} pkgs). Will refill.")
                remaining_capacity = 0 # Forcer le retour à l'entrepôt au prochain tour
                continue # Pour déclencher la vérification de capacité / retour WH

        # Après avoir tenté de servir toutes les livraisons dans la zone (ou être à court de capacité)
        if not active_deliveries_by_zone.get(current_zone): # Si la liste est vide
            zones_to_visit_with_deliveries.discard(current_zone)
            # print(f"Zone {current_zone} completed or emptied.")

    # Retourner à l'entrepôt de départ initial (start_node)
    if route and route[-1] != start_node: # Si on n'est pas déjà au start_node
        # print(f"All deliveries done. Returning to initial start warehouse {start_node}.")
        if nx.has_path(G, source=current_node, target=start_node):
            t_s = time.perf_counter()
            sp_return_to_depot = nx.shortest_path(G, source=current_node, target=start_node, weight="length")
            total_distance_meters += sum(G.edges[u,v,0]['length'] for u,v in zip(sp_return_to_depot[:-1],sp_return_to_depot[1:]))
            route.extend(sp_return_to_depot[1:])
            G.nodes[start_node]['status'] = 'truck_returned_depot'
            local_prof_data["calc_sp_return_to_warehouse"] += (time.perf_counter() - t_s)
        # else:
        # print(f"CRITICAL: Could not find path back to start_node {start_node} from {current_node}.")

    # Nettoyer la route (enlever les doublons consécutifs)
    if route:
        final_route = [route[0]]
        for i in range(1, len(route)):
            if route[i] != route[i-1]:
                final_route.append(route[i])
        route = final_route

    # print(f"Final route: {len(set(route))} unique nodes. Distance: {total_distance_meters/1000:.2f} km.")
    return route, total_distance_meters, {"__local_prof__": local_prof_data}
