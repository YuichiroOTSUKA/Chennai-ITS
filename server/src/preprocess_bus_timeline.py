"""
Preprocess bus probe data into temporal snapshots (2-minute bins).
Applies the same bus-stop dwell filter as preprocess_bus_speeds.py.

Output: api/data/bus_probe_timeline.json
  {
    "bin_minutes": 2,
    "start_ist": "16:10",
    "end_ist":   "16:38",
    "snapshots": [
      {"index":0, "time_ist":"16:10", "segments":{"<fid>": 0.72, ...}},
      ...
    ]
  }

Data covers 2026-03-18 16:10–16:40 IST (10:40–11:10 UTC).
"""

import csv, io, json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

DATA_DIR = Path(__file__).parent / "api" / "data"
CSV_PATH = Path("/home/nkoei/chennai/raw_date_18th_16-10to16-40 .csv")

BIN_MINUTES = 2

# UTC start of data window
START_UTC_H, START_UTC_M = 10, 40

# ─── flat-earth projection ───────────────────────────────────────
REF_LAT = 13.04
COS_REF = math.cos(math.radians(REF_LAT))
LAT_M   = 111_320.0
LON_M   = 111_320.0 * COS_REF

def to_xy(lat, lon):
    return lon * LON_M, lat * LAT_M

def ddmm(s, hemi):
    v = float(s)
    d = int(v / 100)
    deg = d + (v - d * 100) / 60
    return -deg if hemi in ("S", "W") else deg

FREE_KMH      = 30.0
KNOT_TO_KM    = 1.852
MATCH_RADIUS  = 150     # metres
BATCH         = 3000

DWELL_SPEED_KN = 0.5   # knots – below this = bus-stop candidate
DWELL_MIN_S    = 20    # seconds – sustained stop >= this → exclude
MAX_SPEED_KN   = 54    # ≈100 km/h noise filter

def speed_to_cong(knots: float) -> float:
    kmh = knots * KNOT_TO_KM
    return round(max(0.05, min(0.98, 1.0 - kmh / FREE_KMH)), 3)

def bin_to_ist(idx: int) -> str:
    total_m = (START_UTC_H * 60 + START_UTC_M) + idx * BIN_MINUTES + 5 * 60 + 30
    return f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"


def _mark_dwell_pings(pings: list) -> list:
    """
    pings: [(epoch, spd_kn)] sorted ascending.
    Returns bool list: True = bus-stop dwell (exclude).
    """
    n = len(pings)
    exclude = [False] * n
    i = 0
    while i < n:
        if pings[i][1] < DWELL_SPEED_KN:
            j = i + 1
            while j < n and pings[j][1] < DWELL_SPEED_KN:
                j += 1
            if (pings[j - 1][0] - pings[i][0]) >= DWELL_MIN_S:
                for k in range(i, j):
                    exclude[k] = True
            i = j
        else:
            i += 1
    return exclude


