import os
import random
import numpy as np
import osmnx as ox
import networkx as nx

from .utils import timing_decorator, normalize_city_name, parse_interval_config # Ajout de parse_interval_config

@timing_decorator
def load_or_download_graph_timed(city_name: str, network_type: str, cache_folder: str) -> nx.MultiDiGraph | None:
    # ... (fonction inchangée, mais s'assurer qu'elle retourne None en cas d'échec)
    # (votre version originale était correcte sur ce point)
    normalized_city = normalize_city_name(city_name + "_" + network_type)
    filepath = os.path.join(cache_folder, f"{normalized_city}.graphml")
    os.makedirs(cache_folder, exist_ok=True)
    try:
        if os.path.exists(filepath):
            G = ox.load_graphml(filepath)
        else:
            G = ox.graph_from_place(city_name, network_type=network_type)
            ox.save_graphml(G, filepath=filepath)

        if not G.graph.get('crs') or "epsg:4326" in str(G.graph.get('crs')).lower():
            G = ox.project_graph(G)
        elif 'projparams' not in G.graph: G = ox.project_graph(G)
        return G
    except Exception as e:
        print(f"Erreur lors du chargement/téléchargement du graphe pour {city_name}: {e}")
        return None


@timing_decorator
def prepare_graph_data_timed(G: nx.MultiDiGraph,
                             num_delivery_points_config: str, # ex: "10", "$nodes", "random"
                             packages_per_point_config: str, # ex: "2", "1-5", "1-$truck_capacity/2"
                             truck_capacity: int # Nécessaire si $truck_capacity est utilisé
                             ) -> tuple[nx.MultiDiGraph, list]:
    """
    Prépare les données de livraison sur le graphe en fonction de configurations flexibles.

    Args:
        G (nx.MultiDiGraph): Le graphe d'entrée.
        num_delivery_points_config (str): Configuration pour le nombre de points de livraison.
            Peut être un entier, "$nodes", ou "random".
        packages_per_point_config (str): Configuration pour le nombre de colis par point.
            Peut être un entier, ou un intervalle "min-max". Les valeurs min/max
            peuvent utiliser des variables de contexte comme "$truck_capacity".
        truck_capacity (int): Capacité du camion, utilisée pour évaluer les variables de contexte.

    Returns:
        tuple[nx.MultiDiGraph, list]: Le graphe modifié et la liste des IDs des nœuds de livraison.
    """
    if not G or not G.nodes:
        # print("Graphe vide ou non fourni à prepare_graph_data_timed.")
        return G, []

    all_node_ids = list(G.nodes)
    num_total_nodes = len(all_node_ids)
    if num_total_nodes == 0:
        return G, []

    # 1. Déterminer le nombre de points de livraison
    num_deliveries_actual = 0
    num_delivery_points_config = str(num_delivery_points_config).strip().lower()

    if num_delivery_points_config == "$nodes":
        num_deliveries_actual = num_total_nodes
    elif num_delivery_points_config == "random":
        num_deliveries_actual = random.randint(1, num_total_nodes)
    else:
        try:
            num_deliveries_actual = int(num_delivery_points_config)
            if num_deliveries_actual <= 0: num_deliveries_actual = 1 # Au moins 1 si un nombre est donné
            num_deliveries_actual = min(num_deliveries_actual, num_total_nodes) # Ne pas dépasser le nb de noeuds
        except ValueError:
            # print(f"Configuration invalide pour num_delivery_points_config ('{num_delivery_points_config}'). Défaut à 10 ou max noeuds.")
            num_deliveries_actual = min(10, num_total_nodes) # Un défaut raisonnable

    num_deliveries_actual = max(1, num_deliveries_actual) if num_total_nodes > 0 else 0 # S'assurer qu'il y a au moins une livraison si possible

    delivery_nodes_selected_ids = random.sample(all_node_ids, k=num_deliveries_actual) if num_deliveries_actual > 0 else []

    # 2. Nettoyer les attributs et initialiser
    for node_id in G.nodes():
        for attr in ['delivery_type', 'delivery_info', 'status', 'assigned_warehouse', 'cluster_id']:
            if attr in G.nodes[node_id]:
                del G.nodes[node_id][attr]
        G.nodes[node_id]['status'] = 'idle'

    # 3. Assigner les informations de livraison (nombre de colis)
    context_vars = {"truck_capacity": truck_capacity, "nodes": num_total_nodes}
    parsed_packages_config = parse_interval_config(packages_per_point_config, context_vars)

    for node_id in delivery_nodes_selected_ids:
        G.nodes[node_id]['delivery_type'] = 'delivery'

        num_packages_for_node = 1 # Défaut
        if isinstance(parsed_packages_config, tuple): # C'est un intervalle (min, max)
            min_pkgs, max_pkgs = parsed_packages_config
            num_packages_for_node = random.randint(min_pkgs, max_pkgs)
        else: # C'est un nombre fixe
            num_packages_for_node = parsed_packages_config

        # S'assurer que le nombre de colis n'est pas absurde (ex: négatif ou > capacité si c'était une contrainte)
        num_packages_for_node = max(1, num_packages_for_node)

        G.nodes[node_id]['delivery_info'] = {'packages': num_packages_for_node}
        G.nodes[node_id]['status'] = 'pending'

    # print(f"{len(delivery_nodes_selected_ids)} points de livraison configurés.")
    return G, delivery_nodes_selected_ids


def extract_delivery_node_coords(G: nx.MultiDiGraph) -> tuple[np.ndarray, list]:
    coords, node_ids_with_coords = [], []
    for node_id, data in G.nodes(data=True):
        if data.get('delivery_type') == 'delivery':
            if 'x' in data and 'y' in data:
                coords.append([data['x'], data['y']])
                node_ids_with_coords.append(node_id)
    if not coords: return np.array([]), []
    return np.array(coords), node_ids_with_coords