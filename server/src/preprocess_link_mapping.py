"""
One-time preprocessing: assign each OSM segment to a schematic link and
compute its fraction (0.0–1.0) along that link.

Matches the 42-node / 64-corridor layout defined in SchematicMap.vue.
Node names are stored as display strings (same as Vue) for direct lookup.

Output: api/data/link_mapping.json   — {fid: {link_id, fraction}}
        api/data/schematic_links.json — link metadata
"""

import json, math
from pathlib import Path
from collections import Counter

DATA_DIR = Path(__file__).parent / "api" / "data"

# ── Real-world coordinates [lat, lon] keyed by Vue display name ────────────────
NODE_COORDS = {
    "Royapuram":       (13.1105, 80.2940),
    "Perambur":        (13.1162, 80.2456),
    "Avadi":           (13.1066, 80.0983),
    "Ambattur":        (13.1143, 80.1480),
    "Egmore":          (13.0780, 80.2621),
    "Anna Nagar":      (13.0850, 80.2101),
    "Chennai Central": (13.0827, 80.2757),
    "Koyambedu":       (13.0694, 80.1948),
    "Nungambakkam":    (13.0601, 80.2405),
    "Vadapalani":      (13.0530, 80.2115),
    "Mylapore":        (13.0335, 80.2676),
    "T. Nagar":        (13.0400, 80.2330),
    "Poonamallee":     (13.0487, 80.0964),
    "Porur":           (13.0321, 80.1588),
    "Saidapet":        (13.0143, 80.2235),
    "Kathipara":       (13.0141, 80.2003),
    "Guindy":          (13.0077, 80.2206),
    "Madhya Kailash":  (13.0102, 80.2476),
    "Adyar":           (13.0019, 80.2564),
    "Besant Nagar":    (12.9991, 80.2701),
    "Tidel Park":      (12.9900, 80.2472),
    "Velachery":       (12.9784, 80.2199),
    "Taramani":        (12.9758, 80.2423),
    "Thiruvanmiyur":   (12.9827, 80.2570),
    "Perungudi":       (12.9670, 80.2436),
    "Pallavaram":      (12.9680, 80.1509),
    "Chromepet":       (12.9520, 80.1409),
    "Pallikaranai":    (12.9389, 80.2133),
    "Tambaram":        (12.9253, 80.1217),
    "Thoraipakkam":    (12.9307, 80.2348),
    "Sholinganallur":  (12.9010, 80.2270),
    "SRM Nagar":       (12.8826, 80.2283),
    # new nodes
    "Ennore":          (13.1306, 80.3170),
    "Madhavaram":      (13.1480, 80.2500),
    "Redhills":        (13.1910, 80.1810),
    "Mogappair":       (13.0950, 80.1750),
    "Maduravoyal":     (13.0610, 80.1530),
    "Teynampet":       (13.0500, 80.2490),
    "Medavakkam":      (12.9420, 80.2000),
    "Vandalur":        (12.9100, 80.0810),
    "Kelambakkam":     (12.8100, 80.2250),
    "Guduvanchery":    (12.8500, 80.0840),
}

