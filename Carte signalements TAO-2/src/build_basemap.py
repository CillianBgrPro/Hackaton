"""Construit le fond de carte vectoriel compact (build/basemap.json) à partir de cache/.

Les géométries sont simplifiées puis encodées en « polyline » (précision 1e-5,
environ 1 m) pour que le fond complet tienne dans la page (≈ 400 Ko).
"""
import collections
import csv
import json
import re
from pathlib import Path

from shapely import force_2d
from shapely.geometry import LineString, Polygon, box, shape
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parents[1]
CACHE, BUILD = ROOT / "cache", ROOT / "build"
GTFS = CACHE / "gtfs"
BBOX = box(1.76, 47.755, 2.115, 48.02)


# ---------- encodage polyline (format Google, précision 5) ----------
def _enc_num(v):
    v = ~(v << 1) if v < 0 else (v << 1)
    out = ""
    while v >= 0x20:
        out += chr((0x20 | (v & 0x1F)) + 63)
        v >>= 5
    return out + chr(v + 63)


def encode(coords):
    """coords : suite de (lon, lat) -> chaîne encodée de (lat, lon)."""
    out, plat, plon = "", 0, 0
    for x, y in coords:
        lat, lon = round(y * 1e5), round(x * 1e5)
        out += _enc_num(lat - plat) + _enc_num(lon - plon)
        plat, plon = lat, lon
    return out


def lines_of(g):
    if g.is_empty:
        return []
    if isinstance(g, LineString):
        return [g]
    return [l for part in getattr(g, "geoms", []) for l in lines_of(part)]


def polys_of(g):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    return [p for part in getattr(g, "geoms", []) for p in polys_of(part)]


def enc_lines(geoms, tol):
    merged = linemerge([l for g in geoms for l in lines_of(g)])
    return [encode([c[:2] for c in l.coords]) for l in lines_of(merged.simplify(tol, preserve_topology=False))
            if len(l.coords) >= 2]


def enc_polys(geoms, tol, minarea=0.0):
    out = []
    for p in polys_of(unary_union(geoms).simplify(tol)):
        if p.area < minarea:
            continue
        holes = [encode(r.coords) for r in p.interiors if Polygon(r).area >= minarea / 4]
        out.append([encode(p.exterior.coords)] + holes)
    return out


def load(name):
    return json.loads((CACHE / f"{name}.json").read_text())["features"]


