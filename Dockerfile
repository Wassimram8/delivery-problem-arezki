# mon_projet/Dockerfile

# Utiliser une image Python officielle comme image de base
FROM python:3.11-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Installer les dépendances système, y compris ffmpeg
# - apt-get update met à jour la liste des paquets
# - apt-get install -y ffmpeg installe ffmpeg sans interaction
# - rm -rf /var/lib/apt/lists/* nettoie le cache apt pour réduire la taille de l'image
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copier d'abord le fichier des dépendances pour profiter du cache Docker
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier tout le reste du code de l'application dans le répertoire de travail
COPY . .

# Exposer le port sur lequel l'application tourne
EXPOSE 5000

# Commande pour lancer l'application
CMD ["python", "web_app/main.py"]