# ── 64 schematic links — exactly matches SchematicMap.vue corridors ────────────
LINK_DEFS = [
    ("l01",  "Avadi",           "Ambattur"),
    ("l02",  "Ambattur",        "Anna Nagar"),
    ("l03",  "Anna Nagar",      "Koyambedu"),
    ("l04",  "Koyambedu",       "Chennai Central"),
    ("l05",  "Poonamallee",     "Porur"),
    ("l06",  "Porur",           "Koyambedu"),
    ("l07",  "Porur",           "Kathipara"),
    ("l08",  "Kathipara",       "Koyambedu"),
    ("l09",  "Kathipara",       "Guindy"),
    ("l10",  "Guindy",          "Velachery"),
    ("l11",  "Guindy",          "Madhya Kailash"),
    ("l12",  "Madhya Kailash",  "Adyar"),
    ("l13",  "Chennai Central", "Madhya Kailash"),
    ("l14",  "Madhya Kailash",  "Tidel Park"),
    ("l15",  "Tidel Park",      "Taramani"),
    ("l16",  "Taramani",        "Velachery"),
    ("l17",  "Taramani",        "Thoraipakkam"),
    ("l18",  "Adyar",           "Perungudi"),
    ("l19",  "Sholinganallur",  "SRM Nagar"),
    ("l20",  "Velachery",       "Chromepet"),
    ("l21",  "Chromepet",       "Pallavaram"),
    ("l22",  "Pallavaram",      "Tambaram"),
    ("l23",  "Tambaram",        "Chromepet"),
    ("l24",  "Royapuram",       "Chennai Central"),
    ("l25",  "Royapuram",       "Perambur"),
    ("l26",  "Perambur",        "Egmore"),
    ("l27",  "Perambur",        "Ambattur"),
    ("l28",  "Chennai Central", "Egmore"),
    ("l29",  "Chennai Central", "Nungambakkam"),
    ("l30",  "Nungambakkam",    "T. Nagar"),
    ("l31",  "Koyambedu",       "Vadapalani"),
    ("l32",  "Vadapalani",      "T. Nagar"),
    ("l33",  "T. Nagar",        "Saidapet"),
    ("l34",  "Saidapet",        "Guindy"),
    ("l35",  "Saidapet",        "Kathipara"),
    ("l36",  "Chennai Central", "Mylapore"),
    ("l37",  "Mylapore",        "Adyar"),
    ("l38",  "Adyar",           "Besant Nagar"),
    ("l39",  "Besant Nagar",    "Thiruvanmiyur"),
    ("l40",  "Thiruvanmiyur",   "Thoraipakkam"),
    ("l41",  "Perungudi",       "Thoraipakkam"),
    ("l42",  "Thoraipakkam",    "Sholinganallur"),
    ("l43",  "Pallikaranai",    "Thoraipakkam"),
    ("l44",  "Velachery",       "Pallikaranai"),
    ("l45",  "Ennore",          "Royapuram"),
    ("l46",  "Madhavaram",      "Perambur"),
    ("l47",  "Madhavaram",      "Ennore"),
    ("l48",  "Redhills",        "Ambattur"),
    ("l49",  "Redhills",        "Madhavaram"),
    ("l50",  "Mogappair",       "Ambattur"),
    ("l51",  "Mogappair",       "Anna Nagar"),
    ("l52",  "Maduravoyal",     "Poonamallee"),
    ("l53",  "Maduravoyal",     "Koyambedu"),
    ("l54",  "Maduravoyal",     "Porur"),
    ("l55",  "Teynampet",       "T. Nagar"),
    ("l56",  "Teynampet",       "Saidapet"),
    ("l57",  "Teynampet",       "Nungambakkam"),
    ("l58",  "Medavakkam",      "Velachery"),
    ("l59",  "Medavakkam",      "Pallikaranai"),
    ("l60",  "Vandalur",        "Tambaram"),
    ("l61",  "Vandalur",        "Guduvanchery"),
    ("l62",  "Kelambakkam",     "SRM Nagar"),
    ("l63",  "Kelambakkam",     "Guduvanchery"),
    ("l64",  "Guduvanchery",    "Tambaram"),
]

SEG_RESOLUTION_M = 100   # 1バケット = 100m（旧300mから細粒化）
CORRIDOR_M       = 600   # OSMセグをリンクに割り当てる最大垂直距離


def haversine_m(a_lat, a_lon, b_lat, b_lon):
    R = 6_371_000
    la1, lo1 = math.radians(a_lat), math.radians(a_lon)
    la2, lo2 = math.radians(b_lat), math.radians(b_lon)
    dlat, dlon = la2 - la1, lo2 - lo1
    h = math.sin(dlat/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))


