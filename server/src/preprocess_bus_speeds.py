"""
Preprocess bus probe GPS data → per-OSM-segment congestion index.

Input : /home/nkoei/chennai/raw_date_18th_16-10to16-40 .csv
Output: api/data/bus_probe_speeds.json
  { "<feature_id>": 0.72, ... }   (congestion float 0.0–1.0)

Method
------
1. Load OSM segment centroids in flat-earth XY metres.
2. Parse PEIS sentences: filter IGNON + valid fix + Chennai bbox.
3. Per-vehicle bus-stop dwell detection:
     Sort each vehicle's pings by timestamp.
     A run of consecutive pings with speed < DWELL_SPEED_KN lasting
     >= DWELL_MIN_S seconds is classified as "bus stop dwell" and excluded.
     Brief stops (<= DWELL_MIN_S) and slow creep in traffic are kept.
4. GPS noise filter: speed > MAX_SPEED_KN excluded.
5. Batch-match each remaining GPS point to nearest OSM centroid (numpy).
   Accept if distance <= MATCH_RADIUS_M.
6. Aggregate median speed (knots) per segment (min MIN_SAMPLES samples).
7. Map speed → congestion:
     congestion = 1 - speed_kmh / FREE_SPEED_KMH
     clamped to [0.05, 0.98]
   FREE_SPEED_KMH = 30  →  >=30 km/h = free, <=0 km/h = severe
"""

import csv, io, json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import numpy as np

DATA_DIR = Path(__file__).parent / "api" / "data"
CSV_PATH = Path("/home/nkoei/chennai/raw_date_18th_16-10to16-40 .csv")

# ─── flat-earth projection ───────────────────────────────────────
REF_LAT  = 13.04
COS_REF  = math.cos(math.radians(REF_LAT))
LAT_M    = 111_320.0
LON_M    = 111_320.0 * COS_REF

def to_xy(lat, lon):
    return lon * LON_M, lat * LAT_M

# ─── NMEA DDMM decode ────────────────────────────────────────────
def ddmm(s, hemi):
    v = float(s)
    d = int(v / 100)
    deg = d + (v - d * 100) / 60
    return -deg if hemi in ("S", "W") else deg

# ─── speed → congestion ──────────────────────────────────────────
FREE_KMH   = 30.0
KNOT_TO_KM = 1.852

def speed_to_cong(knots: float) -> float:
    kmh = knots * KNOT_TO_KM
    return round(max(0.05, min(0.98, 1.0 - kmh / FREE_KMH)), 3)

# ─── filters ─────────────────────────────────────────────────────
MATCH_RADIUS  = 150    # metres – centroid match threshold
BATCH         = 3000   # points per numpy batch
DWELL_SPEED_KN = 0.5   # knots – below this = candidate for bus stop (≈0.9 km/h)
DWELL_MIN_S    = 20    # seconds – sustained stop >= this → bus stop dwell
MAX_SPEED_KN   = 54    # knots – above this = GPS noise (≈100 km/h)
MIN_SAMPLES    = 2     # minimum pings per segment to compute median


def _parse_epoch(time_str: str, date_str: str) -> float:
    """Parse 'HH:MM:SS' + 'DD/MM/YYYY' → Unix epoch float."""
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M:%S").timestamp()
    except Exception:
        return 0.0


def _mark_dwell_pings(pings: list) -> list[bool]:
    """
    pings: list of (epoch, spd_kn)  sorted by epoch ascending
    Returns bool list: True = bus-stop dwell ping (exclude), False = keep.
    """
    n = len(pings)
    exclude = [False] * n

    i = 0
    while i < n:
        if pings[i][1] < DWELL_SPEED_KN:
            # Find the end of this low-speed run
            j = i + 1
            while j < n and pings[j][1] < DWELL_SPEED_KN:
                j += 1
            duration = pings[j - 1][0] - pings[i][0]
            if duration >= DWELL_MIN_S:
                for k in range(i, j):
                    exclude[k] = True
            i = j
        else:
            i += 1

    return exclude


