"""Nettoie l'export des signalements et produit les fichiers de sortie.

Entrée  : export Excel (date, mode, lieu, coordonnées GPS, motifs)
Sorties : dist/signalements_tao.geojson, .kml, _nettoye.csv
          build/data.json (données compactes pour la page)

Nettoyage : retrait des tests, des doublons exacts et des coordonnées hors réseau ;
harmonisation des motifs ; rattachement à une famille, une commune et l'arrêt TAO le plus proche.
"""
import argparse
import collections
import csv
import json
import math
import unicodedata
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
CACHE, BUILD, DIST = ROOT / "cache", ROOT / "build", ROOT / "dist"

# Ordre = priorité pour la famille principale (couleur et symbole sur la carte).
# Les couleurs doivent rester alignées avec --f0…--f4 dans src/web/styles.css (thème clair).
FAMILIES = [
    {"id": "surete", "label": "Sûreté et atteintes aux personnes", "short": "Sûreté", "shape": "triangle", "color": "#ba022f"},
    {"id": "incivilites", "label": "Incivilités et dégradations", "short": "Incivilités", "shape": "diamond", "color": "#832bc3"},
    {"id": "conducteur", "label": "Comportement conducteur", "short": "Conducteur", "shape": "square", "color": "#509edc"},
    {"id": "reclamations", "label": "Réclamations", "short": "Réclamations", "shape": "circle", "color": "#c9870f"},
    {"id": "autre", "label": "Autre ou non renseigné", "short": "Autre / n.r.", "shape": "ring", "color": "#8a9599"},
]
FAM_INDEX = {f["id"]: i for i, f in enumerate(FAMILIES)}

# Clé normalisée (minuscules, sans accents) -> (libellé propre, famille).
# Ajouter ici toute nouvelle valeur rencontrée dans un futur export.
MOTIFS = {
    "comportement menacant ou agressif": ("Comportement menaçant ou agressif", "surete"),
    "contact physique non sollicite": ("Contact physique non sollicité", "surete"),
    "propos ou gestes a connotation sexuelle": ("Propos ou gestes à connotation sexuelle", "surete"),
    "propos deplaces ou insistants": ("Propos déplacés ou insistants", "surete"),
    "intrusion dans l'espace personnel": ("Intrusion dans l'espace personnel", "surete"),
    "vol ou tentative de vol": ("Vol ou tentative de vol", "surete"),
    "situation ou comportement suspect": ("Situation ou comportement suspect", "surete"),
    "situtation ou comportement suspect": ("Situation ou comportement suspect", "surete"),
    "sentiment d'insecurite ou d'inconfort": ("Sentiment d'insécurité ou d'inconfort", "surete"),
    "vigipirate": ("Vigipirate", "surete"),
    "detention alcool ou personne qui fume": ("Détention d'alcool ou personne qui fume", "incivilites"),
    "degradation": ("Dégradation", "incivilites"),
    "degration": ("Dégradation", "incivilites"),
    "degration ou incivilite": ("Dégradation ou incivilité", "incivilites"),
    "degradation ou incivilite": ("Dégradation ou incivilité", "incivilites"),
    "incivilite": ("Incivilité", "incivilites"),
    "vandalisme": ("Vandalisme", "incivilites"),
    "fraude": ("Fraude", "incivilites"),
    "comportement conducteur": ("Comportement conducteur", "conducteur"),
    "reclamation": ("Réclamation", "reclamations"),
    "sans information": ("Sans information", "autre"),
    "autre situation": ("Autre situation", "autre"),
}
TEST_VALUES = {"test"}
MAX_DIST_OUTSIDE_METRO = 0.05   # degrés (~5 km) : au-delà, coordonnées considérées comme erronées
STOP_RADIUS_M = 250             # rayon de rattachement à un arrêt (repris dans la page)
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def norm_key(s):
    s = unicodedata.normalize("NFKD", s.replace("’", "'")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def clean_text(s):
    return " ".join(unicodedata.normalize("NFC", str(s)).split())


def dist_m(a, b):
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(lat))


def reverse_commune(lat, lng):
    url = f"https://geo.api.gouv.fr/communes?lat={lat}&lon={lng}&fields=nom"
    with urllib.request.urlopen(url, timeout=30) as fh:
        d = json.load(fh)
    return d[0]["nom"] if d else None


