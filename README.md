# Étude d’un problème de livraison urbaine à l’aide d’un graphe routier

Projet réalisé par Arezki Hamadene  
Licence 3 MIAGE – Université Paris Nanterre  
Matière : Graphe et Open Data

## Objectif

Ce projet consiste à modéliser un problème de livraison urbaine à l’aide d’un graphe routier issu de données OpenStreetMap.

Le réseau routier est représenté sous forme de graphe. Des points de livraison sont générés sur ce réseau, puis une tournée est construite en utilisant des algorithmes de plus court chemin et une organisation par zones.

## Technologies utilisées

- Python
- Flask
- NetworkX
- OSMnx
- scikit-learn
- NumPy
- Matplotlib
- OpenStreetMap

## Fonctionnalités principales

- récupération du réseau routier d’une ville ;
- génération de points de livraison ;
- regroupement des livraisons en zones ;
- calcul d’une tournée de livraison ;
- prise en compte de la capacité du camion ;
- visualisation des résultats.
