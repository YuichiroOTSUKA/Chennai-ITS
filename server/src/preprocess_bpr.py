"""
BPR (Bureau of Public Roads) calibration for demand forecasting.

Model: v = v0 / (1 + α*(q/c)^β)
       cong = 1 - v/v0 = 1 - 1/(1 + α*(q/c)^β)

Calibration:
  At q = q_curr (current demand), cong = real_cong (GPS/TT blend).
  Solve for q_curr/c (current v/c ratio):
      q_curr/c = (real_cong / (α*(1-real_cong)))^(1/β)

  For future demand multiplier m:
      cong(m) = 1 - 1/(1 + α*(m * q_curr/c)^β)

BPR defaults: α=0.15, β=4.0  (HCM / TRB standard)

Output: api/data/bpr_params.json
  {
    "l01": {
      "alpha": 0.15, "beta": 4.0,
      "real_cong": 0.35,          # GPS/TT blend at current demand
      "vc_ratio": 1.38,           # current q/c (>1.0 = over-capacity)
      "sensitivity": 0.24,        # d(cong)/dm at m=1.0
      "sat_threshold": 1.32,      # demand multiplier where cong → 0.75
      "forecast": {"0.5":0.12, ..., "3.0":0.97}
    },
    ...
  }
"""

import json, math
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent / "api" / "data"

# ── Load data ─────────────────────────────────────────────────────────────────
probe_speeds = json.loads((DATA_DIR / "bus_probe_speeds.json").read_text())
link_mapping = json.loads((DATA_DIR / "link_mapping.json").read_text())
tt_raw       = json.loads((DATA_DIR / "bus_link_travel_speeds.json").read_text())
link_meta    = json.loads((DATA_DIR / "schematic_links.json").read_text())

LINK_ORDER = [f"l{i:02d}" for i in range(1, 65)]

ALPHA = 0.15   # BPR alpha (HCM standard)
BETA  = 4.0    # BPR beta
SAT   = 0.75   # severe congestion threshold

# ── Link → segments index ─────────────────────────────────────────────────────
link_segs = defaultdict(list)
for fid, info in link_mapping.items():
    link_segs[info["link_id"]].append((info["fraction"], fid))

# ── GPS per-link congestion (weighted by segment fraction) ────────────────────
def gps_cong(lid):
    segs = link_segs.get(lid, [])
    vals = [(f, probe_speeds[fid]) for f, fid in segs if fid in probe_speeds]
    if not vals:
        return None
    w = sum(f for f, _ in vals)
    return sum(f * v for f, v in vals) / w

# ── TT per-link congestion ────────────────────────────────────────────────────
def tt_cong(lid):
    v = tt_raw.get(lid)
    if v is None:           return None
    if isinstance(v, dict): return v["cong"]
    return float(v)

# ── Blended real congestion at current demand ─────────────────────────────────
def real_cong(lid):
    g = gps_cong(lid)
    t = tt_cong(lid)
    if g is not None and t is not None:
        return (g + t) / 2
    return g if g is not None else (t if t is not None else 0.35)

# ── BPR core ──────────────────────────────────────────────────────────────────
def bpr_cong(m_vc):
    """Congestion at m × (current v/c ratio). m=1.0 returns real_cong."""
    return 1.0 - 1.0 / (1.0 + ALPHA * (m_vc ** BETA))

def vc_from_cong(rc):
    """Solve q/c from observed congestion. Clamp to safe range."""
    rc = max(0.051, min(0.979, rc))   # avoid numerical edge
    ratio_inner = rc / (ALPHA * (1.0 - rc))
    return ratio_inner ** (1.0 / BETA)

def predict(m, vc_ratio):
    """Congestion at demand multiplier m, given current v/c ratio."""
    return max(0.05, min(0.98, bpr_cong(m * vc_ratio)))

# ── Saturation threshold ──────────────────────────────────────────────────────
def sat_threshold(vc_ratio):
    """Smallest m (in steps of 0.01) where predicted cong ≥ SAT. None if >10×."""
    for i in range(50, 1001):
        m = i / 100
        if predict(m, vc_ratio) >= SAT:
            return round(m, 2)
    return None

# ── Main ──────────────────────────────────────────────────────────────────────
FORECAST_Q = [round(q / 100, 2) for q in range(50, 305, 5)]   # 0.50 → 3.00

result = {}
for lid in LINK_ORDER:
    rc  = real_cong(lid)
    vc  = vc_from_cong(rc)
    sat = sat_threshold(vc)

    # Sensitivity: d(cong)/dm at m=1.0
    dm   = 0.01
    sens = (predict(1.0 + dm, vc) - predict(1.0 - dm, vc)) / (2 * dm)

    forecast = {str(q): round(predict(q, vc), 3) for q in FORECAST_Q}

    result[lid] = {
        "alpha":         ALPHA,
        "beta":          BETA,
        "real_cong":     round(rc,  3),
        "vc_ratio":      round(vc,  4),
        "sensitivity":   round(sens, 4),
        "sat_threshold": sat,
        "forecast":      forecast,
    }

out_path = DATA_DIR / "bpr_params.json"
out_path.write_text(json.dumps(result, ensure_ascii=False))
print(f"Wrote {out_path}")

# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\nReal congestion: "
      f"mean={sum(result[l]['real_cong'] for l in LINK_ORDER)/64:.3f}, "
      f"min={min(result[l]['real_cong'] for l in LINK_ORDER):.3f}, "
      f"max={max(result[l]['real_cong'] for l in LINK_ORDER):.3f}")
print(f"v/c ratio:       "
      f"mean={sum(result[l]['vc_ratio'] for l in LINK_ORDER)/64:.3f}, "
      f"min={min(result[l]['vc_ratio'] for l in LINK_ORDER):.3f}, "
      f"max={max(result[l]['vc_ratio'] for l in LINK_ORDER):.3f}")

sats = [(lid, result[lid]["sat_threshold"]) for lid in LINK_ORDER
        if result[lid]["sat_threshold"] is not None]
sats.sort(key=lambda x: x[1])
print(f"\nBottleneck ranking (earliest saturation, q_sat ≤ 2.5):")
for lid, q in sats:
    if q <= 2.5:
        meta = link_meta.get(lid, {})
        print(f"  {lid} {meta.get('from','?')}→{meta.get('to','?')}: "
              f"×{q:.2f}  (real_cong={result[lid]['real_cong']:.3f}, "
              f"v/c={result[lid]['vc_ratio']:.3f})")

never = [lid for lid in LINK_ORDER if result[lid]["sat_threshold"] is None]
if never:
    print(f"\nNever reaches severe (>×10): {never}")