def kml_color(hex_color):
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"ff{b}{g}{r}"


def load_records(xlsx):
    df = pd.read_excel(xlsx).iloc[:, :5]
    df.columns = ["date", "mode", "lieu", "gps", "motif"]
    communes = [(f["properties"]["nom"], shape(f["geometry"]))
                for f in json.loads((CACHE / "communes.json").read_text())["features"]]
    metro = unary_union([g for _, g in communes])
    stops = json.loads((BUILD / "basemap.json").read_text(encoding="utf-8"))["stops"]

    recs, excluded, seen = [], [], {}
    for i, r in df.iterrows():
        line_no = i + 2   # numéro de ligne dans Excel (en-tête = ligne 1)
        lieu, raw = clean_text(r.lieu), clean_text(r.motif)
        sig = (str(r.date), lieu, str(r.gps).strip(), raw)
        if sig in seen:
            excluded.append({"ligne": line_no, "raison": f"Doublon exact de la ligne {seen[sig]}", "date": str(r.date), "lieu": lieu})
            continue
        seen[sig] = line_no
        if norm_key(raw) in TEST_VALUES:
            excluded.append({"ligne": line_no, "raison": "Signalement de test", "date": str(r.date), "lieu": lieu})
            continue
        lat, lng = (float(x) for x in str(r.gps).split(","))
        pt = Point(lng, lat)
        com = next((n for n, g in communes if g.contains(pt)), None)
        if com is None:
            if metro.distance(pt) > MAX_DIST_OUTSIDE_METRO:
                excluded.append({"ligne": line_no, "raison": "Coordonnées hors du réseau TAO", "date": str(r.date), "lieu": lieu})
                continue
            com = (reverse_commune(lat, lng) or "Commune inconnue") + " (hors Métropole)"

        motifs, fams = [], []
        for part in raw.split(";"):
            k = norm_key(part)
            if not k:
                continue
            if k not in MOTIFS:
                raise SystemExit(f"Ligne {line_no} : motif inconnu « {part.strip()} ». Ajoutez-le au dictionnaire MOTIFS.")
            label, fam = MOTIFS[k]
            if label not in motifs:
                motifs.append(label)
            if fam not in fams:
                fams.append(fam)
        fams.sort(key=FAM_INDEX.get)

        nearest = min(stops, key=lambda s: dist_m((lat, lng), s["c"]))
        recs.append({"ligne": line_no, "ts": pd.Timestamp(r.date), "mode": clean_text(r["mode"]), "lieu": lieu,
                     "lat": round(lat, 6), "lng": round(lng, 6), "motifs": motifs, "fams": fams, "commune": com,
                     "arret": nearest["n"], "arret_d": round(dist_m((lat, lng), nearest["c"])),
                     "arret_lignes": nearest["l"], "brut": raw})
    recs.sort(key=lambda x: x["ts"])
    for n, x in enumerate(recs, 1):
        x["id"] = n
    return recs, excluded


def properties(x):
    return {
        "id": x["id"], "date": x["ts"].strftime("%Y-%m-%dT%H:%M"), "jour": x["ts"].strftime("%d/%m/%Y"),
        "heure": x["ts"].strftime("%H:%M"), "mois": x["ts"].strftime("%Y-%m"), "jour_semaine": JOURS[x["ts"].weekday()],
        "mode": x["mode"], "lieu": x["lieu"], "commune": x["commune"], "motifs": "; ".join(x["motifs"]),
        "famille_principale": FAMILIES[FAM_INDEX[x["fams"][0]]]["label"],
        "familles": "; ".join(FAMILIES[FAM_INDEX[f]]["label"] for f in x["fams"]),
        "arret_proche": x["arret"], "distance_arret_m": x["arret_d"], "lignes_arret": " ".join(x["arret_lignes"]),
        "motif_saisi": x["brut"], "ligne_excel": x["ligne"],
    }


def write_geojson(recs):
    gj = {"type": "FeatureCollection", "name": "signalements_tao", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x["lng"], x["lat"]]}, "properties": properties(x)}
        for x in recs]}
    (DIST / "signalements_tao.geojson").write_text(json.dumps(gj, ensure_ascii=False, indent=1), encoding="utf-8")


