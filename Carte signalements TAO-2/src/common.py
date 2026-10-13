"""Chemins, constantes et petits utilitaires partagés par les analyses et la carte des Safe Places."""
import csv
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE, BUILD, DIST, DATA = ROOT / "cache", ROOT / "build", ROOT / "dist", ROOT / "data"
GTFS = CACHE / "gtfs"
ANALYSES = BUILD / "analyses"

SIGNALEMENTS_CSV = DIST / "signalements_tao_nettoye.csv"
QUESTIONNAIRE_XLSX = DATA / "questionnaire.xlsx"

# Pôles du pilote Safe Place, retenus d'après les signalements et le questionnaire
PILOT_POLES = {
    "Gare d'Orléans": "centre", "République": "centre", "De Gaulle": "centre", "Royale-Châtelet": "centre",
    "Tourelles-Dauphine": "centre", "Saint-Marceau": "centre", "Mouillère": "centre", "CO'Met": "centre",
    "Zénith": "centre", "Université": "campus", "Parc Floral": "campus", "L'Indien": "campus",
}
SAFETY_FAMILIES = ("Sûreté", "Incivilités")  # familles retenues pour un lieu d'abri
EVENING = lambda hour: hour >= 19 or hour < 5


def meters(a, b):
    """Distance en mètres entre deux points (lat, lon), approximation locale suffisante à cette échelle."""
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * k)


def decode_polyline(s):
    """Décode une polyline Google (précision 5) en liste de (lat, lon)."""
    i = lat = lng = 0
    out = []
    while i < len(s):
        vals = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 31) << shift
                shift += 5
                if b < 32:
                    break
            vals.append(~(result >> 1) if result & 1 else result >> 1)
        lat += vals[0]
        lng += vals[1]
        out.append((lat / 1e5, lng / 1e5))
    return out


def norm(s):
    """Minuscules sans accents, espaces simples : pour comparer des libellés saisis à la main."""
    s = unicodedata.normalize("NFKD", str(s).replace("’", "'")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def base_stop_name(name):
    """Retire le suffixe de quai (« Gare d'Orléans - Quai L » → « Gare d'Orléans »)."""
    return re.sub(r"\s+-\s+Quai\s+\w+$", "", name).strip()


def read_gtfs(name):
    with open(GTFS / name, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_basemap():
    return json.loads((BUILD / "basemap.json").read_text(encoding="utf-8"))


def load_signalements():
    """Signalements nettoyés (sortie de process_signalements.py)."""
    with open(SIGNALEMENTS_CSV, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def safety_counts_by_stop(radius=250):
    """{nom d'arrêt en minuscules: [signalements sûreté ou incivilités, dont le soir, tous signalements]}."""
    out = {}
    for x in load_signalements():
        if int(x["distance_arret_m"]) > radius:
            continue
        c = out.setdefault(x["arret_proche"].lower(), [0, 0, 0])
        c[2] += 1
        if any(f in x["familles"] for f in SAFETY_FAMILIES):
            c[0] += 1
            c[1] += EVENING(int(x["heure"][:2]))
    return out


def survey_citations():
    """{nom d'arrêt: nombre de répondantes le citant}, lu dans build/analyses/survey.json s'il existe."""
    p = ANALYSES / "survey.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("stops", {})


def write_json(path, obj, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    kw = {"separators": (",", ":")} if compact else {"indent": 1}
    path.write_text(json.dumps(obj, ensure_ascii=False, **kw), encoding="utf-8")