def main():
    # ── 1. OSM segment centroids ─────────────────────────────────
    print("Loading OSM segments …")
    gj = json.loads((DATA_DIR / "chennai_roads.geojson").read_text())

    seg_ids, seg_cx, seg_cy = [], [], []
    for feat in gj["features"]:
        coords = feat["geometry"]["coordinates"]
        lon_c  = sum(c[0] for c in coords) / len(coords)
        lat_c  = sum(c[1] for c in coords) / len(coords)
        x, y   = to_xy(lat_c, lon_c)
        seg_ids.append(str(feat["id"]))
        seg_cx.append(x)
        seg_cy.append(y)

    seg_cx_np = np.array(seg_cx, dtype=np.float32)
    seg_cy_np = np.array(seg_cy, dtype=np.float32)
    print(f"  {len(seg_ids)} segments")

    # ── 2. Parse CSV, group by vehicle ───────────────────────────
    print("Parsing bus probe CSV …")
    with open(CSV_PATH, "rb") as f:
        content = f.read().replace(b"\x00", b"")

    # vehicle_pings: vid → list of (epoch, x, y, spd_kn)
    vehicle_pings: dict[str, list] = defaultdict(list)
    skipped = 0

    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
    for row in reader:
        p = row["gprmc"].strip('"').split(",")
        if len(p) < 16:
            continue
        if p[6] == "IGNOFF":
            continue
        if p[10] != "A":
            continue
        try:
            vid = p[5]
            lat = ddmm(p[11], p[12])
            lon = ddmm(p[13], p[14])
            spd = float(p[15])
            epoch = _parse_epoch(p[8], p[9])
        except Exception:
            skipped += 1
            continue
        if not (12.80 <= lat <= 13.25 and 79.90 <= lon <= 80.40):
            continue
        if spd > MAX_SPEED_KN:
            continue
        x, y = to_xy(lat, lon)
        vehicle_pings[vid].append((epoch, x, y, spd))

    n_vehicles = len(vehicle_pings)
    n_raw = sum(len(v) for v in vehicle_pings.values())
    print(f"  Vehicles: {n_vehicles:,}  raw IGNON pings: {n_raw:,}  (skipped: {skipped})")

    # ── 3. Bus-stop dwell filtering ───────────────────────────────
    print("Filtering bus-stop dwell pings …")
    pts_x, pts_y, pts_spd = [], [], []
    n_dwell = 0

    for vid, pings in vehicle_pings.items():
        pings.sort(key=lambda r: r[0])
        epoch_spd = [(r[0], r[3]) for r in pings]
        exclude   = _mark_dwell_pings(epoch_spd)
        for (ep, x, y, spd), ex in zip(pings, exclude):
            if ex:
                n_dwell += 1
            else:
                pts_x.append(x)
                pts_y.append(y)
                pts_spd.append(spd)

    total = len(pts_x)
    pct_dwell = 100 * n_dwell / n_raw if n_raw else 0
    print(f"  Dwell pings excluded: {n_dwell:,} ({pct_dwell:.1f}%)")
    print(f"  Remaining pings for matching: {total:,}")

    pts_x_np   = np.array(pts_x,   dtype=np.float32)
    pts_y_np   = np.array(pts_y,   dtype=np.float32)
    pts_spd_np = np.array(pts_spd, dtype=np.float32)

    # ── 4. Nearest-centroid matching ─────────────────────────────
    print("Matching GPS points to OSM segments …")
    speeds_by_seg: dict[str, list[float]] = defaultdict(list)

    for i in range(0, total, BATCH):
        px  = pts_x_np  [i:i+BATCH].reshape(-1, 1)
        py  = pts_y_np  [i:i+BATCH].reshape(-1, 1)
        spd = pts_spd_np[i:i+BATCH]

        dx = px - seg_cx_np.reshape(1, -1)
        dy = py - seg_cy_np.reshape(1, -1)
        d2 = dx*dx + dy*dy

        nearest  = np.argmin(d2, axis=1)
        min_dist = np.sqrt(d2[np.arange(len(nearest)), nearest])

        for j in range(len(nearest)):
            if min_dist[j] <= MATCH_RADIUS:
                speeds_by_seg[seg_ids[nearest[j]]].append(float(spd[j]))

        if (i // BATCH) % 50 == 0:
            print(f"  … {i+len(spd):,} / {total:,}")

    print(f"  Matched {len(speeds_by_seg)} / {len(seg_ids)} segments")

    # ── 5. Median speed → congestion (min MIN_SAMPLES) ───────────
    result: dict[str, float] = {}
    n_thin = 0
    for fid, spds in speeds_by_seg.items():
        if len(spds) < MIN_SAMPLES:
            n_thin += 1
            continue
        spds.sort()
        median_knots = spds[len(spds) // 2]
        result[fid]  = speed_to_cong(median_knots)

    print(f"  Segments dropped (< {MIN_SAMPLES} samples): {n_thin}")

    # ── 6. Stats ─────────────────────────────────────────────────
    vals = list(result.values())
    free     = sum(1 for v in vals if v < 0.33)
    moderate = sum(1 for v in vals if 0.33 <= v < 0.55)
    heavy    = sum(1 for v in vals if 0.55 <= v < 0.75)
    severe   = sum(1 for v in vals if v >= 0.75)
    print(f"\nCongestion distribution ({len(vals)} segments):")
    print(f"  free={free}  moderate={moderate}  heavy={heavy}  severe={severe}")
    print(f"  avg={sum(vals)/len(vals):.3f}  min={min(vals):.3f}  max={max(vals):.3f}")

    # ── 7. Write output ──────────────────────────────────────────
    out = DATA_DIR / "bus_probe_speeds.json"
    out.write_text(json.dumps(result, ensure_ascii=False))
    print(f"\nWrote {out}")
    pct = 100 * len(result) / len(seg_ids)
    print(f"Coverage: {len(result)} / {len(seg_ids)} segments ({pct:.1f}%)")


if __name__ == "__main__":
    main()