def write_csv(recs):
    keys = list(properties(recs[0]).keys())
    cols = keys[:1] + ["latitude", "longitude"] + keys[1:]
    with open(DIST / "signalements_tao_nettoye.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
        w.writeheader()
        for x in recs:
            w.writerow({**properties(x), "latitude": x["lat"], "longitude": x["lng"]})


def write_kml(recs, first, last):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           f"<name>Signalements réseau TAO ({first:%d/%m/%Y} – {last:%d/%m/%Y})</name>"]
    for f in FAMILIES:
        out.append(f'<Style id="{f["id"]}"><IconStyle><color>{kml_color(f["color"])}</color><scale>0.9</scale>'
                   '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>')
    fields = [("Date", "jour"), ("Heure", "heure"), ("Mode", "mode"), ("Lieu", "lieu"), ("Commune", "commune"),
              ("Motif(s)", "motifs"), ("Arrêt le plus proche", "arret_proche"), ("Lignes", "lignes_arret")]
    for f in FAMILIES:
        out.append(f"<Folder><name>{escape(f['label'])}</name>")
        for x in (x for x in recs if x["fams"][0] == f["id"]):
            p = properties(x)
            rows = "".join(f"<tr><td><b>{escape(a)}</b></td><td>{escape(str(p[b]))}</td></tr>" for a, b in fields)
            out.append(f"<Placemark><name>{escape(p['jour'])} – {escape(x['motifs'][0])}</name><styleUrl>#{f['id']}</styleUrl>"
                       f"<TimeStamp><when>{p['date']}:00</when></TimeStamp>"
                       f"<description><![CDATA[<table>{rows}</table>]]></description>"
                       f"<Point><coordinates>{x['lng']},{x['lat']},0</coordinates></Point></Placemark>")
        out.append("</Folder>")
    out.append("</Document></kml>")
    (DIST / "signalements_tao.kml").write_text("\n".join(out), encoding="utf-8")


def write_page_data(recs, excluded):
    modes = [m for m, _ in collections.Counter(x["mode"] for x in recs).most_common()]
    ordered = []   # motifs ordonnés par famille puis par ordre de déclaration
    for f in FAMILIES:
        for label, fam in dict.fromkeys(MOTIFS.values()):
            if fam == f["id"] and label not in ordered:
                ordered.append(label)
    used = [m for m in ordered if any(m in x["motifs"] for x in recs)]
    mi = {m: i for i, m in enumerate(used)}
    motif_fam = {label: fam for label, fam in MOTIFS.values()}
    communes = sorted({x["commune"] for x in recs}, key=lambda c: (c != "Orléans", "(hors" in c, c))
    page = {
        "families": [{k: f[k] for k in ("id", "label", "short", "shape")} for f in FAMILIES],
        "motifs": [[m, FAM_INDEX[motif_fam[m]]] for m in used],
        "modes": modes, "communes": communes, "excluded": excluded,
        # [id, date, mode, lieu, lat, lng, [motifs], [familles], commune, arrêt, distance arrêt (m), lignes]
        "recs": [[x["id"], x["ts"].strftime("%Y-%m-%dT%H:%M"), modes.index(x["mode"]), x["lieu"], x["lat"], x["lng"],
                  [mi[m] for m in x["motifs"]], [FAM_INDEX[f] for f in x["fams"]], communes.index(x["commune"]),
                  x["arret"], x["arret_d"], " ".join(x["arret_lignes"])] for x in recs],
    }
    (BUILD / "data.json").write_text(json.dumps(page, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Nettoie l'export des signalements TAO et produit les exports SIG.")
    ap.add_argument("xlsx", nargs="?", default=str(ROOT / "data" / "signalements.xlsx"), help="export Excel des signalements")
    args = ap.parse_args()
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    recs, excluded = load_records(args.xlsx)
    write_geojson(recs)
    write_csv(recs)
    write_kml(recs, recs[0]["ts"], recs[-1]["ts"])
    write_page_data(recs, excluded)
    print(f"{len(recs)} signalements conservés, {len(excluded)} écartés :")
    for e in excluded:
        print(f"  ligne {e['ligne']} : {e['raison']} ({e['lieu']})")
    print("Familles principales :", dict(collections.Counter(FAMILIES[FAM_INDEX[x['fams'][0]]]["short"] for x in recs)))


if __name__ == "__main__":
    main()
