"""
Preprocess bus probe data → travel-time speeds per schematic link per 2-minute bin.

Extends preprocess_link_travel_time.py by assigning each traversal to a time bin
based on its start epoch, enabling TT-method REPLAY snapshots.

Output: api/data/bus_link_tt_timeline.json
{
  "bin_minutes": 2,
  "start_ist": "16:10",
  "end_ist":   "16:38",
  "snapshots": [
    {
      "index": 0,
      "time_ist": "16:10",
      "links": { "l01": {"cong": 0.42, "n": 5}, ... }
    },
    ...
  ]
}
"""

import csv, io, json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

DATA_DIR = Path(__file__).parent / "api" / "data"
CSV_PATH = Path("/home/nkoei/chennai/raw_date_18th_16-10to16-40 .csv")

BIN_MINUTES  = 2
START_UTC_H, START_UTC_M = 10, 40

# ─── flat-earth projection ───────────────────────────────────────
REF_LAT  = 13.04
COS_REF  = math.cos(math.radians(REF_LAT))
LAT_M    = 111_320.0
LON_M    = 111_320.0 * COS_REF

def to_xy(lat, lon):
    return lon * LON_M, lat * LAT_M

def ddmm(s, hemi):
    v = float(s)
    d = int(v / 100)
    deg = d + (v - d * 100) / 60
    return -deg if hemi in ("S", "W") else deg

FREE_KMH     = 30.0
MATCH_RADIUS = 150    # metres
BATCH        = 5000
MIN_PINGS    = 2      # minimum pings on a link per traversal
MAX_GAP_S    = 25     # break if next ping > 25s away
MIN_DIST_M   = 10     # ignore traversals < 10m displacement

def speed_ms_to_cong(v_ms: float) -> float:
    kmh = v_ms * 3.6
    return round(max(0.05, min(0.98, 1.0 - kmh / FREE_KMH)), 3)

def bin_to_ist(idx: int) -> str:
    total_m = (START_UTC_H * 60 + START_UTC_M) + idx * BIN_MINUTES + 5 * 60 + 30
    return f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"


