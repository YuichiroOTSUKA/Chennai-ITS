"""
SUMO simulation pipeline for Chennai ITS.

Pipeline:
  1. Download OSM highway data for Chennai urban bbox (Overpass API)
  2. Build SUMO network with netconvert
  3. Generate random trip demand × 3 scenarios (baseline / low / high)
  4. Run SUMO × 3 scenarios, output per-edge speed every 120s
  5. Parse edge output → aggregate by schematic link → sumo_scenarios.json

Scenarios (30-min window matching 16:10–16:40 IST bus probe):
  baseline   – moderate demand (calibrated to evening peak)
  low_demand – 50% of baseline (off-peak analog)
  high_demand – 180% of baseline (extreme peak surge)

Output: api/data/sumo_scenarios.json
{
  "time_labels": ["16:10", …],          // 15 × 2-min bins
  "scenarios": {
    "baseline":    {"links": {"l01": [0.42,…], …}, "net_ts": [0.35,…]},
    "low_demand":  {…},
    "high_demand": {…}
  }
}
"""

import json, math, os, subprocess, sys, tempfile, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR  = Path(__file__).parent / "api" / "data"
WORK_DIR  = Path(__file__).parent / "sumo_workspace"
WORK_DIR.mkdir(exist_ok=True)

SUMO_HOME   = os.environ.get("SUMO_HOME", "")
NETCONVERT  = "netconvert"
SUMO_BIN    = "sumo"
RANDOM_TRIPS = Path(SUMO_HOME) / "tools" / "randomTrips.py" if SUMO_HOME else None

# ── Chennai bbox (trunk+primary+secondary, urban core) ────────────────────────
BBOX = (12.85, 79.95, 13.20, 80.30)   # south, west, north, east

# ── Simulation params ─────────────────────────────────────────────────────────
SIM_DURATION_S  = 1800          # 30 min (matching probe window)
OUTPUT_INTERVAL = 120           # 2-min edge output
FREE_KMH        = 30.0          # reference free-flow speed
FREE_MS         = FREE_KMH / 3.6

# Period = seconds between vehicle spawns.
# baseline ≈ 1 vehicle / 1.5s ≈ 2400 veh/h across network
SCENARIOS = {
    "baseline":    1.5,
    "low_demand":  3.0,    # 50% of baseline
    "high_demand": 0.83,   # ~180% of baseline
}

N_BINS      = 15   # 15 × 120s = 1800s
BIN_MINUTES = 2
START_IST   = (16, 10)   # hours, minutes


def bin_to_ist(idx: int) -> str:
    total_m = START_IST[0] * 60 + START_IST[1] + idx * BIN_MINUTES
    return f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"


def speed_to_cong(v_ms: float) -> float:
    return round(max(0.05, min(0.98, 1.0 - v_ms / FREE_MS)), 3)


# ── Step 1: Download OSM ──────────────────────────────────────────────────────
def download_osm():
    osm_path = WORK_DIR / "chennai.osm"
    if osm_path.exists() and osm_path.stat().st_size > 100_000:
        print(f"OSM already exists ({osm_path.stat().st_size/1e6:.1f} MB), skipping download")
        return osm_path

    s, w, n, e = BBOX
    query = f"""[out:xml][timeout:90];
(
  way["highway"~"^(motorway|trunk|primary|secondary)(|_link)$"]({s},{w},{n},{e});
  node(w);
);
out body;
"""
    url = "https://overpass-api.de/api/interpreter"
    print("Downloading OSM from Overpass API …")
    import urllib.parse
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "chennai-its/1.0 (research)",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = resp.read()
    osm_path.write_bytes(data)
    print(f"  Downloaded {len(data)/1e6:.1f} MB → {osm_path}")
    return osm_path


