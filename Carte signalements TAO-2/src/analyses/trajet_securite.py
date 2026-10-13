"""Trajet Sécurité : comparaison « le plus rapide » / « le plus serein » sur les horaires réels.

Scénario de la maquette : départ de la fac (campus de La Source) à 22 h 30, un soir de semaine,
pour rentrer près de Léon Blum (Saint-Jean-de-Braye). Tram A puis tram B, correspondance à De Gaulle.

Entrées : GTFS (avec calendar_dates), réseau de rues IGN (cache/roads_*.json), build/basemap.json
Sorties : build/analyses/trajet_securite.json, trajet_reseau.svg, trajet_derniers_metres.svg

  python -m src.analyses.trajet_securite             # scénario de la maquette
  python -m src.analyses.trajet_securite --explore   # trajets les plus rapides sur une plage de départs
"""
import argparse
import collections
import heapq
import json
import math

from src.common import ANALYSES, CACHE, GTFS, base_stop_name, decode_polyline, load_basemap, meters, read_gtfs, write_json

DATE = "20261013"                        # mardi, soir de semaine type
REQUEST = 22 * 3600 + 30 * 60            # Léa demande un itinéraire à 22 h 30
ORIGIN = (47.8432, 1.9352)               # fac, campus de La Source
DEST = (47.9165, 1.9745)                 # domicile (fictif), Saint-Jean-de-Braye
WALK_SPEED = 1.2                          # m/s
DETOUR = 1.3                              # facteur de détour pour les accès aux arrêts à vol d'oiseau
MIN_TRANSFER = 120                        # s
STOP_MARGIN = 2 * 60                      # le trajet serein fait arriver 2 min avant le tram
PLATFORM_MARGIN = 3 * 60                  # retour sur le quai 3 min avant le départ
# Poids du coût de sérénité (à calibrer avec TAO et des usagères)
W_WAIT, W_RESIDENTIAL, W_TRANSFER = 1.0, 0.8, 2.0
MAIN_ROADS = {"1", "2", "3", "4"}         # importance IGN : avenues et axes principaux
SAFE_PENALTY = {"1": 1.0, "2": 1.0, "3": 1.0, "4": 1.15, "5": 1.7}

hhmm = lambda s: f"{int(s) // 3600 % 24:02d}:{int(s) % 3600 // 60:02d}"   # horaire publié (tronqué)
hhmm_round = lambda s: hhmm(s + 30)                                         # heure calculée, arrondie


# ---------- horaires ----------
def load_timetable(t0=21 * 3600, t1=25 * 3600 + 30 * 60):
    active = {r["service_id"] for r in read_gtfs("calendar_dates.txt") if r["date"] == DATE and r["exception_type"] == "1"}
    if not active:
        raise SystemExit(f"Aucun service actif le {DATE} dans le GTFS : changez DATE.")
    routes = {r["route_id"]: r for r in read_gtfs("routes.txt")}
    trips = {t["trip_id"]: t for t in read_gtfs("trips.txt") if t["service_id"] in active}
    stops = {s["stop_id"]: s for s in read_gtfs("stops.txt") if s["location_type"] == "0"}
    hms = lambda t: (lambda h, m, s: h * 3600 + m * 60 + s)(*map(int, t.split(":")))
    times = collections.defaultdict(list)
    with open(GTFS / "stop_times.txt", encoding="utf-8-sig") as fh:
        hdr = fh.readline().strip().split(",")
        ix = {k: i for i, k in enumerate(hdr)}
        for row in fh:
            p = row.rstrip("\n").split(",")
            if p[ix["trip_id"]] in trips:
                times[p[ix["trip_id"]]].append((int(p[ix["stop_sequence"]]), p[ix["stop_id"]], hms(p[ix["arrival_time"]]), hms(p[ix["departure_time"]])))
    trip_stops, conns = {}, []
    for tid, v in times.items():
        v.sort()
        trip_stops[tid] = [(base_stop_name(stops[s]["stop_name"]), a, d, s) for _, s, a, d in v if s in stops]
        for x, y in zip(v, v[1:]):
            if t0 <= x[3] <= t1 and x[1] in stops and y[1] in stops:
                conns.append((x[3], y[2], x[1], y[1], tid))
    conns.sort()
    line_of = {tid: routes[t["route_id"]]["route_short_name"] for tid, t in trips.items()}
    return stops, trip_stops, conns, line_of