REF_LAT = 13.04
COS_REF = math.cos(math.radians(REF_LAT))
LAT_M   = 111_320.0
LON_M   = 111_320.0 * COS_REF

def to_xy(lat, lon):
    return (lon * LON_M, lat * LAT_M)

def seg_project(px, py, ax, ay, bx, by):
    abx, aby = bx - ax, by - ay
    ab2 = abx*abx + aby*aby
    if ab2 == 0:
        dx, dy = px - ax, py - ay
        return 0.0, math.sqrt(dx*dx + dy*dy)
    t = max(0.0, min(1.0, ((px-ax)*abx + (py-ay)*aby) / ab2))
    cx, cy = ax + t*abx, ay + t*aby
    dx, dy = px - cx, py - cy
    return t, math.sqrt(dx*dx + dy*dy)


def main():
    print("Loading GeoJSON …")
    gj = json.loads((DATA_DIR / "chennai_roads.geojson").read_text())

    links_xy     = []
    link_lengths = {}
    for lid, frm, to in LINK_DEFS:
        la_a, lo_a = NODE_COORDS[frm]
        la_b, lo_b = NODE_COORDS[to]
        ax, ay = to_xy(la_a, lo_a)
        bx, by = to_xy(la_b, lo_b)
        length_m  = haversine_m(la_a, lo_a, la_b, lo_b)
        seg_count = max(3, math.ceil(length_m / SEG_RESOLUTION_M))
        links_xy.append((lid, ax, ay, bx, by))
        link_lengths[lid] = {
            "length_m":  round(length_m),
            "seg_count": seg_count,
            "from": frm,
            "to":   to,
        }

    print(f"Processing {len(gj['features'])} OSM features …")

    mapping  = {}
    assigned = 0
    skipped  = 0

    for feat in gj["features"]:
        coords = feat["geometry"]["coordinates"]
        fid    = str(feat["id"])

        cx_sum = cy_sum = 0.0
        for lon, lat in coords:
            x, y = to_xy(lat, lon)
            cx_sum += x; cy_sum += y
        n  = len(coords)
        cx, cy = cx_sum / n, cy_sum / n

        best_lid  = None
        best_t    = None
        best_dist = CORRIDOR_M

        for lid, ax, ay, bx, by in links_xy:
            t, d = seg_project(cx, cy, ax, ay, bx, by)
            if d < best_dist:
                best_dist = d; best_lid = lid; best_t = t

        if best_lid is not None:
            mapping[fid] = {"link_id": best_lid, "fraction": round(best_t, 4)}
            assigned += 1
        else:
            skipped += 1

    print(f"Assigned : {assigned}")
    print(f"Skipped  : {skipped}  (outside {CORRIDOR_M}m corridor)")

    counts = Counter(v["link_id"] for v in mapping.values())
    total_buckets = sum(v["seg_count"] for v in link_lengths.values())
    print(f"\nTotal buckets: {total_buckets}  (avg {total_buckets/len(LINK_DEFS):.0f}/link)")
    print(f"Avg OSM segs/bucket: {assigned/total_buckets:.1f}")
    print()
    print("Link ID | from → to | length | buckets | segs")
    for lid, frm, to in LINK_DEFS:
        info = link_lengths[lid]
        c    = counts.get(lid, 0)
        eff  = info['length_m'] / info['seg_count']
        print(f"  {lid:4s}  {frm[:14]:14s} → {to[:14]:14s}  "
              f"{info['length_m']:6d}m  {info['seg_count']:4d}bkt  {c:4d}segs  ({eff:.0f}m/bkt)")

    (DATA_DIR / "link_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False))
    (DATA_DIR / "schematic_links.json").write_text(
        json.dumps(link_lengths, ensure_ascii=False, indent=2))
    print(f"\nWrote link_mapping.json  ({len(mapping)} entries)")
    print(f"Wrote schematic_links.json  ({len(link_lengths)} links)")


if __name__ == "__main__":
    main()
