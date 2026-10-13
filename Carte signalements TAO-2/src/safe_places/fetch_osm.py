"""Télécharge l'extrait OpenStreetMap Centre-Val de Loire (Geofabrik) et en extrait les lieux utiles.

Sortie : cache/osm/pois_metro.json — commerces, lieux ouverts tard et lieux publics de la Métropole,
avec leurs horaires (opening_hours) quand ils sont renseignés.

L'extrait pèse environ 250 Mo : il n'est retéléchargé qu'avec --force.
L'API Overpass serait plus légère, mais elle est souvent saturée ; l'extrait complet est plus fiable.
"""
import argparse
import json
import re
import shutil
import urllib.request

import osmium

from src.common import CACHE

EXTRACT_URL = "https://download.geofabrik.de/europe/france/centre-latest.osm.pbf"
OSM = CACHE / "osm"
BBOX = (47.755, 1.76, 48.02, 2.115)  # emprise de la Métropole (lat min, lon min, lat max, lon max)

AMENITIES = {"pharmacy", "bar", "pub", "cafe", "restaurant", "fast_food", "fuel", "library", "townhall", "police", "cinema"}
SHOPS = {"bakery", "pastry", "convenience", "supermarket", "tobacco", "newsagent", "kiosk", "general", "ticket"}
TOURISM = {"hotel", "hostel"}
KEEP_TAGS = ("name", "opening_hours", "addr:housenumber", "addr:street", "addr:postcode", "addr:city",
             "brand", "operator", "automated", "self_service", "shop", "amenity", "tourism", "office")


def wanted(tags):
    name = tags.get("name", "")
    tao_agency = bool(re.search(r"\bTAO\b", name)) and ("agence" in name.lower() or tags.get("shop") == "ticket")
    return (tags.get("amenity") in AMENITIES or tags.get("shop") in SHOPS
            or tags.get("tourism") in TOURISM or tao_agency)


class PoiHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.pois = []

    def _add(self, kind, oid, lat, lon, tags):
        if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
            return
        t = dict(tags)
        if wanted(t):
            self.pois.append({"id": f"{kind}/{oid}", "lat": round(lat, 6), "lon": round(lon, 6),
                              **{k: t[k] for k in KEEP_TAGS if k in t}})

    def node(self, n):
        if n.tags and n.location.valid():
            self._add("node", n.id, n.location.lat, n.location.lon, [(t.k, t.v) for t in n.tags])

    def way(self, w):
        tags = [(t.k, t.v) for t in w.tags]
        if not tags or not wanted(dict(tags)):
            return
        pts = [(nd.lat, nd.lon) for nd in w.nodes if nd.location.valid()]
        if pts:  # bâtiment ou surface : on garde son centre
            self._add("way", w.id, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), tags)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="retélécharger l'extrait")
    args = ap.parse_args()
    OSM.mkdir(parents=True, exist_ok=True)
    pbf = OSM / "centre-latest.osm.pbf"
    if args.force or not pbf.exists():
        print("Téléchargement de l'extrait OpenStreetMap (environ 250 Mo)…")
        req = urllib.request.Request(EXTRACT_URL, headers={"User-Agent": "carte-signalements-tao/1.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(pbf, "wb") as fh:
            shutil.copyfileobj(r, fh)
    out = OSM / "pois_metro.json"
    if out.exists() and out.stat().st_mtime > pbf.stat().st_mtime and not args.force:
        print("Lieux OpenStreetMap déjà extraits :", out.relative_to(CACHE.parent))
        return
    h = PoiHandler()
    h.apply_file(str(pbf), locations=True)
    out.write_text(json.dumps(h.pois, ensure_ascii=False), encoding="utf-8")
    print(f"{len(h.pois)} lieux extraits dans la Métropole, dont {sum('opening_hours' in p for p in h.pois)} avec des horaires")


if __name__ == "__main__":
    main()
