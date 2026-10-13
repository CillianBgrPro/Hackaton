"""Lieux candidats au label TAO Safe Place, rattachés aux arrêts, et arrêts prioritaires.

Entrées : cache/osm/pois_metro.json, build/basemap.json, signalements nettoyés, questionnaire (facultatif)
Sorties : build/safe_places.json (données de la carte)
          dist/safe-places/safe_places_candidats.csv et .geojson (liste à démarcher)
"""
import collections
import csv
import json
import re

from src.common import BUILD, CACHE, DIST, PILOT_POLES, load_basemap, meters, safety_counts_by_stop, survey_citations, write_json
from src.safe_places.opening_hours import closing, is_open, parse

MAX_DISTANCE = 200            # m à vol d'oiseau, soit 2 à 3 min à pied
LATE, NIGHT = 21 * 60, 23 * 60 + 30   # 21 h : début du service de nuit TAO (SOS et arrêts à la demande)
OUT = DIST / "safe-places"

# (clé, libellé, groupe de la note « Label TAO Safe Place », test sur les attributs OSM)
CATEGORIES = [
    ("boulangerie", "Boulangerie", "commerce", lambda t: t.get("shop") in ("bakery", "pastry")),
    ("pharmacie", "Pharmacie", "commerce", lambda t: t.get("amenity") == "pharmacy"),
    ("tabac", "Tabac, presse", "commerce", lambda t: t.get("shop") in ("tobacco", "newsagent", "kiosk")),
    ("superette", "Supérette, supermarché", "commerce", lambda t: t.get("shop") in ("convenience", "supermarket", "general")),
    ("bar", "Bar, café", "commerce", lambda t: t.get("amenity") in ("bar", "pub", "cafe", "cafe;bar")),
    ("restaurant", "Restaurant, restauration rapide", "commerce", lambda t: t.get("amenity") in ("restaurant", "fast_food")),
    ("hotel", "Hôtel", "tard", lambda t: t.get("tourism") in ("hotel", "hostel")),
    ("station", "Station-service", "tard", lambda t: t.get("amenity") == "fuel"),
    ("cinema", "Cinéma", "tard", lambda t: t.get("amenity") == "cinema"),
    ("public", "Lieu public (médiathèque, mairie, agence TAO)", "public",
     lambda t: t.get("amenity") in ("library", "townhall") or t.get("name", "").startswith("Agence commerciale TAO")),
]
CLASS_LABEL = {"nuit": "Ouvert après 23 h 30 ou la nuit", "tard": "Ouvert jusqu'à 21 h – 23 h 30",
               "jour": "Journée (ferme avant 21 h)", "ferme": "Ouvert seulement certains soirs", "nr": "Horaires non renseignés"}


def category(tags):
    for key, label, group, test in CATEGORIES:
        if test(tags):
            return key, label, group
    return None


def clock(minutes):
    if not minutes:
        return None
    m = minutes - 1440 if minutes > 1440 else minutes
    return "minuit" if m in (0, 1440) else f"{m // 60} h {m % 60:02d}".replace(" h 00", " h")


def opening_class(oh):
    """Classe d'horaires d'après l'heure de fermeture tenue au moins trois soirs de semaine."""
    week = parse(oh)
    if not week:
        return "nr", None, None, None
    closes = sorted((closing(week, d) or 0 for d in range(5)), reverse=True)
    usual = closes[2]
    weekend = max(closing(week, 4) or 0, closing(week, 5) or 0)
    if oh.strip() == "24/7" or usual >= NIGHT:
        cls = "nuit"
    elif usual >= LATE:
        cls = "tard"
    elif usual > 0:
        cls = "jour"
    else:
        cls = "ferme"
    return cls, usual, weekend if weekend >= LATE else None, any(is_open(week, d, 15 * 60) for d in range(5))


