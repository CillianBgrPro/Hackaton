"""Télécharge les données ouvertes nécessaires au fond de carte dans cache/.

- Contours des 22 communes d'Orléans Métropole (API Découpage administratif)
- Routes, surfaces en eau et voies ferrées (IGN BD TOPO via le WFS de la Géoplateforme)
- GTFS du réseau TAO, calendrier compris (transport.data.gouv.fr)
- Feuilles de style Leaflet et Leaflet.markercluster (cdnjs), intégrées dans la page

Les fichiers déjà présents sont conservés ; utiliser --force pour tout retélécharger.
"""
import argparse
import io
import json
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"
UA = {"User-Agent": "carte-signalements-tao/1.0"}

EPCI_ORLEANS_METROPOLE = "244500468"
GTFS_URL = "https://www.data.gouv.fr/api/1/datasets/r/b2dfbaa3-47e9-4749-b6a4-750bebd760e7"
GTFS_FILES = ["routes.txt", "shapes.txt", "stops.txt", "trips.txt", "stop_times.txt", "calendar_dates.txt"]
VENDOR_CSS = {
    "leaflet.css": "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
    "markercluster.css": "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.min.css",
}

WFS = "https://data.geopf.fr/wfs/ows"
BBOX = "1.76,47.755,2.115,48.02,'EPSG:4326'"   # emprise de la Métropole (lon, lat)
CORE = "1.83,47.81,2.0,47.96,'EPSG:4326'"      # cœur urbain, pour les rues locales
IGN_LAYERS = {
    "roads_main": ("BDTOPO_V3:troncon_de_route",
                   f"importance IN ('1','2','3','4') AND BBOX(geometrie,{BBOX})",
                   "geometrie,importance,nature,nom_collaboratif_gauche"),
    "roads_local": ("BDTOPO_V3:troncon_de_route",
                    f"importance='5' AND nature NOT IN ('Chemin','Sentier','Escalier','Route empierrée') AND BBOX(geometrie,{CORE})",
                    "geometrie,importance,nature"),
    "water": ("BDTOPO_V3:surface_hydrographique", f"BBOX(geometrie,{BBOX})", "geometrie,nature,persistance"),
    "rail": ("BDTOPO_V3:troncon_de_voie_ferree", f"BBOX(geometrie,{BBOX})", "geometrie,nature"),
}


def get(url, timeout=180):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def fetch_communes(force):
    out = CACHE / "communes.json"
    if out.exists() and not force:
        return
    url = (f"https://geo.api.gouv.fr/epcis/{EPCI_ORLEANS_METROPOLE}/communes"
           "?fields=nom,code,population&format=geojson&geometry=contour")
    out.write_bytes(get(url))
    print("communes :", len(json.loads(out.read_text())["features"]))


def fetch_ign(force):
    page = 5000
    for name, (typename, cql, props) in IGN_LAYERS.items():
        out = CACHE / f"{name}.json"
        if out.exists() and not force and json.loads(out.read_text()).get("props") == props:
            continue  # déjà en cache avec les mêmes attributs
        feats, start = [], 0
        while True:
            q = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES=typename,
                     OUTPUTFORMAT="application/json", COUNT=str(page), STARTINDEX=str(start),
                     SRSNAME="EPSG:4326", CQL_FILTER=cql, PROPERTYNAME=props, SORTBY="cleabs")
            batch = json.loads(get(WFS + "?" + urllib.parse.urlencode(q))).get("features", [])
            feats += batch
            if len(batch) < page:
                break
            start += page
        out.write_text(json.dumps({"type": "FeatureCollection", "props": props, "features": feats}))
        print(f"IGN {name} :", len(feats))


def fetch_gtfs(force):
    target = CACHE / "gtfs"
    if all((target / f).exists() for f in GTFS_FILES) and not force:
        return
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(get(GTFS_URL, timeout=300))) as z:
        for f in GTFS_FILES:
            (target / f).write_bytes(z.read(f))
    print("GTFS TAO :", ", ".join(GTFS_FILES))


def fetch_vendor_css(force):
    for name, url in VENDOR_CSS.items():
        out = CACHE / name
        if out.exists() and not force:
            continue
        out.write_bytes(get(url))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="retélécharger même si le cache existe")
    args = ap.parse_args()
    CACHE.mkdir(exist_ok=True)
    fetch_communes(args.force)
    fetch_ign(args.force)
    fetch_gtfs(args.force)
    fetch_vendor_css(args.force)
    print("Sources à jour dans", CACHE.relative_to(ROOT))


if __name__ == "__main__":
    main()
