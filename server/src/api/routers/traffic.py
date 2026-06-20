import json, random, time, math
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent / "data"
_roads_raw         = json.loads((DATA_DIR / "chennai_roads.geojson").read_text())
_intersections_raw = json.loads((DATA_DIR / "chennai_intersections.json").read_text())
_link_mapping      = json.loads((DATA_DIR / "link_mapping.json").read_text())
_schematic_links   = json.loads((DATA_DIR / "schematic_links.json").read_text())
_probe_speeds: dict[str, float] = json.loads((DATA_DIR / "bus_probe_speeds.json").read_text())
_probe_timeline = json.loads((DATA_DIR / "bus_probe_timeline.json").read_text())
_link_travel_raw: dict[str, dict] = json.loads((DATA_DIR / "bus_link_travel_speeds.json").read_text())
_link_tt_timeline_raw = json.loads((DATA_DIR / "bus_link_tt_timeline.json").read_text())
# support both old format (float) and new format ({cong, n})
def _tt_entry(lid: str):
    v = _link_travel_raw.get(lid)
    if v is None:           return None, 0
    if isinstance(v, dict): return v["cong"], v["n"]
    return float(v), 0

# Pre-index: link_id → list of (fraction, feature_id)
_link_segs = {}   # type: dict[str, list]
for fid, info in _link_mapping.items():
    _link_segs.setdefault(info["link_id"], []).append((info["fraction"], int(fid)))
for lst in _link_segs.values():
    lst.sort(key=lambda x: x[0])

LINK_ORDER = [
    "l01","l02","l03","l04","l05","l06","l07","l08","l09","l10",
    "l11","l12","l13","l14","l15","l16","l17","l18","l19","l20",
    "l21","l22","l23","l24","l25","l26","l27","l28","l29","l30",
    "l31","l32","l33","l34","l35","l36","l37","l38","l39","l40",
    "l41","l42","l43","l44","l45","l46","l47","l48","l49","l50",
    "l51","l52","l53","l54","l55","l56","l57","l58","l59","l60",
    "l61","l62","l63","l64",
]

# ── Proximity index: intersection → nearby segment fids ──────────────────────
_LAT0, _LON0 = 13.07, 80.24
_M_PER_LAT   = 111320.0
_M_PER_LON   = 108430.0   # 111320 * cos(13°)
_RADIUS_M    = 500

def _to_m(lat: float, lon: float):
    return (lon - _LON0) * _M_PER_LON, (lat - _LAT0) * _M_PER_LAT