def next_departure(trip_stops, line_of, line, board, to, after):
    """Premier passage de la ligne à l'arrêt `board` après `after`, dans le sens qui mène à `to`.
    On retient l'heure de passage (arrivée du tram, portes ouvertes) : c'est l'heure à laquelle il faut être sur le quai."""
    best = None
    for tid, seq in trip_stops.items():
        if line_of[tid] != line:
            continue
        names = [s[0] for s in seq]
        if board in names and to in names and names.index(to) > names.index(board):
            dep = seq[names.index(board)][1]
            if dep >= after and (best is None or dep < best[0]):
                best = (dep, tid)
    if best is None:
        raise SystemExit(f"Pas de tram {line} de {board} vers {to} après {hhmm(after)}")
    seq = trip_stops[best[1]]
    return {s[0]: s[1] for s in seq}, best[0]


def transfer_waits(trip_stops, line_of):
    """Attentes de correspondance tram A (vers le nord) → tram B (vers l'est) à De Gaulle, 22 h – minuit."""
    arr = sorted(seq[[s[0] for s in seq].index("De Gaulle")][1] for tid, seq in trip_stops.items()
                 if line_of[tid] == "A" and _after(seq, "Royale-Châtelet", "De Gaulle"))
    dep = sorted(seq[[s[0] for s in seq].index("De Gaulle")][1] for tid, seq in trip_stops.items()
                 if line_of[tid] == "B" and _after(seq, "De Gaulle", "Clos du Hameau"))
    out = []
    for t in arr:
        if 22 * 3600 <= t <= 24 * 3600:
            nxt = [d for d in dep if d >= t + MIN_TRANSFER]
            if nxt:
                out.append([hhmm(t), hhmm(nxt[0]), (nxt[0] - t) // 60])
    return out


def _after(seq, a, b):
    names = [s[0] for s in seq]
    return a in names and b in names and names.index(a) < names.index(b)


# ---------- recherche d'itinéraires (Connection Scan) ----------
def csa(conns, stops, line_of, tdep, origin, dest, max_access=800, max_egress=950):
    pos = {sid: (float(s["stop_lat"]), float(s["stop_lon"])) for sid, s in stops.items()}
    walk = lambda m: int(m * DETOUR / WALK_SPEED)
    access = {s: walk(meters(origin, p)) for s, p in pos.items() if meters(origin, p) <= max_access}
    egress = {s: walk(meters(p, dest)) for s, p in pos.items() if meters(p, dest) <= max_egress}
    foot = footpaths(pos)
    S, J, board = {s: tdep + w for s, w in access.items()}, {s: ("start", w) for s, w in access.items()}, {}
    for cd, ca, a, b, tid in conns:
        if cd < tdep:
            continue
        if S.get(a, 1e18) + (MIN_TRANSFER if J.get(a, ("x",))[0] == "trip" else 0) <= cd:
            board[tid] = (cd, a)  # dernier point de montée possible : évite les allers-retours
        if tid in board and ca < S.get(b, 1e18):
            S[b] = ca
            J[b] = ("trip", tid, board[tid][1], board[tid][0], ca)
            for o, w in foot.get(b, ()):  # correspondance à pied vers un quai voisin
                if ca + w < S.get(o, 1e18):
                    S[o], J[o] = ca + w, ("walk", b)
    best = min(((S[s] + w, s) for s, w in egress.items() if s in S), default=None)
    if not best:
        return None
    arr, s = best
    legs = []
    while J[s][0] != "start":
        if J[s][0] == "walk":
            legs.append(f"à pied {base_stop_name(stops[J[s][1]]['stop_name'])} → {base_stop_name(stops[s]['stop_name'])}")
            s = J[s][1]
            continue
        _, tid, frm, dep, ca = J[s]
        legs.append(f"{line_of[tid]} {base_stop_name(stops[frm]['stop_name'])} {hhmm(dep)} → {base_stop_name(stops[s]['stop_name'])} {hhmm(ca)}")
        s = frm
    return arr, legs[::-1]


_FOOT = {}


def footpaths(pos, radius=350):
    """Correspondances à pied entre arrêts proches (temps de marche, à vol d'oiseau avec détour)."""
    if _FOOT:
        return _FOOT
    grid = collections.defaultdict(list)
    for sid, (la, lo) in pos.items():
        grid[(round(la / 0.004), round(lo / 0.006))].append(sid)
    for sid, p in pos.items():
        gx, gy = round(p[0] / 0.004), round(p[1] / 0.006)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in grid[(gx + dx, gy + dy)]:
                    d = meters(p, pos[o])
                    if o != sid and d <= radius:
                        _FOOT.setdefault(sid, []).append((o, int(d * DETOUR / WALK_SPEED) + 30))
    return _FOOT


# ---------- marche sur le réseau de rues ----------
def road_graph(bbox):
    adj = collections.defaultdict(list)
    lat0, lon0, lat1, lon1 = bbox
    for name, default in (("roads_main", "4"), ("roads_local", "5")):
        for f in json.loads((CACHE / f"{name}.json").read_text())["features"]:
            g, pr = f["geometry"], f["properties"]
            imp, nm = pr.get("importance") or default, pr.get("nom_collaboratif_gauche") or ""
            for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
                pts = [(round(c[1], 6), round(c[0], 6)) for c in ln]
                if not any(lat0 <= p[0] <= lat1 and lon0 <= p[1] <= lon1 for p in pts):
                    continue
                for a, b in zip(pts, pts[1:]):
                    d = meters(a, b)
                    adj[a].append((b, d, imp, nm))
                    adj[b].append((a, d, imp, nm))
    return adj


def walk_path(adj, src, dst, safe):
    nodes = list(adj)
    src, dst = min(nodes, key=lambda n: meters(n, src)), min(nodes, key=lambda n: meters(n, dst))
    dist, prev, pq = {src: 0}, {}, [(0, src)]
    while pq:
        c, u = heapq.heappop(pq)
        if u == dst:
            break
        if c > dist[u]:
            continue
        for v, d, imp, nm in adj[u]:
            w = d * (SAFE_PENALTY.get(imp, 1.7) if safe else 1)
            if c + w < dist.get(v, 1e18):
                dist[v], prev[v] = c + w, (u, d, imp, nm)
                heapq.heappush(pq, (c + w, v))
    path, length, main, names = [dst], 0.0, 0.0, collections.Counter()
    while path[-1] != src:
        u, d, imp, nm = prev[path[-1]]
        length += d
        main += d if imp in MAIN_ROADS else 0
        names[nm] += d
        path.append(u)
    return {"path": path[::-1], "length": round(length), "main_share": round(main / length, 2),
            "residential_m": round(length - main), "streets": [n for n, _ in names.most_common(4) if n]}


# ---------- cartes SVG ----------
def projector(bbox, width):
    lat0, lon0, lat1, lon1 = bbox
    k = math.cos(math.radians((lat0 + lat1) / 2))
    sx = width / ((lon1 - lon0) * k)
    return (lambda p: ((p[1] - lon0) * k * sx, (lat1 - p[0]) * sx)), (lat1 - lat0) * sx


def path_d(pts, f):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in map(f, pts))


def svg_network(bm, stops_xy):
    bbox = (47.835, 1.885, 47.918, 1.985)
    f, H = projector(bbox, 360)
    tram = {l["id"]: [decode_polyline(g) for g in l["g"]] for l in bm["lines"] if l["t"] == 0}
    out = [f'<svg viewBox="0 0 360 {H:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Trajet sur le réseau de tram"><rect width="360" height="{H:.0f}" fill="#eef1ef"/>']
    for poly in bm["water"]:
        out.append(f'<path d="{path_d(decode_polyline(poly[0]), f)}Z" fill="#c4dae5"/>')
    for lid, col in (("A", "#e2121a"), ("B", "#762a80")):
        for seg in tram[lid]:
            out.append(f'<path d="{path_d(seg, f)}" fill="none" stroke="{col}" stroke-opacity=".28" stroke-width="2.5"/>')
    pf, dg, ch = stops_xy["Parc Floral"], stops_xy["De Gaulle"], stops_xy["Clos du Hameau"]
    keep = {"A": lambda q: pf[0] - .0005 <= q[0] <= dg[0] + .0003, "B": lambda q: dg[1] - .0004 <= q[1] <= ch[1] + .0005}
    for lid, col in (("A", "#e2121a"), ("B", "#762a80")):
        for seg in tram[lid]:
            run = []
            for q in seg + [None]:
                if q is not None and keep[lid](q):
                    run.append(q)
                    continue
                if len(run) > 1:
                    out.append(f'<path d="{path_d(run, f)}" fill="none" stroke="{col}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
                run = []
    for name, (dx, dy, anchor) in {"Parc Floral": (8, 4, "start"), "De Gaulle": (9, 15, "start"), "Clos du Hameau": (-6, -10, "end")}.items():
        x, y = f(stops_xy[name])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#fff" stroke="#14181c" stroke-width="2.4"/>'
                   f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" font-size="11" font-weight="700" text-anchor="{anchor}" fill="#14181c" paint-order="stroke" stroke="#eef1ef" stroke-width="3">{name}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_last_meters(adj, bm, stops_xy, fast, safe):
    bbox = (47.9085, 1.9655, 47.9185, 1.9795)
    f, H = projector(bbox, 520)
    inside = lambda p: bbox[0] <= p[0] <= bbox[2] and bbox[1] <= p[1] <= bbox[3]
    main, local = [], []
    for a, lst in adj.items():
        for b, d, imp, nm in lst:
            if a < b and inside(a) and inside(b):
                (main if imp in MAIN_ROADS else local).append((a, b))
    out = [f'<svg viewBox="0 0 520 {H:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Derniers mètres à pied"><rect width="520" height="{H:.0f}" fill="#eef1ef"/>']
    out += [f'<path d="{path_d(s, f)}" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/>' for s in local]
    out += [f'<path d="{path_d(s, f)}" stroke="#d6dcdc" stroke-width="7.5" stroke-linecap="round"/>' for s in main]
    out += [f'<path d="{path_d(s, f)}" stroke="#fff" stroke-width="5.5" stroke-linecap="round"/>' for s in main]
    for l in bm["lines"]:
        if l["id"] == "B":
            out += [f'<path d="{path_d(decode_polyline(g), f)}" fill="none" stroke="#762a80" stroke-width="3.5"/>' for g in l["g"]]
    out.append(f'<path d="{path_d(fast["path"], f)}" fill="none" stroke="#6b7680" stroke-width="4" stroke-dasharray="2 7" stroke-linecap="round"/>')
    out.append(f'<path d="{path_d(safe["path"], f)}" fill="none" stroke="#138a52" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
    for name, (dx, dy, anchor) in {"Léon Blum": (-9, 16, "end"), "Clos du Hameau": (-10, 20, "end"), "Clos de l'Arche": (-8, -9, "end")}.items():
        x, y = f(stops_xy[name])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#fff" stroke="#762a80" stroke-width="3"/>'
                   f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" font-size="13" font-weight="700" text-anchor="{anchor}" fill="#14181c" paint-order="stroke" stroke="#eef1ef" stroke-width="4">{name}</text>')
    x, y = f(safe["path"][-1])
    out.append(f'<g transform="translate({x:.1f} {y:.1f})"><path d="M0-20 C9-20 13.5-13.5 13.5-8 C13.5 1 0 12 0 12 C0 12-13.5 1-13.5-8 C-13.5-13.5-9-20 0-20z" fill="#14181c"/></g>'
               f'<text x="{x + 16:.1f}" y="{y - 10:.1f}" font-size="13" font-weight="800" fill="#14181c" paint-order="stroke" stroke="#eef1ef" stroke-width="4">Domicile</text>')
    n = len(safe["path"])
    for i, label in ((n // 4, safe["streets"][0] if safe["streets"] else ""), (3 * n // 4, safe["streets"][1] if len(safe["streets"]) > 1 else "")):
        x, y = f(safe["path"][i])
        out.append(f'<text x="{x - 10:.1f}" y="{y + 4:.1f}" font-size="11.5" font-weight="700" font-style="italic" text-anchor="end" fill="#0e6b40" paint-order="stroke" stroke="#eef1ef" stroke-width="4">{label.title()}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- scénario ----------
def main():
    ap = argparse.ArgumentParser(description="Trajet Sécurité : scénario de la maquette.")
    ap.add_argument("--explore", action="store_true", help="lister les trajets les plus rapides entre 22 h 25 et 23 h")
    args = ap.parse_args()
    stops, trip_stops, conns, line_of = load_timetable()
    if args.explore:
        seen = set()
        for m in range(0, 36):
            t = 22 * 3600 + 25 * 60 + 60 * m
            r = csa(conns, stops, line_of, t, ORIGIN, DEST)
            if r and r[0] not in seen:
                seen.add(r[0])
                print(f"départ {hhmm(t)} → arrivée {hhmm(r[0])} :", " | ".join(r[1]))
        return
    bm = load_basemap()
    stops_xy = {}
    for s in bm["stops"]:
        if s["tram"] and s["n"] not in stops_xy:
            stops_xy[s["n"]] = tuple(s["c"])
    walk_min = lambda m: m / WALK_SPEED / 60
    quais = [(float(s["stop_lat"]), float(s["stop_lon"])) for s in stops.values() if base_stop_name(s["stop_name"]) == "Parc Floral"]
    access = min(meters(ORIGIN, q) for q in quais) * DETOUR / WALK_SPEED  # jusqu'au quai le plus proche
    a_times, a_dep = next_departure(trip_stops, line_of, "A", "Parc Floral", "De Gaulle", REQUEST + access)
    a_arr = a_times["De Gaulle"]
    b_times, b_dep = next_departure(trip_stops, line_of, "B", "De Gaulle", "Clos du Hameau", a_arr + MIN_TRANSFER)
    adj = road_graph((47.900, 1.950, 47.926, 1.992))
    fast_walk = walk_path(adj, stops_xy["Léon Blum"], DEST, safe=False)
    safe_walk = walk_path(adj, stops_xy["Clos du Hameau"], DEST, safe=True)
    transfer = (b_dep - a_arr) / 60
    fast = {"depart": REQUEST, "wait_stop": (a_dep - REQUEST - access) / 60, "transfer": transfer, "transfer_outdoor": transfer,
            "alight": "Léon Blum", "alight_time": b_times["Léon Blum"], "walk": fast_walk}
    safe = {"depart": a_dep - access - STOP_MARGIN, "wait_stop": STOP_MARGIN / 60, "transfer": transfer,
            "transfer_outdoor": PLATFORM_MARGIN / 60, "safe_place": transfer - PLATFORM_MARGIN / 60,
            "alight": "Clos du Hameau", "alight_time": b_times["Clos du Hameau"], "walk": safe_walk}
    for t in (fast, safe):
        for k in ("wait_stop", "transfer", "transfer_outdoor", "safe_place"):  # minutes affichées, arrondies
            if k in t:
                t[k] = round(t[k])
        t["arrival"] = t["alight_time"] + t["walk"]["length"] / WALK_SPEED
        t["duration"] = round((t["arrival"] - REQUEST) / 60)
        t["exposed_wait"] = t["wait_stop"] + t["transfer_outdoor"]
        t["cost"] = t["duration"] + W_WAIT * t["exposed_wait"] + W_RESIDENTIAL * walk_min(t["walk"]["residential_m"]) + W_TRANSFER
    waits = transfer_waits(trip_stops, line_of)
    out = {"date": DATE, "tram_a": {"board": "Parc Floral", "dep": hhmm(a_dep), "arr_de_gaulle": hhmm(a_arr)},
           "tram_b": {"dep_de_gaulle": hhmm(b_dep), "leon_blum": hhmm(b_times["Léon Blum"]), "clos_du_hameau": hhmm(b_times["Clos du Hameau"])},
           "transfer_waits_de_gaulle": waits}
    for key, t in (("rapide", fast), ("securite", safe)):
        out[key] = {"depart": hhmm(t["depart"]), "arrivee": hhmm_round(t["arrival"]), "duree_min": round(t["duration"]),
                    "attente_arret_min": round(t["wait_stop"]), "correspondance_min": round(t["transfer"]),
                    "attente_decouvert_min": round(t["exposed_wait"]), "safe_place_min": round(t.get("safe_place", 0)),
                    "descente": t["alight"], "marche_m": t["walk"]["length"], "marche_axes_principaux": t["walk"]["main_share"],
                    "rues": t["walk"]["streets"], "cout": round(t["cost"])}
    write_json(ANALYSES / "trajet_securite.json", out)
    (ANALYSES / "trajet_reseau.svg").write_text(svg_network(bm, stops_xy), encoding="utf-8")
    (ANALYSES / "trajet_derniers_metres.svg").write_text(svg_last_meters(adj, bm, stops_xy, fast_walk, safe_walk), encoding="utf-8")
    print(f"Tram A {hhmm(a_dep)} Parc Floral → {hhmm(a_arr)} De Gaulle ; tram B {hhmm(b_dep)} → Léon Blum {hhmm(b_times['Léon Blum'])}, Clos du Hameau {hhmm(b_times['Clos du Hameau'])}")
    for key in ("rapide", "securite"):
        r = out[key]
        print(f"  {key:9s} départ {r['depart']} arrivée {r['arrivee']} · attente à découvert {r['attente_decouvert_min']} min · "
              f"marche {r['marche_m']} m ({round(100 * r['marche_axes_principaux'])} % d'axes principaux) · coût {r['cout']}")
    print("  correspondances A → B à De Gaulle :", ", ".join(f"{a} → {b} ({m} min)" for a, b, m in waits))


if __name__ == "__main__":
    main()
