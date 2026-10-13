# Projet TAO sécurité : cartes, analyses et maquettes

Tout le code produit pour l'étude sur la sécurité des usagères du réseau TAO (Orléans Métropole) :

1. **Carte des signalements** : les 298 signalements nettoyés sur une carte interactive, avec tableau de bord et exports SIG.
2. **Carte des Safe Places potentielles** : les commerces et lieux publics proches des arrêts, classés par horaires d'ouverture, et les arrêts prioritaires à couvrir le soir.
3. **Analyses** : synthèse du questionnaire usagères, plan du pilote Safe Place, calcul du Trajet Sécurité sur les horaires réels.
4. **Maquettes** : les planches de concept (widget SOS, scénario SOS, Safe Place, Trajet Sécurité) et les prompts vidéo.

## Prérequis

- Python 3.9 ou plus récent
- `make` (fourni avec les outils de développement macOS)
- Une connexion internet au premier lancement : GTFS, IGN, contours communaux, et l'extrait OpenStreetMap Centre-Val de Loire (environ 250 Mo)

## Démarrage

```bash
make
```

La première exécution crée l'environnement virtuel `.venv/`, installe les dépendances, télécharge les sources dans `cache/`, puis construit les deux cartes et les analyses. Les exécutions suivantes réutilisent le cache.

| Commande | Ce qu'elle produit |
|---|---|
| `make signalements` | `dist/carte-signalements-tao.html` + GeoJSON, KML, CSV des signalements |
| `make safe-places` | `dist/safe-places/carte-safe-places-tao.html` + liste à démarcher (CSV, GeoJSON) |
| `make analyses` | `build/analyses/` : `survey.json`, `pilot.json`, `trajet_securite.json` et deux cartes SVG |
| `make serve` | sert `dist/` sur http://localhost:8000 |
| `make refresh` | retélécharge toutes les sources (nouveau GTFS, IGN, OpenStreetMap) |
| `make clean` | supprime `build/` et `dist/` |

Pour une nouvelle version de l'export des signalements : `make XLSX="chemin/vers/export.xlsx"`. Si le script s'arrête sur « motif inconnu », ajoutez la valeur au dictionnaire `MOTIFS` de `src/process_signalements.py`.

## Structure

```
data/
  signalements.xlsx              export des signalements (anonymisé)
  questionnaire.xlsx             réponses au questionnaire usagères
src/
  common.py                      chemins, pôles pilotes, distances, lecture des données partagées
  fetch_sources.py               GTFS (avec calendrier), IGN BD TOPO, contours communaux, CSS Leaflet → cache/
  build_basemap.py               fond de carte simplifié et encodé → build/basemap.json
  process_signalements.py        nettoyage, familles, communes, arrêts → dist/ + build/data.json
  assemble.py                    assemble une page autonome à partir d'un dossier web
  web/                           carte des signalements (index.html, styles.css, app.js)
  safe_places/
    fetch_osm.py                 extrait OpenStreetMap Geofabrik → cache/osm/pois_metro.json
    opening_hours.py             lecture simplifiée des horaires OSM
    build_candidates.py          classement par horaires, arrêts proches, priorités → build/ et dist/safe-places/
    web/                         carte des Safe Places (index.html, styles.css, app.js)
  analyses/
    survey.py                    synthèse du questionnaire et lieux cités → build/analyses/survey.json
    pilot.py                     signalements et citations le long des trams A et B → build/analyses/pilot.json
    trajet_securite.py           itinéraires sur les horaires réels, derniers mètres, cartes SVG
maquettes/                       planches HTML et PNG, prompts vidéo
cache/  build/                   fichiers intermédiaires (ignorés par git, recréés par make)
dist/                            livrables
```

## Carte des signalements

Règles de nettoyage, dans `src/process_signalements.py` :

- **Doublons exacts** (même date et heure, lieu, coordonnées et motif) : seul le premier est conservé.
- **Tests** : les lignes dont le motif vaut « test » sont retirées.
- **Coordonnées hors réseau** : au-delà d'environ 5 km de la Métropole, le point est retiré. Plus près, il est rattaché à sa commune avec la mention « hors Métropole » (cas de Gidy, desservi par la ligne 53).
- **Motifs** : fautes de frappe corrigées, accents et majuscules unifiés. Un signalement peut porter plusieurs motifs.
- **Famille principale** (couleur et symbole sur la carte), par ordre de priorité : sûreté > incivilités > conducteur > réclamations > autre.
- **Arrêt le plus proche** : à vol d'oiseau, d'après les arrêts du GTFS.

### Familles et couleurs

| Famille | Symbole | Clair | Sombre |
|---|---|---|---|
| Sûreté et atteintes aux personnes | triangle | `#ba022f` | `#cc243d` |
| Incivilités et dégradations | losange | `#832bc3` | `#9a47b5` |
| Comportement conducteur | carré | `#509edc` | `#3f91ee` |
| Réclamations | rond | `#c9870f` | `#b28727` |
| Autre ou non renseigné | anneau | `#8a9599` | `#7d8a8f` |