def _seg_midpoint(f):
    coords = f["geometry"]["coordinates"]
    if not coords:
        return None
    mid = coords[len(coords) // 2]
    return mid[1], mid[0]   # lat, lon

_seg_pos_m = {}  # type: dict[int, tuple]
for _f in _roads_raw["features"]:
    _pt = _seg_midpoint(_f)
    if _pt:
        _seg_pos_m[_f["id"]] = _to_m(*_pt)

_r2 = _RADIUS_M ** 2

def _compute_isec_nearby():
    result: dict[str, list[int]] = {}
    for isec in _intersections_raw:
        ix, iy = _to_m(isec["lat"], isec["lon"])
        nearby = [
            fid for fid, (sx, sy) in _seg_pos_m.items()
            if abs(sx - ix) < _RADIUS_M and abs(sy - iy) < _RADIUS_M
            and (sx - ix) ** 2 + (sy - iy) ** 2 < _r2
        ]
        result[isec["id"]] = nearby
    return result

_isec_nearby = _compute_isec_nearby()

def _snap_intersection_cong(seg_map: dict) -> list:
    result = []
    for isec in _intersections_raw:
        nearby = _isec_nearby.get(isec["id"], [])
        vals = [seg_map[str(fid)] for fid in nearby if str(fid) in seg_map]
        cong = round(sum(vals) / len(vals), 3) if vals else \
               round(_probe_speeds.get(str(nearby[0]), 0.3), 3) if nearby else 0.3
        result.append({**isec, "congestion": cong})
    return result

# ─────────────────────────────────────────────────────────────────────────────

def _cong_level(v: float) -> str:
    if v < 0.33: return "free"
    if v < 0.55: return "moderate"
    if v < 0.75: return "heavy"
    return "severe"

# In-memory congestion state (LIVE mode)
_congestion = {}  # type: dict[int, float]
_last_update = 0.0

def _hour_factor(hour: int) -> float:
    if 8 <= hour <= 10:
        return 0.45 + 0.20 * math.sin(math.pi * (hour - 8) / 2)
    if 17 <= hour <= 20:
        return 0.42 + 0.22 * math.sin(math.pi * (hour - 17) / 3)
    if 0 <= hour <= 5:
        return 0.12
    return 0.28

def _update_congestion():
    global _last_update
    now = time.time()
    if now - _last_update < 30:
        return
    _last_update = now
    hour = datetime.now().hour
    base = _hour_factor(hour)
    rng = random.Random(int(now / 30))
    for f in _roads_raw["features"]:
        rid = f["id"]
        rid_str = str(rid)
        if rid not in _congestion:
            if rid_str in _probe_speeds:
                _congestion[rid] = round(max(0.05, min(0.98,
                    _probe_speeds[rid_str] + rng.gauss(0, 0.03))), 3)
            else:
                _congestion[rid] = round(max(0.05, min(0.98, rng.gauss(base, 0.15))), 3)
        else:
            prev   = _congestion[rid]
            target = _probe_speeds.get(rid_str, base)
            delta  = rng.gauss(0, 0.04)
            _congestion[rid] = round(max(0.05, min(0.98, prev + delta + (target - prev) * 0.10)), 3)


@router.get("/traffic/roads", response_model=None, tags=["Traffic"])
def get_roads():
    _update_congestion()
    features = []
    for f in _roads_raw["features"]:
        c = _congestion.get(f["id"], 0.3)
        nf = dict(f)
        nf["properties"] = {**f["properties"], "congestion": c}
        features.append(nf)
    return {"type": "FeatureCollection", "features": features}


@router.get("/traffic/intersections", response_model=None, tags=["Traffic"])
def get_intersections():
    _update_congestion()
    rng = random.Random(int(time.time() / 30))
    result = []
    for node in _intersections_raw:
        # Use nearby segment congestion if available, else simulate
        nearby = _isec_nearby.get(node["id"], [])
        vals = [_congestion[fid] for fid in nearby if fid in _congestion]
        if vals:
            congestion = round(max(0.05, min(0.98,
                sum(vals) / len(vals) + rng.gauss(0, 0.04))), 2)
        else:
            congestion = round(max(0.05, min(0.98, rng.gauss(0.4, 0.2))), 2)
        result.append({**node, "congestion": congestion})
    return {"status": "ok", "result": result}


def _aggregate_schematic(cong_lookup, rng_seed: int) -> list:
    rng = random.Random(rng_seed)
    links_out = []
    for lid in LINK_ORDER:
        if lid not in _schematic_links:
            continue
        meta = _schematic_links[lid]
        n    = meta["seg_count"]
        segs = _link_segs.get(lid, [])

        bucket_vals: list[list[float]] = [[] for _ in range(n)]
        for frac, fid in segs:
            cval = cong_lookup(fid)
            b    = min(int(frac * n), n - 1)
            bucket_vals[b].append(cval)

        raw = [None] * n
        for i, vals in enumerate(bucket_vals):
            if vals:
                raw[i] = sum(vals) / len(vals)

        last = 0.3
        filled = []
        for v in raw:
            last = v if v is not None else last
            filled.append(last)
        last = filled[-1]
        for i in range(n - 1, -1, -1):
            if raw[i] is None:
                filled[i] = (filled[i] + last) * 0.5
            else:
                last = filled[i]

        fwd = [round(v, 3) for v in filled]
        bwd = [round(max(0.05, min(0.98, v + rng.gauss(0, 0.08))), 3) for v in filled]

        links_out.append({
            "id":        lid,
            "from":      meta["from"],
            "to":        meta["to"],
            "length_m":  meta["length_m"],
            "seg_count": n,
            "forward":   fwd,
            "backward":  bwd,
        })
    return links_out


def _schematic_tt(gps_links: list) -> list:
    """
    TT method with GPS-modulated spatial pattern.

    Per bucket:
      blended = alpha * tt_modulated + (1 - alpha) * gps_bucket
    where:
      tt_modulated = tt_base * (gps_bucket / gps_link_avg)  -- scales GPS pattern to TT level
      alpha        = reliability weight = min(1, n_trav / N_FULL)

    This gives:
      - TT absolute level when n_trav is high
      - GPS spatial variation within every link
      - Graceful fallback to GPS when TT data is sparse
    """
    N_FULL = 150  # traversals for full TT trust

    gps_by_id = {lk["id"]: lk for lk in gps_links}
    links_out  = []

    for lid in LINK_ORDER:
        if lid not in _schematic_links:
            continue
        meta      = _schematic_links[lid]
        n         = meta["seg_count"]
        tt_base, n_trav = _tt_entry(lid)
        alpha     = min(1.0, n_trav / N_FULL) if tt_base is not None else 0.0

        gps_lk    = gps_by_id.get(lid)
        gps_fwd   = gps_lk["forward"]  if gps_lk else [0.3] * n
        gps_bwd   = gps_lk["backward"] if gps_lk else [0.3] * n

        def blend(gps_arr, tt_b, a):
            avg = sum(gps_arr) / len(gps_arr) if gps_arr else 0.3
            out = []
            for g in gps_arr:
                if tt_b is not None and avg > 0:
                    tt_mod = tt_b * (g / avg)
                else:
                    tt_mod = g
                v = a * tt_mod + (1 - a) * g
                out.append(round(max(0.05, min(0.98, v)), 3))
            return out

        fwd = blend(gps_fwd, tt_base, alpha)
        bwd = blend(gps_bwd, tt_base, alpha)

        links_out.append({
            "id": lid, "from": meta["from"], "to": meta["to"],
            "length_m": meta["length_m"], "seg_count": n,
            "forward": fwd, "backward": bwd,
            "n_trav": n_trav, "alpha": round(alpha, 2),
        })
    return links_out


@router.get("/traffic/schematic", response_model=None, tags=["Traffic"])
def get_schematic(method: str = "gps"):
    if method == "tt":
        _update_congestion()
        gps_links = _aggregate_schematic(
            lambda fid: _congestion.get(fid, 0.3),
            rng_seed=int(time.time() / 30) + 1,
        )
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": "travel_time",
            "links": _schematic_tt(gps_links),
        }

    _update_congestion()
    links = _aggregate_schematic(
        lambda fid: _congestion.get(fid, 0.3),
        rng_seed=int(time.time() / 30) + 1,
    )
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "gps",
        "links": links,
    }