def read_csv(name):
    with open(GTFS / name, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def line_sort_key(l):
    if l in ("A", "B"):
        return (0, 0, l)
    if l.isdigit():
        return (1, int(l), l)
    return (2, 0, l)


def main():
    BUILD.mkdir(exist_ok=True)
    B = {}

    # Communes et contour de la Métropole
    communes = load("communes")
    B["communes"] = []
    for f in communes:
        g = shape(f["geometry"])
        rp = g.representative_point()
        B["communes"].append({"n": f["properties"]["nom"], "p": f["properties"].get("population"),
                              "r": enc_polys([g], 0.00015), "c": [round(rp.y, 5), round(rp.x, 5)]})
    B["metro"] = enc_polys([unary_union([shape(f["geometry"]) for f in communes])], 0.00015)

    # Eau : cours d'eau et canaux, plus les grands plans d'eau
    water = [force_2d(shape(f["geometry"])) for f in load("water")
             if f["properties"]["nature"] in ("Ecoulement naturel", "Canal") or shape(f["geometry"]).area > 2.5e-6]
    B["water"] = enc_polys([w.intersection(BBOX) for w in water], 0.00006, minarea=2e-7)

    # Routes par classe d'importance
    roads = collections.defaultdict(list)
    for f in load("roads_main"):
        imp, nat = f["properties"]["importance"], f["properties"]["nature"] or ""
        key = "r1" if imp in ("1", "2") or "Type autoroutier" in nat else ("r3" if imp == "3" else "r4")
        roads[key].append(force_2d(shape(f["geometry"])))
    roads["r5"] = [force_2d(shape(f["geometry"])) for f in load("roads_local")]
    B["r1"] = enc_lines(roads["r1"], 0.00005)
    B["r3"] = enc_lines(roads["r3"], 0.00005)
    B["r4"] = enc_lines(roads["r4"], 0.00004)
    B["r5"] = enc_lines(roads["r5"], 0.00004)
    B["rail"] = enc_lines([force_2d(shape(f["geometry"])) for f in load("rail")
                           if f["properties"]["nature"] == "Voie ferrée principale"], 0.00005)

    # Lignes TAO (tracés GTFS)
    routes = {r["route_id"]: r for r in read_csv("routes.txt")}
    pts = collections.defaultdict(list)
    for r in read_csv("shapes.txt"):
        pts[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
    shapes = {k: LineString([(x, y) for _, x, y in sorted(v)]) for k, v in pts.items()}
    trips = read_csv("trips.txt")
    route_shapes = collections.defaultdict(set)
    for t in trips:
        route_shapes[t["route_id"]].add(t["shape_id"])
    B["lines"] = []
    for rid, sids in route_shapes.items():
        r = routes[rid]
        if r["route_short_name"] in ("LA", "LB"):   # doublons « bus » des lignes de tram
            continue
        geom = unary_union([shapes[s] for s in sids if s in shapes])
        B["lines"].append({"id": r["route_short_name"], "name": r["route_long_name"].title(),
                           "t": int(r["route_type"]), "col": "#" + r["route_color"], "g": enc_lines([geom], 0.00004)})
    B["lines"].sort(key=lambda l: (l["t"] != 0, line_sort_key(l["id"])))

    # Lignes desservant chaque arrêt (via stop_times)
    trip_line = {t["trip_id"]: {"LA": "A", "LB": "B"}.get(routes[t["route_id"]]["route_short_name"],
                                                         routes[t["route_id"]]["route_short_name"]) for t in trips}
    stop_lines = collections.defaultdict(set)
    with open(GTFS / "stop_times.txt", encoding="utf-8-sig") as fh:
        header = fh.readline().strip().split(",")
        i_trip, i_stop = header.index("trip_id"), header.index("stop_id")
        for row in fh:
            parts = row.rstrip("\n").split(",")
            line = trip_line.get(parts[i_trip])
            if line:
                stop_lines[parts[i_stop]].add(line)

    # Arrêts : quais de même nom regroupés quand ils sont proches (< ~300 m)
    base_name = lambda n: re.sub(r"\s+-\s+Quai\s+\w+$", "", n).strip()
    groups = collections.defaultdict(list)   # nom -> liste de groupes [(lon, lat, stop_id), ...]
    for s in read_csv("stops.txt"):
        if s["location_type"] != "0":
            continue
        p = (float(s["stop_lon"]), float(s["stop_lat"]), s["stop_id"])
        for grp in groups[base_name(s["stop_name"])]:
            if abs(grp[0][0] - p[0]) < 0.004 and abs(grp[0][1] - p[1]) < 0.003:
                grp.append(p)
                break
        else:
            groups[base_name(s["stop_name"])].append([p])
    B["stops"] = []
    for name, grps in groups.items():
        for grp in grps:
            lines = sorted(set().union(*(stop_lines.get(p[2], set()) for p in grp)), key=line_sort_key)
            x = sum(p[0] for p in grp) / len(grp)
            y = sum(p[1] for p in grp) / len(grp)
            B["stops"].append({"n": name, "c": [round(y, 5), round(x, 5)],
                               "tram": any(l in ("A", "B") for l in lines), "l": lines})

    js = json.dumps(B, ensure_ascii=False, separators=(",", ":"))
    (BUILD / "basemap.json").write_text(js, encoding="utf-8")
    print(f"Fond de carte : {len(js) / 1024:.0f} Ko, {len(B['lines'])} lignes, {len(B['stops'])} arrêts "
          f"(dont {sum(s['tram'] for s in B['stops'])} de tram)")


if __name__ == "__main__":
    main()
