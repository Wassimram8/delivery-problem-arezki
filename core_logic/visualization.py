import os
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import networkx as nx
import osmnx as ox   # Pour ox.plot_graph

# Importer depuis le module utils dans le même package core_logic
from . import utils # On importe le module utils entier pour accéder à utils.timing_decorator

# Déclaration de 'ani' au niveau du module pour qu'il soit accessible par 'update'
# C'est une pratique courante pour les callbacks de FuncAnimation
ani = None

@utils.timing_decorator # Si vous avez mis timing_decorator dans utils.py
def visualize_route_matplotlib_timed(G_projected: nx.MultiDiGraph, route_nodes: list,
                                     start_node_osmid: int, # Actuellement non utilisé dans le plot mais gardé pour cohérence
                                     map_filename_base: str, # ex: "output_folder/city_network" (sans extension)
                                     animation_interval: int = 500) -> tuple[str | None, str | None]:
    """
    Visualise la route avec Matplotlib et sauvegarde l'animation en GIF et/ou MP4.
    Retourne les chemins d'accès aux fichiers GIF et MP4 sauvegardés (ou None si échec).
    """
    global ani # Permet à `update` de potentiellement arrêter `ani`

    if not route_nodes:
        # print("Route is empty, cannot visualize with Matplotlib.") # Moins de verbosité
        return None, None # Pas de GIF, pas de MP4
    print("Starting plot")
    fig, ax = ox.plot_graph(G_projected, show=False, close=False,
                            edge_color="gray", edge_alpha=0.3, edge_linewidth=0.5,
                            node_size=0, bgcolor="w") # Fond blanc explicite
    delivery_plots = {} # Pour stocker les objets scatter des maisons

    warehouse_x, warehouse_y = [], []
    for node_id, data in G_projected.nodes(data=True):
        if 'x' not in data or 'y' not in data: continue # Skip nodes without coordinates
        node_type = data.get('delivery_type')
        if node_type == 'warehouse':
            warehouse_x.append(data['x'])
            warehouse_y.append(data['y'])
        elif node_type == 'delivery':
            sc = ax.scatter(data['x'], data['y'], c='orange', s=60, ec='black', zorder=3) # Taille un peu augmentée
            delivery_plots[node_id] = sc

    if warehouse_x:
        print("Scattering")
        ax.scatter(warehouse_x, warehouse_y, c='blue', s=120, marker='s', ec='black', zorder=4) # Taille un peu augmentée

    truck_plot, = ax.plot([], [], 'o', color='red', markersize=10, zorder=5)
    trail_plot, = ax.plot([], [], '-', color='red', linewidth=2.5, alpha=0.7, zorder=2) # Ligne un peu plus épaisse

    # S'assurer que tous les nœuds de la route ont des coordonnées
    print("Checking coordinates")
    valid_route_nodes_for_coords = [node_id for node_id in route_nodes if node_id in G_projected.nodes and 'x' in G_projected.nodes[node_id] and 'y' in G_projected.nodes[node_id]]
    if len(valid_route_nodes_for_coords) != len(route_nodes):
        # print(f"Warning: {len(route_nodes) - len(valid_route_nodes_for_coords)} route nodes missing coordinates. Animation might be incomplete.")
        # On continue avec les nœuds valides, mais c'est un signe de problème en amont.
        # Pour la robustesse, on pourrait décider de ne pas animer si trop de nœuds manquent.
        # Pour l'instant, on utilise seulement les nœuds valides.
        # Il faudrait idéalement filtrer route_nodes au début, mais cela changerait la longueur de l'animation.
        # Solution simple: arrêter si la route devient vide après filtrage.
        if not valid_route_nodes_for_coords:
            # print("No valid route nodes with coordinates left after filtering. Cannot animate.")
            plt.close(fig)
            return None, None
        # Si on continue, il faut s'assurer que route_x_coords et route_y_coords sont basés sur valid_route_nodes_for_coords
        # et que len(frames) dans FuncAnimation correspond.
        # Pour la simplicité de cette étape, on assume que la route fournie est majoritairement valide
        # et que les list comprehensions ci-dessous ne lèveront pas d'erreurs.
        # La vérification après la création des listes de coordonnées est plus directe.

    route_x_coords = [G_projected.nodes[node_id]['x'] for node_id in route_nodes if node_id in G_projected.nodes and 'x' in G_projected.nodes[node_id]]
    route_y_coords = [G_projected.nodes[node_id]['y'] for node_id in route_nodes if node_id in G_projected.nodes and 'y' in G_projected.nodes[node_id]]


    # Vérification après la tentative d'extraction des coordonnées
    if not route_x_coords or len(route_x_coords) != len(route_nodes): # Si des nœuds manquaient de coords
        # print("Warning: Coordinate extraction failed for some route nodes. Cannot animate reliably.")
        plt.close(fig)
        return None, None # N'essaie pas d'animer si les données sont incomplètes

    serviced_in_animation = set()

    legend_handles = [
        plt.Line2D([0], [0], marker='s', color='w', label='Warehouse', markersize=10, markerfacecolor='blue', markeredgecolor='black'),
        plt.Line2D([0], [0], marker='o', color='w', label='Pending Delivery', markersize=8, markerfacecolor='orange', markeredgecolor='black'),
        plt.Line2D([0], [0], marker='o', color='w', label='Serviced Delivery', markersize=8, markerfacecolor='purple', markeredgecolor='black'),
        plt.Line2D([0], [0], marker='o', color='w', label='Truck', markersize=10, markerfacecolor='red'), # 'w' pour que le markerfacecolor soit visible
        plt.Line2D([0], [0], color='red', lw=2.5, alpha=0.7, label='Truck Path')
    ]
    ax.legend(handles=legend_handles, loc='upper left', bbox_to_anchor=(1.02, 1), borderaxespad=0., fontsize='small')

    blit_enabled = True # blit=False est plus stable et plus simple à déboguer

    def update(frame_num):
        # nonlocal serviced_in_animation # Pas nécessaire en Python 3 si on ne réassigne pas serviced_in_animation lui-même

        if frame_num >= len(route_nodes): # Sécurité, ne devrait pas arriver avec frames=len(route_nodes)
            if ani: ani.event_source.stop()
            return [] if blit_enabled else None # Retour attendu par blitting

        current_node_id = route_nodes[frame_num]
        # Utiliser les coordonnées pré-calculées pour éviter des accès répétitifs au dictionnaire du graphe
        truck_x, truck_y = route_x_coords[frame_num], route_y_coords[frame_num]

        truck_plot.set_data([truck_x], [truck_y])
        trail_plot.set_data(route_x_coords[:frame_num+1], route_y_coords[:frame_num+1])

        if current_node_id in delivery_plots and current_node_id not in serviced_in_animation:
            # Le statut 'serviced' actuel du nœud dans G_projected.nodes[...]['status']
            # est le résultat de la simulation de route. On l'utilise pour savoir si la couleur doit changer.
            # Ou plus simplement : si c'est un nœud de livraison, on change sa couleur la 1ère fois qu'on le visite DANS L'ANIMATION.
            if G_projected.nodes[current_node_id].get('delivery_type') == 'delivery':
                delivery_plots[current_node_id].set_facecolor('purple') # Changement de couleur
                serviced_in_animation.add(current_node_id)

        if blit_enabled:
            # Pour blit=True, retourner tous les artistes modifiés
            # Le titre change aussi, donc il faut l'inclure.
            artists_to_return = [truck_plot, trail_plot]
            if current_node_id in delivery_plots and G_projected.nodes[current_node_id].get('delivery_type') == 'delivery':
                if delivery_plots[current_node_id] not in artists_to_return: # Éviter doublons si déjà inclus
                    artists_to_return.append(delivery_plots[current_node_id])
            return artists_to_return
        return # Pour blit=False, pas besoin de retourner d'artistes


    ax.set_xlabel("X Coordinate (meters)")
    ax.set_ylabel("Y Coordinate (meters)")
    fig.tight_layout(rect=[0, 0, 0.80, 1]) # Ajuster pour que la légende et le titre ne se chevauchent pas

    # Création de l'animation
    # Note: 'ani' est déjà défini au niveau du module
    print("Creating animation")
    ani = animation.FuncAnimation(fig, update, frames=len(route_nodes),
                                  interval=animation_interval, blit=blit_enabled, repeat=False)

    # Sauvegarde en MP4 (si ffmpeg est disponible)
    mp4_filepath = f"{map_filename_base}.mp4"
    mp4_saved_path = None
    try:
        # petite vérification pour ffmpeg
        ffmpeg_available = False
        try:
            # Vérifie si ffmpeg est dans le PATH et exécutable
            if os.system("ffmpeg -version > nul 2>&1") == 0 or os.system("ffmpeg -version > /dev/null 2>&1") == 0 : # Pour Windows et Unix
                ffmpeg_available = True
            elif plt.rcParams['animation.ffmpeg_path'] != 'ffmpeg' and os.path.exists(plt.rcParams['animation.ffmpeg_path']):
                ffmpeg_available = True # Si un chemin explicite est configuré dans Matplotlib
        except Exception:
            pass # Erreur lors de la vérification, on suppose qu'il n'est pas là

        if ffmpeg_available:
            print(f"Attempting to save MP4 to {mp4_filepath} (requires ffmpeg)...") # Moins de verbosité
            calculated_fps_mp4 = max(5, int(1000 / animation_interval)) # Au moins 5 fps pour une vidéo
            ani.save(mp4_filepath, writer='ffmpeg', fps=calculated_fps_mp4, dpi=150) # DPI pour meilleure qualité
            print(f"MP4 Animation saved to '{mp4_filepath}'")
            mp4_saved_path = mp4_filepath
        else:
            print("ffmpeg not found or not configured. Skipping MP4 save.")
    except Exception as e:
        # print(f"Could not save MP4: {e}. Ensure ffmpeg is installed and in PATH. Skipping MP4.")
        mp4_saved_path = None

    plt.close(fig) # Très important pour libérer la mémoire, surtout si appelée en boucle ou par un serveur

    return mp4_saved_path