# ── Pre-compute all replay snapshots at startup ───────────────────────────────
def _build_schematic_snapshots() -> list:
    snaps = []
    for s in _probe_timeline["snapshots"]:
        seg_map: dict[str, float] = s["segments"]
        links = _aggregate_schematic(
            lambda fid, m=seg_map: m.get(str(fid), _probe_speeds.get(str(fid), 0.3)),
            rng_seed=s["index"] + 100,
        )
        intersections = _snap_intersection_cong(seg_map)
        snaps.append({
            "index":         s["index"],
            "time_ist":      s["time_ist"],
            "links":         links,
            "intersections": intersections,
        })
    return snaps

_schematic_snapshots = _build_schematic_snapshots()


# ── Pre-compute TT-method snapshots ──────────────────────────────────────────
# Build a dict: bin_idx → {link_id: {cong, n}}
_tt_timeline_by_bin: dict[int, dict] = {}
for _s in _link_tt_timeline_raw["snapshots"]:
    _tt_timeline_by_bin[_s["index"]] = _s["links"]


def _schematic_tt_for_bin(gps_links: list, bin_idx: int) -> list:
    """
    TT-method spatial blend for a specific time bin.
    Uses per-bin TT traversals where available; falls back to overall TT data.
    """
    N_FULL    = 50   # lower threshold per bin (fewer traversals available)
    bin_data  = _tt_timeline_by_bin.get(bin_idx, {})
    gps_by_id = {lk["id"]: lk for lk in gps_links}
    links_out = []

    for lid in LINK_ORDER:
        if lid not in _schematic_links:
            continue
        meta    = _schematic_links[lid]
        n       = meta["seg_count"]
        gps_lk  = gps_by_id.get(lid)
        gps_fwd = gps_lk["forward"]  if gps_lk else [0.3] * n
        gps_bwd = gps_lk["backward"] if gps_lk else [0.3] * n

        # Per-bin TT data (preferred) → fallback to overall TT
        if lid in bin_data and bin_data[lid]["n"] >= 2:
            tt_base  = bin_data[lid]["cong"]
            n_trav   = bin_data[lid]["n"]
        else:
            tt_base, n_trav = _tt_entry(lid)

        alpha = min(1.0, n_trav / N_FULL) if tt_base is not None else 0.0

        def blend(gps_arr, tt_b, a):
            avg = sum(gps_arr) / len(gps_arr) if gps_arr else 0.3
            return [
                round(max(0.05, min(0.98,
                    a * (tt_b * (g / avg) if tt_b is not None and avg > 0 else g)
                    + (1 - a) * g
                )), 3)
                for g in gps_arr
            ]

        links_out.append({
            "id": lid, "from": meta["from"], "to": meta["to"],
            "length_m": meta["length_m"], "seg_count": n,
            "forward":  blend(gps_fwd, tt_base, alpha),
            "backward": blend(gps_bwd, tt_base, alpha),
            "n_trav": n_trav, "alpha": round(alpha, 2),
        })
    return links_out