Ces couleurs ont été vérifiées pour rester distinguables par les personnes daltoniennes (toutes paires, dans les deux thèmes). Le symbole sert de second repère. Pour les changer : variables `--f0` à `--f4` de `src/web/styles.css` et champ `color` de `FAMILIES` dans `src/process_signalements.py`.

## Carte des Safe Places potentielles

- **Lieux** : boulangeries, pharmacies, tabacs, supérettes, bars et cafés, restaurants, hôtels, stations-service, cinémas, médiathèques, mairies et agence TAO, tirés d'OpenStreetMap. Les commissariats sont affichés comme points de repère.
- **Proximité** : lieux à moins de 200 m à vol d'oiseau d'un arrêt de tram ou de bus, soit 2 à 3 minutes à pied (`MAX_DISTANCE`).
- **Horaires** : on retient l'heure de fermeture tenue au moins trois soirs de semaine. « Tard » à partir de 21 h, début du service de nuit TAO ; « nuit » à partir de 23 h 30 ou 24 h/24 (`LATE`, `NIGHT`).
- **Arrêt prioritaire** : au moins 2 signalements sûreté ou incivilités, ou 2 citations dans le questionnaire, ou situé dans un pôle pilote (`PILOT_POLES` dans `src/common.py`).

Limites : près de la moitié des lieux n'ont pas d'horaires dans OpenStreetMap, et les pharmacies de garde (qui changent chaque nuit) n'y figurent pas. Les stations-service sont souvent automatiques la nuit. Aucun lieu n'est partenaire : la carte sert à préparer la prospection. Données OSM sous licence ODbL : mentionner « © contributeurs OpenStreetMap ».

## Analyses

- **`survey.py`** : indicateurs du questionnaire (moments d'insécurité, solutions jugées utiles, intérêt pour le Trajet Sécurité) et rattachement des lieux cités aux arrêts. Les citations alimentent les priorités Safe Place et le plan du pilote.
- **`pilot.py`** : pour chaque arrêt des trams A (nord → sud) et B (ouest → est), les signalements sûreté et incivilités à moins de 250 m, ceux du soir et les citations. Résume les pôles centre-ville et campus de La Source.
- **`trajet_securite.py`** : reproduit le scénario de la maquette Trajet Sécurité sur les horaires réels du GTFS (paramètres en tête de fichier : `DATE`, `REQUEST`, `ORIGIN`, `DEST`, poids du coût). Il calcule le trajet le plus rapide et le trajet serein, les chemins à pied sur les rues IGN, et les attentes de correspondance A → B à De Gaulle sur la soirée. Avec `--explore`, il liste les trajets les plus rapides sur une plage de départs (algorithme Connection Scan).

  ```bash
  .venv/bin/python -m src.analyses.trajet_securite --explore
  ```

## Maquettes

Les planches de `maquettes/` sont des pages HTML autonomes, avec leur export PNG. Elles ont été construites à partir des résultats des analyses (chiffres, cartes SVG) : si les données changent, il faut reporter les nouvelles valeurs à la main. Elles portent la mention « maquette de travail non officielle » ; la charte TAO / Keolis reste à appliquer.

- `maquette-activite-en-direct` : widget après le scan, bouton SOS (appui court pour signaler, appui maintenu pour l'alarme).
- `scenario-sos-partage-position` : une alerte, trois destinataires (proches, chauffeur, poste central).
- `scenario-safe-place` : parcours Safe Place, kit du label, pilote croisé avec le questionnaire.
- `trajet-securite` : parcours dans l'app, comparaison sur données réelles, fonctionnement de l'algorithme.
- `prompts-videos/` : prompts Claude Design pour les vidéos explicatives.

## Publication en Artifact claude.ai

`make artifact` (signalements) et `make safe-places` produisent aussi une version sans balises `<html>`, `<head>` et `<body>` dans `build/`, au format attendu par les Artifacts. Versions en ligne actuelles :

- Signalements : https://claude.ai/artifact/Lk1zoNUeSrnPwKTesQ91Qc
- Safe Places : https://claude.ai/artifact/NPRwKpk965Sb85UW1rqoe5

## Sources et licences

- Signalements : export « Données 1 an SOS », anonymisé. Questionnaire : 51 réponses du 12 octobre 2026.
- Lignes, arrêts, horaires et couleurs des lignes : GTFS du réseau TAO (transport.data.gouv.fr), voir les conditions de réutilisation de la fiche.
- Routes, cours d'eau, voies ferrées : IGN BD TOPO® (Géoplateforme).
- Contours communaux : API Découpage administratif (geo.api.gouv.fr).
- Commerces et lieux publics : © contributeurs OpenStreetMap, extrait Geofabrik, licence ODbL.
- Bibliothèques : Leaflet 1.9.4, Leaflet.markercluster 1.5.3, Leaflet.heat 0.2.0 (cdnjs).