def main():
    start_epoch = datetime(2026, 3, 18, START_UTC_H, START_UTC_M, 0,
                           tzinfo=timezone.utc).timestamp()

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

    vehicle_pings: dict[str, list] = defaultdict(list)
    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
    for row in reader:
        p = row["gprmc"].strip('"').split(",")
        if len(p) < 16:
            continue
        if p[6] == "IGNOFF" or p[10] != "A":
            continue
        try:
            vid = p[5]
            lat = ddmm(p[11], p[12])
            lon = ddmm(p[13], p[14])
            spd = float(p[15])
            dt  = datetime.fromisoformat(row["createddate"].replace("Z", "+00:00"))
        except Exception:
            continue
        if not (12.80 <= lat <= 13.25 and 79.90 <= lon <= 80.40):
            continue
        if spd > MAX_SPEED_KN:
            continue
        epoch = dt.timestamp()
        x, y  = to_xy(lat, lon)
        vehicle_pings[vid].append((epoch, x, y, spd))

    n_veh = len(vehicle_pings)
    n_raw = sum(len(v) for v in vehicle_pings.values())
    print(f"  Vehicles: {n_veh:,}  raw IGNON pings: {n_raw:,}")

    # ── 3. Apply dwell filter per vehicle ────────────────────────
    print("Applying bus-stop dwell filter …")
    pts_x, pts_y, pts_spd, pts_bin = [], [], [], []
    n_dwell = 0

    for vid, pings in vehicle_pings.items():
        pings.sort(key=lambda r: r[0])
        epoch_spd = [(r[0], r[3]) for r in pings]
        exclude   = _mark_dwell_pings(epoch_spd)
        for (epoch, x, y, spd), ex in zip(pings, exclude):
            if ex:
                n_dwell += 1
            else:
                offset_sec = epoch - start_epoch
                if offset_sec < 0:
                    continue
                bin_idx = int(offset_sec // (BIN_MINUTES * 60))
                pts_x.append(x)
                pts_y.append(y)
                pts_spd.append(spd)
                pts_bin.append(bin_idx)

    total = len(pts_x)
    print(f"  Dwell excluded: {n_dwell:,} ({100*n_dwell/n_raw:.1f}%)")
    print(f"  Remaining for matching: {total:,}")

    pts_x_np   = np.array(pts_x,   dtype=np.float32)
    pts_y_np   = np.array(pts_y,   dtype=np.float32)
    pts_spd_np = np.array(pts_spd, dtype=np.float32)
    pts_bin_np = np.array(pts_bin, dtype=np.int32)

    n_bins = int(pts_bin_np.max()) + 1 if len(pts_bin_np) else 0

    # ── 4. Nearest-centroid matching (batched) ───────────────────
    print("Matching GPS points to OSM segments …")
    bins_data: list[dict] = [defaultdict(list) for _ in range(n_bins)]

    for i in range(0, total, BATCH):
        px  = pts_x_np  [i:i+BATCH].reshape(-1, 1)
        py  = pts_y_np  [i:i+BATCH].reshape(-1, 1)
        spd = pts_spd_np[i:i+BATCH]
        bi  = pts_bin_np[i:i+BATCH]

        dx = px - seg_cx_np.reshape(1, -1)
        dy = py - seg_cy_np.reshape(1, -1)
        d2 = dx*dx + dy*dy

        nearest  = np.argmin(d2, axis=1)
        min_dist = np.sqrt(d2[np.arange(len(nearest)), nearest])

        for j in range(len(nearest)):
            if min_dist[j] <= MATCH_RADIUS:
                b = int(bi[j])
                if b < n_bins:
                    bins_data[b][seg_ids[nearest[j]]].append(float(spd[j]))

        if (i // BATCH) % 50 == 0:
            print(f"  … {i+len(spd):,}/{total:,}")

    # ── 5. Compute congestion per bin per segment ─────────────────
    print("Computing congestion per snapshot …")
    snapshots = []
    for idx in range(n_bins):
        seg_map = {}
        for fid, spds in bins_data[idx].items():
            spds.sort()
            median_k = spds[len(spds) // 2]
            seg_map[fid] = speed_to_cong(median_k)
        snapshots.append({
            "index":    idx,
            "time_ist": bin_to_ist(idx),
            "segments": seg_map,
        })
        print(f"  bin {idx:2d} ({bin_to_ist(idx)} IST): {len(seg_map)} segments")

    # ── 6. Save ───────────────────────────────────────────────────
    out = {
        "bin_minutes": BIN_MINUTES,
        "start_ist":   bin_to_ist(0),
        "end_ist":     bin_to_ist(n_bins - 1),
        "snapshots":   snapshots,
    }
    out_path = DATA_DIR / "bus_probe_timeline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False))
    print(f"\nWrote {out_path}")
    print(f"Snapshots: {n_bins}  ({bin_to_ist(0)} – {bin_to_ist(n_bins-1)} IST)")


if __name__ == "__main__":
    main()