def _build_schematic_snapshots_tt() -> list:
    snaps = []
    for s in _probe_timeline["snapshots"]:
        seg_map: dict[str, float] = s["segments"]
        gps_links = _aggregate_schematic(
            lambda fid, m=seg_map: m.get(str(fid), _probe_speeds.get(str(fid), 0.3)),
            rng_seed=s["index"] + 300,
        )
        links = _schematic_tt_for_bin(gps_links, s["index"])
        intersections = _snap_intersection_cong(seg_map)
        snaps.append({
            "index":         s["index"],
            "time_ist":      s["time_ist"],
            "links":         links,
            "intersections": intersections,
        })
    return snaps


_schematic_snapshots_tt = _build_schematic_snapshots_tt()


@router.get("/traffic/schematic-snapshots", response_model=None, tags=["Traffic"])
def get_schematic_snapshots(method: str = "gps"):
    """
    Pre-computed time snapshots from bus probe data (2-min bins, 16:10–16:38 IST).
    method=gps (default) or method=tt for travel-time speed method.
    """
    snaps = _schematic_snapshots_tt if method == "tt" else _schematic_snapshots
    return {
        "bin_minutes": _probe_timeline["bin_minutes"],
        "start_ist":   _probe_timeline["start_ist"],
        "end_ist":     _probe_timeline["end_ist"],
        "method":      method,
        "snapshots":   snaps,
    }


@router.get("/traffic/road-snapshots", response_model=None, tags=["Traffic"])
def get_road_snapshots():
    """
    Lightweight per-snapshot segment congestion (no geometries).
    Client merges these values into the base GeoJSON for replay mode.
    """
    return {
        "bin_minutes": _probe_timeline["bin_minutes"],
        "start_ist":   _probe_timeline["start_ist"],
        "end_ist":     _probe_timeline["end_ist"],
        "snapshots": [
            {
                "index":    s["index"],
                "time_ist": s["time_ist"],
                "segments": s["segments"],   # {str_osm_id: congestion_float}
            }
            for s in _probe_timeline["snapshots"]
        ],
    }


