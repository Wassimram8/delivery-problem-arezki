from flask import Flask, render_template, request, url_for, send_from_directory
import os
import sys
import json # Pour afficher le profiling joliment

# Ajouter le répertoire parent au sys.path pour importer core_logic
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir) # Ajoute mon_projet_livraison/ au path

from core_logic.pipeline import execute_main_pipeline
from core_logic import utils # Importer le module utils pour accéder à PROF_DATA

app = Flask(__name__)

# Le dossier où le core_logic sauvegarde ses outputs (GIFs, MP4s, GraphMLs)
CORE_OUTPUT_DIR = os.path.join(parent_dir, "core_output_web")
os.makedirs(CORE_OUTPUT_DIR, exist_ok=True)

@app.route('/media/<path:filename>')
def serve_media(filename):
    return send_from_directory(CORE_OUTPUT_DIR, filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Récupérer les valeurs du formulaire
        city_name = request.form.get('city_name', 'Pantin, France')
        network_type = request.form.get('network_type', 'drive')

        num_delivery_points_config = request.form.get('num_delivery_points_config', "10")
        packages_per_point_config = request.form.get('packages_per_point_config', "1-3")
        truck_capacity = int(request.form.get('truck_capacity', 10))

        cluster_range_str = request.form.get('cluster_range', "2,3,4")
        try:
            cluster_range_input = [int(x.strip()) for x in cluster_range_str.split(',') if x.strip()]
            if not cluster_range_input: # S'assurer qu'il y a au moins un élément par défaut
                cluster_range_input = [2,3,4]
        except ValueError:
            cluster_range_input = [2,3,4] # Défaut si parsing échoue

        animation_interval = int(request.form.get('animation_interval', 700))

        # Effacer les données de profiling précédentes AVANT de lancer une nouvelle exécution
        utils.PROF_DATA.clear() # Assure que chaque exécution a des données de profiling fraîches

        # Exécuter le pipeline du cœur logique
        results_data = execute_main_pipeline(
            city_name=city_name,
            network_type=network_type,
            output_folder=CORE_OUTPUT_DIR,
            num_delivery_points_config=num_delivery_points_config,
            packages_per_point_config=packages_per_point_config,
            truck_capacity=truck_capacity,
            cluster_range_input=cluster_range_input,
            animation_interval=animation_interval
        )

        # Préparer les URLs des médias pour le template
        # Vérifier si le chemin existe avant de créer l'URL
        if results_data.get("mp4_path") and os.path.exists(results_data["mp4_path"]):
            results_data["mp4_url"] = url_for('serve_media', filename=os.path.basename(results_data["mp4_path"]))
        else:
            results_data["mp4_url"] = None

        # Formatter les données de profiling pour l'affichage
        # results_data["profiling_data"] est déjà une copie de utils.PROF_DATA au moment de la fin du pipeline
        if "profiling_data" in results_data and results_data["profiling_data"]:
            results_data["profiling_json"] = json.dumps(results_data["profiling_data"], indent=2, sort_keys=True)
        else:
            results_data["profiling_json"] = json.dumps({"message": "Aucune donnée de profiling disponible pour cette exécution (ou le pipeline a échoué tôt)."}, indent=2)
        results_data["graph_file_exists"] = False # Initialiser

        graph_path = results_data.get("graph_path")
        print(f"Check de graph_path: {graph_path}")
        if graph_path and os.path.exists(results_data["graph_path"]):
            results_data["graph_file_exists"] = True
        return render_template('results.html', results=results_data)

    # Paramètres par défaut pour le formulaire (méthode GET)
    default_params = {
        "city_name": "Pantin, France",
        "network_type": "all",
        "num_delivery_points_config": "1-$nodes",
        "packages_per_point_config": "1-3",
        "truck_capacity": 10,
        "cluster_range": "2,3,4",
        "animation_interval": 500
    }
    return render_template('index.html', params=default_params)

if __name__ == '__main__':
    print(f"Démarrage du serveur Flask. Média servi depuis: {os.path.abspath(CORE_OUTPUT_DIR)}")
    print(f"Python sys.path inclus: {parent_dir}") # Pour vérifier l'import
    app.run(debug=True, host='0.0.0.0', port=5001) # host='0.0.0.0' pour accès depuis d'autres machines sur le réseau