# ── Step 2: Build SUMO network ────────────────────────────────────────────────
def build_network(osm_path: Path) -> Path:
    net_path = WORK_DIR / "chennai.net.xml"
    if net_path.exists():
        print(f"Network already exists: {net_path}")
        return net_path

    print("Running netconvert …")
    cmd = [
        NETCONVERT,
        "--osm-files",        str(osm_path),
        "--output-file",      str(net_path),
        "--geometry.remove",
        "--roundabouts.guess",
        "--ramps.guess",
        "--lefthand",
        "--junctions.join",
        "--tls.guess",
        "--no-internal-links",
        "--osm.all-attributes",
        "--keep-edges.by-vclass", "passenger,bus",
        "--verbose",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("netconvert stderr:", result.stderr[-2000:])
        raise RuntimeError("netconvert failed")
    print(f"  Network built: {net_path}")
    return net_path


# ── Step 3: Generate random trips ─────────────────────────────────────────────
def generate_trips(net_path: Path, scenario: str, period: float) -> Path:
    trip_path = WORK_DIR / f"trips_{scenario}.xml"
    rou_path  = WORK_DIR / f"routes_{scenario}.xml"

    if rou_path.exists():
        print(f"  Routes exist: {rou_path}")
        return rou_path

    print(f"  Generating trips for '{scenario}' (period={period}s) …")

    # randomTrips.py
    rt_script = RANDOM_TRIPS or Path(SUMO_HOME) / "tools" / "randomTrips.py"
    cmd_trips = [
        sys.executable, str(rt_script),
        "-n", str(net_path),
        "-o", str(trip_path),
        "-b", "0",
        "-e", str(SIM_DURATION_S),
        "-p", str(period),
        "--vehicle-class", "passenger",
        "--validate",
        "--seed", "42",
    ]
    r = subprocess.run(cmd_trips, capture_output=True, text=True,
                       env={**os.environ, "SUMO_HOME": SUMO_HOME})
    if r.returncode != 0:
        print("randomTrips stderr:", r.stderr[-1000:])
        raise RuntimeError("randomTrips failed")

    # duarouter: trips → routes
    cmd_route = [
        "duarouter",
        "-n", str(net_path),
        "-t", str(trip_path),
        "-o", str(rou_path),
        "--no-step-log",
        "--ignore-errors",
        "--seed", "42",
    ]
    r2 = subprocess.run(cmd_route, capture_output=True, text=True)
    if r2.returncode != 0:
        # Try using trips directly without routing
        print("  duarouter failed, using trip file directly …")
        trip_path.rename(rou_path)

    print(f"  Routes: {rou_path}")
    return rou_path


# ── Step 4: Run SUMO ──────────────────────────────────────────────────────────
def run_sumo(net_path: Path, rou_path: Path, scenario: str) -> Path:
    out_path = WORK_DIR / f"edgedata_{scenario}.xml"
    if out_path.exists():
        print(f"  Edge output exists: {out_path}")
        return out_path

    # Write edgeData additional file (SUMO 1.x approach)
    add_path = WORK_DIR / f"edgedata_add_{scenario}.xml"
    add_path.write_text(
        f'<additional>\n'
        f'  <edgeData id="ed_{scenario}" file="{out_path}" period="{OUTPUT_INTERVAL}"/>\n'
        f'</additional>\n'
    )

    print(f"  Running SUMO for '{scenario}' …")
    cmd = [
        SUMO_BIN,
        "-n", str(net_path),
        "-r", str(rou_path),
        "-a", str(add_path),
        "--duration-log.disable",
        "--no-step-log",
        "--time-to-teleport", "-1",
        "--begin", "0",
        "--end",   str(SIM_DURATION_S),
        "--seed", "42",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 and not out_path.exists():
        print("SUMO stderr:", r.stderr[-2000:])
        raise RuntimeError(f"SUMO failed for {scenario}")
    print(f"  Output: {out_path}")
    return out_path


# ── Step 5: Parse edge output → link aggregation ──────────────────────────────
def parse_edgedata(out_path: Path, link_mapping: dict) -> list:
    """
    Parse SUMO meandata XML → per-bin per-link congestion list.
    Returns list of 15 dicts: {link_id: cong_float}
    """
    tree = ET.parse(str(out_path))
    root = tree.getroot()

    # Each <interval begin=... end=...> = one 120s bin
    bins = []
    for interval in sorted(root.findall("interval"), key=lambda el: float(el.get("begin", 0))):
        edge_speeds: dict[str, list] = defaultdict(list)
        for edge in interval.findall("edge"):
            eid   = edge.get("id", "")
            speed = edge.get("speed")
            if speed is None or eid.startswith(":"):
                continue
            # Strip leading '-' (reverse direction) and '#N' segment suffix
            osm_id = eid.lstrip("-").split("#")[0]
            # Skip SUMO-generated auxiliary edges
            if not osm_id.isdigit():
                continue
            try:
                v = float(speed)
            except ValueError:
                continue
            if v < 0:
                continue
            edge_speeds[osm_id].append(v)

        # Aggregate to schematic links
        link_vals: dict[str, list] = defaultdict(list)
        for osm_id, speeds in edge_speeds.items():
            if osm_id in link_mapping:
                lid = link_mapping[osm_id]["link_id"]
                avg_v = sum(speeds) / len(speeds)
                link_vals[lid].append(avg_v)

        link_cong = {}
        for lid, vals in link_vals.items():
            v_avg = sum(vals) / len(vals)
            link_cong[lid] = speed_to_cong(v_avg)

        bins.append(link_cong)

    return bins


# ── Step 6: Fill missing bins / links ─────────────────────────────────────────
LINK_ORDER = [f"l{i:02d}" for i in range(1, 65)]

def fill_bins(bins: list, fallback_cong: float = 0.35) -> list:
    """Ensure exactly N_BINS, all 64 links present."""
    # Trim or pad to N_BINS
    while len(bins) < N_BINS:
        bins.append({})
    bins = bins[:N_BINS]

    for b in bins:
        for lid in LINK_ORDER:
            if lid not in b:
                b[lid] = fallback_cong

    return bins


def bins_to_link_ts(bins: list) -> dict:
    """Convert list-of-dicts → dict of link_id → [15 values]"""
    ts: dict[str, list] = {lid: [] for lid in LINK_ORDER}
    for b in bins:
        for lid in LINK_ORDER:
            ts[lid].append(b.get(lid, 0.35))
    return ts


def net_ts(bins: list) -> list:
    """Network-wide average congestion per bin."""
    result = []
    for b in bins:
        vals = [v for v in b.values() if v is not None]
        result.append(round(sum(vals) / len(vals), 3) if vals else 0.35)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Load link mapping (OSM way id str → {link_id, fraction})
    link_mapping: dict = json.loads((DATA_DIR / "link_mapping.json").read_text())
    print(f"Link mapping: {len(link_mapping)} segments")

    # Step 1: OSM
    osm_path = download_osm()

    # Step 2: Network
    net_path = build_network(osm_path)

    # Steps 3–5: Per scenario
    results = {}
    for scenario, period in SCENARIOS.items():
        print(f"\n=== Scenario: {scenario} (period={period}s) ===")
        rou_path = generate_trips(net_path, scenario, period)
        out_path = run_sumo(net_path, rou_path, scenario)
        bins = parse_edgedata(out_path, link_mapping)
        bins = fill_bins(bins)
        results[scenario] = {
            "links":  bins_to_link_ts(bins),
            "net_ts": net_ts(bins),
        }
        print(f"  Net avg cong: {results[scenario]['net_ts']}")

    # Save
    time_labels = [bin_to_ist(i) for i in range(N_BINS)]
    out = {
        "time_labels": time_labels,
        "scenarios":   results,
    }
    out_file = DATA_DIR / "sumo_scenarios.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False))
    print(f"\nWrote {out_file}")

    # Summary
    for sc, v in results.items():
        avg = sum(v["net_ts"]) / len(v["net_ts"])
        print(f"  {sc:12s}: avg_cong={avg:.3f}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, SUMO_HOME + "/tools")
    main()