@router.get("/traffic/method-comparison", response_model=None, tags=["Traffic"])
def get_method_comparison():
    """
    Per-link GPS vs TT comparison statistics over the 15-snapshot timeline.
    Returns time series, Pearson correlation, volatility, n_trav, and adoption recommendation.
    """
    time_labels = [s["time_ist"] for s in _schematic_snapshots]
    n_bins = len(time_labels)

    # GPS time series per link (avg of forward buckets per snapshot)
    gps_ts_map: dict[str, list[float]] = {}
    for snap in _schematic_snapshots:
        for lk in snap["links"]:
            lid = lk["id"]
            fwd = lk.get("forward", [])
            gps_ts_map.setdefault(lid, []).append(
                round(sum(fwd) / len(fwd), 4) if fwd else 0.3
            )

    # TT time series + n_trav per link per snapshot
    tt_ts_map: dict[str, list[float]] = {}
    tt_n_map:  dict[str, list[int]]   = {}
    for snap in _schematic_snapshots_tt:
        for lk in snap["links"]:
            lid = lk["id"]
            fwd = lk.get("forward", [])
            tt_ts_map.setdefault(lid, []).append(
                round(sum(fwd) / len(fwd), 4) if fwd else 0.3
            )
            tt_n_map.setdefault(lid, []).append(lk.get("n_trav", 0))

    def stats(ts):
        n = len(ts)
        avg = sum(ts) / n
        std = (sum((v - avg) ** 2 for v in ts) / n) ** 0.5
        return round(avg, 4), round(std, 4)

    def pearson(xs, ys):
        n = len(xs)
        mx, sx = stats(xs)
        my, sy = stats(ys)
        if sx == 0 or sy == 0:
            return 0.0
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
        return round(cov / (sx * sy), 4)

    # Network-wide time series (all-link average per bin)
    def net_ts(ts_map):
        per_bin = [[] for _ in range(n_bins)]
        for ts in ts_map.values():
            for i, v in enumerate(ts[:n_bins]):
                per_bin[i].append(v)
        return [round(sum(b) / len(b), 4) if b else 0.3 for b in per_bin]

    net_gps = net_ts(gps_ts_map)
    net_tt  = net_ts(tt_ts_map)

    links_out = []
    for lid in LINK_ORDER:
        if lid not in _schematic_links:
            continue
        meta = _schematic_links[lid]

        gps_ts   = gps_ts_map.get(lid, [0.3] * n_bins)
        tt_ts    = tt_ts_map.get(lid,  [0.3] * n_bins)
        n_trav_ts = tt_n_map.get(lid,  [0]   * n_bins)

        gps_avg, gps_std = stats(gps_ts)
        tt_avg,  tt_std  = stats(tt_ts)

        diffs    = [g - t for g, t in zip(gps_ts, tt_ts)]
        abs_diffs = [abs(d) for d in diffs]
        mean_diff = round(sum(diffs) / len(diffs), 4)
        mad  = round(sum(abs_diffs) / len(abs_diffs), 4)
        rmse = round((sum(d ** 2 for d in diffs) / len(diffs)) ** 0.5, 4)
        corr = pearson(gps_ts, tt_ts)

        avg_n_trav = round(sum(n_trav_ts) / len(n_trav_ts), 1)
        min_n_trav = min(n_trav_ts)

        # Adoption recommendation
        # TT is preferred when: enough traversals AND good temporal correlation
        # Blend when moderately reliable; GPS when TT data is sparse/uncorrelated
        if avg_n_trav >= 30 and corr >= 0.4:
            rec, conf = "tt",    "high"
        elif avg_n_trav >= 10 and corr >= 0.2:
            rec, conf = "blend", "medium"
        elif avg_n_trav >= 5:
            rec, conf = "blend", "low"
        else:
            rec, conf = "gps",   "low"

        # Volatility ratio: how much more/less volatile is TT vs GPS
        vol_ratio = round(tt_std / gps_std, 3) if gps_std > 0 else 1.0

        links_out.append({
            "id":         lid,
            "from":       meta["from"],
            "to":         meta["to"],
            "length_m":   meta["length_m"],
            # time series
            "gps_ts":     gps_ts,
            "tt_ts":      tt_ts,
            "n_trav_ts":  n_trav_ts,
            "diff_ts":    [round(d, 4) for d in diffs],
            # aggregate stats
            "gps_avg":    gps_avg,
            "tt_avg":     tt_avg,
            "gps_std":    gps_std,
            "tt_std":     tt_std,
            "mean_diff":  mean_diff,
            "mad":        mad,
            "rmse":       rmse,
            "correlation": corr,
            "avg_n_trav": avg_n_trav,
            "min_n_trav": min_n_trav,
            "vol_ratio":  vol_ratio,
            "recommendation": rec,
            "confidence": conf,
        })

    # Network-level summary
    def net_avg(key):
        return round(sum(lk[key] for lk in links_out) / len(links_out), 4)

    rec_dist = {"gps": 0, "blend": 0, "tt": 0}
    for lk in links_out:
        rec_dist[lk["recommendation"]] += 1

    return {
        "time_labels": time_labels,
        "network": {
            "gps_ts":    net_gps,
            "tt_ts":     net_tt,
            "gps_avg":   net_avg("gps_avg"),
            "tt_avg":    net_avg("tt_avg"),
            "mean_corr": net_avg("correlation"),
            "mean_mad":  net_avg("mad"),
            "mean_rmse": net_avg("rmse"),
            "rec_tt":    rec_dist["tt"],
            "rec_blend": rec_dist["blend"],
            "rec_gps":   rec_dist["gps"],
        },
        "links": links_out,
    }


