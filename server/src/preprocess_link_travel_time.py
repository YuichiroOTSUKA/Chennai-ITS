"""
Preprocess bus probe data → travel-time-based speed per schematic link.

Method:
  For each bus vehicle, track sequences of GPS pings on the same schematic link.
  Traversal speed = accumulated XY displacement / elapsed time  [m/s]
  This is the space-mean speed, vs the time-mean speed from instantaneous GPS field.

Output: api/data/bus_link_travel_speeds.json
  { "l01": 0.42, ... }   (congestion float 0.0–1.0, keyed by schematic link id)
"""

import csv, io, json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

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

def ddmm(s, hemi):
    v = float(s)
    d = int(v / 100)
    deg = d + (v - d * 100) / 60
    return -deg if hemi in ("S", "W") else deg

FREE_KMH     = 30.0
MATCH_RADIUS = 150    # metres
BATCH        = 5000
MIN_PINGS    = 2      # minimum pings on a link to count as a traversal
MAX_GAP_S    = 25     # break traversal if next ping is >25s away (missed >2 pings)
MIN_DIST_M   = 10     # ignore traversals with <10m displacement (stopped bus)

def speed_ms_to_cong(v_ms: float) -> float:
    kmh = v_ms * 3.6
    return round(max(0.05, min(0.98, 1.0 - kmh / FREE_KMH)), 3)


