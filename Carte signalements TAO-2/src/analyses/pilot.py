"""Plan du pilote Safe Place : signalements et citations le long des lignes de tram A et B.

Entrées : GTFS (ordre des arrêts), signalements nettoyés, build/analyses/survey.json (facultatif)
Sortie  : build/analyses/pilot.json — pour chaque arrêt, dans l'ordre de la ligne :
          [nom, signalements sûreté/incivilités à 250 m, dont le soir, tous signalements, citations]
"""
import collections

from src.common import ANALYSES, GTFS, PILOT_POLES, base_stop_name, read_gtfs, safety_counts_by_stop, survey_citations, write_json

# Sens de lecture retenu : nord → sud pour A, ouest → est pour B
LINE_START = {"A": "Jules Verne", "B": "Georges Pompidou"}


def tram_orders():
    routes = {r["route_id"]: r["route_short_name"] for r in read_gtfs("routes.txt")}
    names = {s["stop_id"]: base_stop_name(s["stop_name"]) for s in read_gtfs("stops.txt")}
    trip_line = {t["trip_id"]: routes[t["route_id"]] for t in read_gtfs("trips.txt") if routes[t["route_id"]] in LINE_START}
    seqs = collections.defaultdict(list)
    with open(GTFS / "stop_times.txt", encoding="utf-8-sig") as fh:
        hdr = fh.readline().strip().split(",")
        it, isd, iseq = hdr.index("trip_id"), hdr.index("stop_id"), hdr.index("stop_sequence")
        for row in fh:
            p = row.rstrip("\n").split(",")
            if p[it] in trip_line:
                seqs[p[it]].append((int(p[iseq]), p[isd]))
    best = {}
    for tid, v in seqs.items():
        order = [names[s] for _, s in sorted(v)]
        line = trip_line[tid]
        if order[0] == LINE_START[line] and len(order) > len(best.get(line, [])):
            best[line] = order
    return best


def main():
    orders = tram_orders()
    counts = safety_counts_by_stop()
    cites = {k.lower(): v for k, v in survey_citations().items()}
    out = {}
    for line, order in orders.items():
        rows = []
        for name in order:
            rel, ev, allc = counts.get(name.lower(), [0, 0, 0])
            rows.append([name, rel, ev, allc, cites.get(name.lower(), 0)])
        out[line] = rows
        print(f"Ligne {line} : {sum(r[1] for r in rows)} signalements sûreté ou incivilités à 250 m, "
              f"dont {sum(r[2] for r in rows)} le soir ; {sum(r[4] for r in rows)} citations")
    for pole in ("centre", "campus"):
        names = [n for n, p in PILOT_POLES.items() if p == pole]
        rows = [r for r in out.get("A", []) if r[0] in names]
        total = sum(r[1] for r in out.get("A", []))
        print(f"Pôle {pole} : {sum(r[1] for r in rows)} signalements sur {total} de la ligne A, "
              f"{sum(r[4] for r in rows)} citations")
    out["poles"] = PILOT_POLES
    write_json(ANALYSES / "pilot.json", out)


if __name__ == "__main__":
    main()