@router.get("/traffic/link-analytics", response_model=None, tags=["Traffic"])
def get_link_analytics():
    """
    Per-link congestion statistics derived from bus probe timeline snapshots.
    Returns time series (15 steps) and summary stats for each schematic link.
    """
    time_labels = [s["time_ist"] for s in _schematic_snapshots]

    # Build per-link forward-average time series from precomputed snapshots
    link_ts: dict[str, list[float]] = {}
    for snap in _schematic_snapshots:
        for lk in snap["links"]:
            lid = lk["id"]
            fwd = lk.get("forward", [])
            avg_fwd = round(sum(fwd) / len(fwd), 3) if fwd else 0.3
            link_ts.setdefault(lid, []).append(avg_fwd)

    links_out = []
    for lid in LINK_ORDER:
        if lid not in _schematic_links:
            continue
        meta = _schematic_links[lid]
        ts = link_ts.get(lid, [0.3] * len(time_labels))
        avg = round(sum(ts) / len(ts), 3)
        mx = round(max(ts), 3)
        mn = round(min(ts), 3)
        std = round((sum((v - avg) ** 2 for v in ts) / len(ts)) ** 0.5, 3)
        tt_base, n_trav = _tt_entry(lid)
        links_out.append({
            "id": lid,
            "from": meta["from"],
            "to": meta["to"],
            "length_m": meta["length_m"],
            "avg_cong": avg,
            "max_cong": mx,
            "min_cong": mn,
            "std_cong": std,
            "tt_base": round(tt_base, 3) if tt_base is not None else None,
            "n_trav": n_trav,
            "snapshots": ts,
        })

    # Network-wide average congestion per time step
    net_ts = []
    for snap in _schematic_snapshots:
        all_vals: list[float] = []
        for lk in snap["links"]:
            all_vals.extend(lk.get("forward", []))
        net_ts.append(round(sum(all_vals) / len(all_vals), 3) if all_vals else 0.3)

    return {
        "time_labels": time_labels,
        "links": links_out,
        "network_ts": net_ts,
    }