def main():
    pois = json.loads((CACHE / "osm" / "pois_metro.json").read_text(encoding="utf-8"))
    stops = load_basemap()["stops"]
    tram_stops = [s for s in stops if s["tram"]]
    candidates, police = [], []
    for t in pois:
        name = t.get("name", "")
        if t.get("amenity") == "police":
            police.append({"n": name or "Police", "c": [t["lat"], t["lon"]]})
            continue
        cat = category(t)
        if not cat:
            continue
        p = (t["lat"], t["lon"])
        near = min(stops, key=lambda s: meters(p, s["c"]))
        d = meters(p, near["c"])
        if d > MAX_DISTANCE:
            continue
        near_tram = min(tram_stops, key=lambda s: meters(p, s["c"]))
        cls, usual, weekend, day = opening_class(t.get("opening_hours"))
        addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
        if t.get("addr:city"):
            addr = f"{addr}, {t['addr:city']}" if addr else t["addr:city"]
        candidates.append({
            "id": t["id"], "n": name or cat[1], "named": bool(name), "k": cat[0], "g": cat[2], "lat": t["lat"], "lon": t["lon"],
            "cls": cls, "close": clock(usual), "wk": clock(weekend), "day": day, "oh": t.get("opening_hours"), "addr": addr,
            "stop": near["n"], "d": round(d), "tram": near["tram"], "lines": near["l"],
            "tstop": near_tram["n"], "td": round(meters(p, near_tram["c"])),
            "auto": t.get("automated") == "yes" or t.get("self_service") == "yes"})

    # Arrêts (regroupés par nom) avec la demande : signalements sûreté / incivilités, citations, pôles pilotes
    signals = safety_counts_by_stop()
    cites = {k.lower(): v for k, v in survey_citations().items()}
    poles = {k.lower(): v for k, v in PILOT_POLES.items()}
    grouped = collections.OrderedDict()
    for s in stops:
        g = grouped.setdefault(s["n"].lower(), {"n": s["n"], "c": s["c"], "tram": s["tram"], "l": set()})
        if s["tram"] and not g["tram"]:
            g.update(c=s["c"], tram=True)
        g["l"] |= set(s["l"])
    order = lambda v: (v not in ("A", "B"), not v.isdigit(), int(v) if v.isdigit() else 0, v)
    stop_rows = []
    for key, g in grouped.items():
        near = [c for c in candidates if meters((c["lat"], c["lon"]), g["c"]) <= MAX_DISTANCE]
        sig, sig_evening, _ = signals.get(key, [0, 0, 0])
        stop_rows.append({"n": g["n"], "c": g["c"], "tram": g["tram"], "l": sorted(g["l"], key=order)[:8],
                          "sig": sig, "sev": sig_evening, "cite": cites.get(key, 0), "pole": poles.get(key),
                          "eve": sum(c["cls"] in ("tard", "nuit") for c in near), "day": sum(bool(c["day"]) for c in near),
                          "nr": sum(c["cls"] == "nr" for c in near), "all": len(near)})
    write_json(BUILD / "safe_places.json", {
        "pois": candidates, "police": police, "stops": stop_rows,
        "meta": {"total_metro": len(pois), "with_hours_metro": sum("opening_hours" in p for p in pois)}}, compact=True)

    # Exports pour la prospection
    OUT.mkdir(parents=True, exist_ok=True)
    labels = {k: lab for k, lab, _, _ in CATEGORIES}
    with open(OUT / "safe_places_candidats.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["nom", "type", "horaires_classe", "ferme_en_semaine_vers", "tard_ven_sam", "horaires_osm", "adresse",
                    "arret_proche", "distance_m", "lignes_arret", "arret_tram_proche", "distance_tram_m", "latitude", "longitude", "lien_osm"])
        for c in sorted(candidates, key=lambda c: (c["stop"], c["d"])):
            w.writerow([c["n"], labels[c["k"]], CLASS_LABEL[c["cls"]], c["close"] or "", c["wk"] or "", c["oh"] or "", c["addr"],
                        c["stop"], c["d"], " ".join(c["lines"]), c["tstop"], c["td"], c["lat"], c["lon"], f"https://www.openstreetmap.org/{c['id']}"])
    geojson = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
         "properties": {"nom": c["n"], "type": labels[c["k"]], "horaires_classe": CLASS_LABEL[c["cls"]], "ferme_vers": c["close"],
                        "horaires_osm": c["oh"], "adresse": c["addr"], "arret_proche": c["stop"], "distance_m": c["d"], "osm": c["id"]}}
        for c in candidates]}
    write_json(OUT / "safe_places_candidats.geojson", geojson)

    counts = collections.Counter(c["cls"] for c in candidates)
    trams = [r for r in stop_rows if r["tram"]]
    priority = [r for r in stop_rows if r["sig"] >= 2 or r["cite"] >= 2 or r["pole"]]
    print(f"{len(candidates)} lieux candidats à moins de {MAX_DISTANCE} m d'un arrêt :",
          ", ".join(f"{CLASS_LABEL[k].lower()} {counts[k]}" for k in CLASS_LABEL))
    print(f"Arrêts de tram avec un lieu ouvert après 21 h : {sum(r['eve'] > 0 for r in trams)} sur {len(trams)}")
    gaps = [r["n"] for r in priority if r["eve"] == 0]
    print(f"Arrêts prioritaires sans lieu ouvert le soir ({len(gaps)} sur {len(priority)}) :", ", ".join(gaps))


if __name__ == "__main__":
    main()