def main():
    # ── 1. Load OSM segment centroids ────────────────────────────
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

    # ── 2. Load link_mapping: seg_fid → link_id ──────────────────
    link_mapping = json.loads((DATA_DIR / "link_mapping.json").read_text())
    seg_to_link  = {fid: info["link_id"] for fid, info in link_mapping.items()}
    print(f"  link_mapping: {len(seg_to_link)} segments assigned to links")

    # ── 3. Load schematic link lengths ───────────────────────────
    schematic_links = json.loads((DATA_DIR / "schematic_links.json").read_text())

    # ── 4. Parse CSV ─────────────────────────────────────────────
    print("Parsing bus probe CSV …")
    with open(CSV_PATH, "rb") as f:
        content = f.read().replace(b"\x00", b"")

    # Collect (vid, epoch, x, y) for all valid IGNON pings
    records = []   # [vid, epoch_f, x, y]
    reader  = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
    for row in reader:
        p = row["gprmc"].strip('"').split(",")
        if len(p) < 16:               continue
        if p[6] == "IGNOFF":          continue
        if p[10] != "A":              continue
        try:
            lat = ddmm(p[11], p[12])
            lon = ddmm(p[13], p[14])
            dt  = datetime.fromisoformat(row["createddate"].replace("Z", "+00:00"))
            vid = p[5]
        except Exception:
            continue
        if not (12.80 <= lat <= 13.25 and 79.90 <= lon <= 80.40):
            continue
        x, y = to_xy(lat, lon)
        records.append((vid, dt.timestamp(), x, y))

    total = len(records)
    print(f"  Valid IGNON pings: {total:,}")

    # ── 5. Batch nearest-centroid matching ───────────────────────
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

    # Assign link_id per ping (None if out of match radius)
    ping_link = []
    for i, (vid, epoch, x, y) in enumerate(records):
        if nearest_dist[i] <= MATCH_RADIUS:
            fid  = seg_ids[nearest_seg[i]]
            lid  = seg_to_link.get(fid)       # None if not in any link
        else:
            lid = None
        ping_link.append(lid)

    matched = sum(1 for l in ping_link if l is not None)
    print(f"  Matched to schematic links: {matched:,} / {total:,} ({100*matched/total:.1f}%)")

    # ── 6. Group by vehicle, sort by time ────────────────────────
    print("Grouping by vehicle …")
    veh_pings: dict[str, list] = defaultdict(list)
    for i, (vid, epoch, x, y) in enumerate(records):
        veh_pings[vid].append((epoch, x, y, ping_link[i]))
    for vid in veh_pings:
        veh_pings[vid].sort(key=lambda r: r[0])

    # ── 7. Extract traversals per link ───────────────────────────
    print("Extracting link traversals …")
    # link_id → list of (total_dist_m, elapsed_s)
    traversals: dict[str, list] = defaultdict(list)

    for vid, pings in veh_pings.items():
        # Scan consecutive pings for runs on the same link
        trav_link  = None
        trav_start = 0.0
        trav_dist  = 0.0
        trav_pings = 0
        prev_epoch, prev_x, prev_y = None, None, None

        for epoch, x, y, lid in pings:
            gap = (epoch - prev_epoch) if prev_epoch is not None else 0.0

            # Break conditions: link changed, off-road, or time gap too large
            if lid != trav_link or gap > MAX_GAP_S:
                # Save completed traversal
                if trav_link is not None and trav_pings >= MIN_PINGS and trav_dist >= MIN_DIST_M:
                    elapsed = prev_epoch - trav_start
                    if elapsed > 0:
                        traversals[trav_link].append((trav_dist, elapsed))
                # Start new traversal
                trav_link  = lid
                trav_start = epoch
                trav_dist  = 0.0
                trav_pings = 1
            else:
                # Continuing same link
                if prev_x is not None:
                    trav_dist += math.sqrt((x - prev_x)**2 + (y - prev_y)**2)
                trav_pings += 1

            prev_epoch, prev_x, prev_y = epoch, x, y

        # Close final traversal
        if trav_link is not None and trav_pings >= MIN_PINGS and trav_dist >= MIN_DIST_M:
            elapsed = prev_epoch - trav_start
            if elapsed > 0:
                traversals[trav_link].append((trav_dist, elapsed))

    total_travs = sum(len(v) for v in traversals.values())
    print(f"  Total valid traversals: {total_travs:,} across {len(traversals)} links")

    # ── 8. Compute space-mean speed per link ─────────────────────
    print("Computing space-mean speed per link …")
    result: dict[str, float] = {}
    link_stats = []

    for lid, travs in traversals.items():
        # Space-mean speed: total_distance / total_time (harmonic mean of speeds)
        # Use median of individual traversal speeds to be robust to outliers
        speeds_ms = [d / t for d, t in travs if t > 0]
        speeds_ms.sort()
        median_ms = speeds_ms[len(speeds_ms) // 2]
        cong = speed_ms_to_cong(median_ms)
        result[lid] = {"cong": cong, "n": len(travs)}
        link_stats.append((lid, median_ms * 3.6, len(travs), cong))

    # ── 9. Print comparison ──────────────────────────────────────
    print(f"\n{'Link':<6} {'km/h':>7} {'n_trav':>7} {'cong_tt':>9}  {'cong_gps':>9}  {'diff':>7}")
    print("─" * 52)

    # Load GPS-based congestion for comparison
    gps_cong = json.loads((DATA_DIR / "bus_probe_speeds.json").read_text())
    # Aggregate GPS per link (median of segments in that link)
    link_gps_vals: dict[str, list] = defaultdict(list)
    for fid, cval in gps_cong.items():
        lid = seg_to_link.get(fid)
        if lid:
            link_gps_vals[lid].append(cval)
    link_gps_med = {}
    for lid, vals in link_gps_vals.items():
        vals.sort()
        link_gps_med[lid] = vals[len(vals) // 2]

    link_stats.sort(key=lambda x: x[0])
    for lid, kmh, nt, cong_tt in link_stats:
        cong_gps = link_gps_med.get(lid, float('nan'))
        diff = cong_tt - cong_gps if not math.isnan(cong_gps) else float('nan')
        gps_str  = f"{cong_gps:.3f}" if not math.isnan(cong_gps) else "  n/a"
        diff_str = f"{diff:+.3f}"     if not math.isnan(diff)    else "  n/a"
        print(f"{lid:<6} {kmh:>7.1f} {nt:>7} {cong_tt:>9.3f}  {gps_str:>9}  {diff_str:>7}")

    # Summary stats
    all_tt  = [c for _, _, _, c in link_stats]
    all_gps = [link_gps_med[lid] for lid, _, _, _ in link_stats if lid in link_gps_med]
    print(f"\n旅行時間速度: {len(result)}/{len(schematic_links)} リンクカバー")
    if all_tt:
        print(f"  avg_cong={sum(all_tt)/len(all_tt):.3f}  "
              f"min={min(all_tt):.3f}  max={max(all_tt):.3f}")
    if all_gps:
        print(f"GPS瞬間速度: {len(all_gps)} リンク(集約)")
        print(f"  avg_cong={sum(all_gps)/len(all_gps):.3f}  "
              f"min={min(all_gps):.3f}  max={max(all_gps):.3f}")

    # ── 10. Save ─────────────────────────────────────────────────
    out_path = DATA_DIR / "bus_link_travel_speeds.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