@router.get("/traffic/stats", response_model=None, tags=["Traffic"])
def get_stats():
    _update_congestion()
    vals = list(_congestion.values())
    if not vals:
        return {"status": "ok", "result": {}}
    avg = sum(vals) / len(vals)
    severe   = sum(1 for v in vals if v >= 0.75)
    moderate = sum(1 for v in vals if 0.45 <= v < 0.75)
    free     = sum(1 for v in vals if v < 0.45)
    return {
        "status": "ok",
        "result": {
            "avg_congestion":    round(avg, 3),
            "severe_segments":   severe,
            "moderate_segments": moderate,
            "free_segments":     free,
            "total_segments":    len(vals),
            "congestion_index":  round(avg * 10, 1),
        }
    }


# ── BPR demand forecast ───────────────────────────────────────────────────────
_BPR_PATH = DATA_DIR / "bpr_params.json"
_bpr_cache = None

def _load_bpr():
    global _bpr_cache
    if _bpr_cache is None:
        if not _BPR_PATH.exists():
            return None
        _bpr_cache = json.loads(_BPR_PATH.read_text())
    return _bpr_cache

def _nearest_q_key(demand: float) -> str:
    """Round demand to nearest 0.05 step stored in bpr_params.forecast."""
    q = max(0.5, min(3.0, demand))
    return str(round(round(q / 0.05) * 0.05, 2))

@router.get("/traffic/forecast", response_model=None, tags=["Traffic"])
def get_forecast(demand: float = 1.0):
    bpr = _load_bpr()
    if bpr is None:
        raise HTTPException(status_code=503, detail="BPR data not available. Run preprocess_bpr.py")
    q_key = _nearest_q_key(demand)
    links_out = {}
    for lid in LINK_ORDER:
        p = bpr.get(lid)
        if p is None:
            links_out[lid] = 0.35
            continue
        links_out[lid] = p["forecast"].get(q_key, p["real_cong"])
    # Bottleneck ranking (by sat_threshold ascending)
    bottlenecks = sorted(
        [{"id": lid,
          "sat_threshold": bpr[lid].get("sat_threshold"),
          "real_cong":     bpr[lid]["real_cong"],
          "pred_cong":     links_out[lid],
          "vc_ratio":      bpr[lid]["vc_ratio"],
          "sensitivity":   bpr[lid]["sensitivity"]}
         for lid in LINK_ORDER if lid in bpr],
        key=lambda x: (x["sat_threshold"] or 99)
    )
    net_pred = round(sum(links_out.values()) / len(links_out), 3)
    net_real = round(sum(bpr[lid]["real_cong"] for lid in LINK_ORDER if lid in bpr) / 64, 3)
    return {
        "demand": round(float(demand), 2),
        "q_key":  q_key,
        "net_real": net_real,
        "net_pred": net_pred,
        "links":  links_out,
        "bottlenecks": bottlenecks,
    }

@router.get("/traffic/bpr-params", response_model=None, tags=["Traffic"])
def get_bpr_params():
    bpr = _load_bpr()
    if bpr is None:
        raise HTTPException(status_code=503, detail="BPR data not available. Run preprocess_bpr.py")
    # Merge schematic_links metadata (from/to/length) into each link entry
    out = {}
    for lid, params in bpr.items():
        meta = _schematic_links.get(lid, {})
        out[lid] = {**params, "from": meta.get("from"), "to": meta.get("to"), "length_m": meta.get("length_m")}
    return out


# ── SUMO simulation scenarios ─────────────────────────────────────────────────
_SUMO_PATH = DATA_DIR / "sumo_scenarios.json"
_sumo_scenarios_cache = None

@router.get("/traffic/sumo-scenarios", response_model=None, tags=["Traffic"])
def get_sumo_scenarios():
    global _sumo_scenarios_cache
    if not _SUMO_PATH.exists():
        raise HTTPException(status_code=503, detail="SUMO simulation data not yet generated")
    if _sumo_scenarios_cache is None:
        _sumo_scenarios_cache = json.loads(_SUMO_PATH.read_text())
    return _sumo_scenarios_cache