def main():
    start_epoch = datetime(2026, 3, 18, START_UTC_H, START_UTC_M, 0,
                           tzinfo=timezone.utc).timestamp()

    # ── 1. OSM segment centroids ─────────────────────────────────
    print("Loading OSM segments …")
    gj = json.loads((DATA_DIR / "chennai_roads.geojson").read_text())
    seg_ids, seg_cx, seg_cy = [], [], []
    for feat in gj["features"]:
        coords = feat["geometry"]["coordinates"]
        lon_c = sum(c[0] for c in coords) / len(coords)
        lat_c = sum(c[1] for c in coords) / len(coords)
        x, y  = to_xy(lat_c, lon_c)
        seg_ids.append(str(feat["id"]))
        seg_cx.append(x)
        seg_cy.append(y)
    seg_cx_np = np.array(seg_cx, dtype=np.float32)
    seg_cy_np = np.array(seg_cy, dtype=np.float32)
    print(f"  {len(seg_ids)} segments")

    # ── 2. Link mapping ──────────────────────────────────────────
    link_mapping = json.loads((DATA_DIR / "link_mapping.json").read_text())
    seg_to_link  = {fid: info["link_id"] for fid, info in link_mapping.items()}
    schematic_links = json.loads((DATA_DIR / "schematic_links.json").read_text())
    print(f"  {len(seg_to_link)} segments assigned to schematic links")

    # ── 3. Parse CSV ─────────────────────────────────────────────
    print("Parsing bus probe CSV …")
    with open(CSV_PATH, "rb") as f:
        content = f.read().replace(b"\x00", b"")

    records = []   # (vid, epoch, x, y)
    reader  = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
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
            dt  = datetime.fromisoformat(row["createddate"].replace("Z", "+00:00"))
        except Exception:
            continue
        if not (12.80 <= lat <= 13.25 and 79.90 <= lon <= 80.40):
            continue
        x, y = to_xy(lat, lon)
        records.append((vid, dt.timestamp(), x, y))

    total = len(records)
    print(f"  Valid IGNON pings: {total:,}")

    # ── 4. Batch nearest-centroid matching ───────────────────────
    print("Matching pings to OSM segments …")
    pts_x  = np.array([r[2] for r in records], dtype=np.float32)
    pts_y  = np.array([r[3] for r in records], dtype=np.float32)
    nearest_seg  = np.full(total, -1, dtype=np.int32)
    nearest_dist = np.full(total, np.inf, dtype=np.float32)

    for i in range(0, total, BATCH):
        px = pts_x[i:i+BATCH].reshape(-1, 1)
        py = pts_y[i:i+BATCH].reshape(-1, 1)
        dx = px - seg_cx_np.reshape(1, -1)
        dy = py - seg_cy_np.reshape(1, -1)
        d2 = dx*dx + dy*dy
        nn  = np.argmin(d2, axis=1)
        nd  = np.sqrt(d2[np.arange(len(nn)), nn])
        nearest_seg [i:i+BATCH] = nn
        nearest_dist[i:i+BATCH] = nd
        if (i // BATCH) % 20 == 0:
            print(f"  … {i+len(nn):,}/{total:,}")

    ping_link = []
    for i in range(total):
        if nearest_dist[i] <= MATCH_RADIUS:
            fid = seg_ids[nearest_seg[i]]
            lid = seg_to_link.get(fid)
        else:
            lid = None
        ping_link.append(lid)

    matched = sum(1 for l in ping_link if l is not None)
    print(f"  Matched to schematic links: {matched:,}/{total:,} ({100*matched/total:.1f}%)")

    # ── 5. Group by vehicle, sort by time ────────────────────────
    print("Grouping by vehicle …")
    veh_pings: dict[str, list] = defaultdict(list)
    for i, (vid, epoch, x, y) in enumerate(records):
        veh_pings[vid].append((epoch, x, y, ping_link[i]))
    for vid in veh_pings:
        veh_pings[vid].sort(key=lambda r: r[0])

    # ── 6. Extract traversals with bin assignment ─────────────────
    print("Extracting traversals …")
    # traversals_by_bin[bin_idx][link_id] = [speed_ms, ...]
    traversals_by_bin: list[dict] = [defaultdict(list) for _ in range(20)]

    n_trav_total = 0
    for vid, pings in veh_pings.items():
        trav_link  = None
        trav_start = 0.0
        trav_dist  = 0.0
        trav_pings = 0
        prev_epoch, prev_x, prev_y = None, None, None

        for epoch, x, y, lid in pings:
            gap = (epoch - prev_epoch) if prev_epoch is not None else 0.0

            if lid != trav_link or gap > MAX_GAP_S:
                # Close current traversal
                if trav_link is not None and trav_pings >= MIN_PINGS and trav_dist >= MIN_DIST_M:
                    elapsed = prev_epoch - trav_start
                    if elapsed > 0:
                        speed_ms = trav_dist / elapsed
                        offset_s = trav_start - start_epoch
                        if offset_s >= 0:
                            bin_idx = int(offset_s // (BIN_MINUTES * 60))
                            if bin_idx < len(traversals_by_bin):
                                traversals_by_bin[bin_idx][trav_link].append(speed_ms)
                                n_trav_total += 1
                # Start new traversal
                trav_link  = lid
                trav_start = epoch
                trav_dist  = 0.0
                trav_pings = 1
            else:
                if prev_x is not None:
                    trav_dist += math.sqrt((x - prev_x)**2 + (y - prev_y)**2)
                trav_pings += 1

            prev_epoch, prev_x, prev_y = epoch, x, y

        # Close final traversal
        if trav_link is not None and trav_pings >= MIN_PINGS and trav_dist >= MIN_DIST_M:
            elapsed = prev_epoch - trav_start
            if elapsed > 0:
                speed_ms = trav_dist / elapsed
                offset_s = trav_start - start_epoch
                if offset_s >= 0:
                    bin_idx = int(offset_s // (BIN_MINUTES * 60))
                    if bin_idx < len(traversals_by_bin):
                        traversals_by_bin[bin_idx][trav_link].append(speed_ms)
                        n_trav_total += 1

    print(f"  Total traversals assigned to bins: {n_trav_total:,}")

    # ── 7. Compute per-bin per-link TT congestion ─────────────────
    # Determine actual number of bins used
    n_bins = 15  # 16:10–16:38, 15 × 2-min bins
    snapshots = []
    for idx in range(n_bins):
        link_data: dict[str, dict] = {}
        for lid in traversals_by_bin[idx]:
            speeds = sorted(traversals_by_bin[idx][lid])
            if not speeds:
                continue
            median_ms = speeds[len(speeds) // 2]
            link_data[lid] = {
                "cong": speed_ms_to_cong(median_ms),
                "n":    len(speeds),
            }
        snapshots.append({
            "index":    idx,
            "time_ist": bin_to_ist(idx),
            "links":    link_data,
        })
        links_covered = len(link_data)
        total_travs   = sum(v["n"] for v in link_data.values())
        print(f"  bin {idx:2d} ({bin_to_ist(idx)} IST): {links_covered} links, {total_travs} traversals")

    # ── 8. Summary ───────────────────────────────────────────────
    all_cong = [v["cong"] for s in snapshots for v in s["links"].values()]
    if all_cong:
        print(f"\nTT timeline avg_cong: {sum(all_cong)/len(all_cong):.3f}  "
              f"min={min(all_cong):.3f}  max={max(all_cong):.3f}")

    # ── 9. Save ───────────────────────────────────────────────────
    out = {
        "bin_minutes": BIN_MINUTES,
        "start_ist":   bin_to_ist(0),
        "end_ist":     bin_to_ist(n_bins - 1),
        "snapshots":   snapshots,
    }
    out_path = DATA_DIR / "bus_link_tt_timeline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
