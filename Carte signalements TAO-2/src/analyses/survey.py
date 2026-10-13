"""Synthèse du questionnaire « Expérience des femmes dans les transports en commun ».

Entrée  : data/questionnaire.xlsx (export Google Forms)
Sortie  : build/analyses/survey.json (indicateurs, lieux cités, citations par arrêt)
"""
import argparse
from collections import Counter

import pandas as pd

from src.common import ANALYSES, QUESTIONNAIRE_XLSX, norm, write_json

# Repérage des colonnes par un extrait de leur intitulé (plus robuste que l'ordre)
COLUMNS = {
    "profil": "Profil",
    "moment": "À quel moment vous sentez-vous le moins en sécurité",
    "lieu": "Lieu précis d'insécurité",
    "probleme": "Quel problème avez-vous déjà rencontré",
    "solutions": "Parmi ces solutions",
    "trajet_securite": "Trajet sécurité",
    "sos_connu": "Saviez-vous que des boutons SOS",
    "suffisant": "sont-ils suffisants",
}

# Lieux cités en texte libre → arrêt du réseau (ou lieu hors arrêt)
PLACE_RULES = [
    ("Gare d'Orléans", lambda t: "gare" in t and "aubrais" not in t, True),
    ("De Gaulle", lambda t: "gaulle" in t, True),
    ("L'Indien", lambda t: "indien" in t, True),
    ("Parc Floral", lambda t: "parc flora" in t, True),
    ("Victor Hugo", lambda t: "victor hugo" in t, True),
    ("Léon Blum", lambda t: "leon blum" in t, True),
    ("Université", lambda t: "campus" in t or " fac" in " " + t, True),
    ("Argonne (quartier)", lambda t: "argonne" in t or "argogne" in t, False),
    ("La Source (quartier)", lambda t: "la source" in t, False),
    ("Saint-Jean-de-Braye", lambda t: "saint jean de braye" in t, False),
    ("Rue des Carmes", lambda t: "carmes" in t, False),
    ("Centre-ville", lambda t: "centre-ville" in t or "centre ville" in t, False),
]


def col(df, key):
    match = [c for c in df.columns if COLUMNS[key].lower() in str(c).lower()]
    if not match:
        raise SystemExit(f"Colonne introuvable : « {COLUMNS[key]} »")
    return df[match[0]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("xlsx", nargs="?", default=str(QUESTIONNAIRE_XLSX))
    args = ap.parse_args()
    df = pd.read_excel(args.xlsx)
    n = len(df)
    has = lambda key, txt: int(col(df, key).fillna("").map(lambda v: txt.lower() in str(v).lower()).sum())
    solutions = Counter(p.strip() for v in col(df, "solutions").dropna() for p in str(v).split(", "))
    places, stops = Counter(), Counter()
    for v in col(df, "lieu").dropna():
        t = norm(v)
        for name, rule, is_stop in PLACE_RULES:
            if rule(t):
                places[name] += 1
                if is_stop:
                    stops[name] += 1
    out = {
        "n": n,
        "femmes": int((col(df, "profil") == "Femme").sum()),
        "moment": {"soir_nuit": has("moment", "Le soir ou la nuit"), "arret": has("moment", "En attendant à un arrêt"),
                   "vehicule": has("moment", "Dans le tram ou le bus"), "marche": has("moment", "En marchant après"),
                   "pas_insecurite": has("moment", "pas particulièrement")},
        "attente_trop_longue": has("probleme", "Temps d’attente trop long"),
        "solutions": dict(solutions.most_common()),
        "trajet_securite": col(df, "trajet_securite").value_counts().to_dict(),
        "sos_connu": col(df, "sos_connu").value_counts().to_dict(),
        "dispositifs_suffisants": col(df, "suffisant").value_counts().to_dict(),
        "lieux_repondants": int(col(df, "lieu").notna().sum()),
        "places": dict(places.most_common()),
        "stops": dict(stops.most_common()),
    }
    write_json(ANALYSES / "survey.json", out)
    pct = lambda v: f"{round(100 * v / n)} %"
    print(f"Questionnaire : {n} réponses ({out['femmes']} femmes)")
    print(f"  moins en sécurité le soir ou la nuit : {pct(out['moment']['soir_nuit'])} · en attendant à un arrêt : {pct(out['moment']['arret'])}")
    print(f"  Safe places citées comme solution : {pct(solutions.get('“Safe places”', 0))}")
    print("  lieux cités :", ", ".join(f"{k} ({v})" for k, v in places.most_common()))


if __name__ == "__main__":
    main()
