# app.py
import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np

st.set_page_config(page_title="Chennai Intersection Congestion - Schematic Map", layout="wide")

st.title("Chennai Metropolitan Area - Intersection Congestion (Schematic Map)")

# =========================================================
# Geometry helpers (no extra dependencies)
# =========================================================
def _lonlat_to_xy_m(lon, lat, lon0, lat0):
    """
    Equirectangular approximation: lon/lat -> meters around (lon0, lat0).
    Good enough for city-scale schematic alignment.
    """
    R = 6371000.0
    x = np.deg2rad(lon - lon0) * R * np.cos(np.deg2rad(lat0))
    y = np.deg2rad(lat - lat0) * R
    return x, y

def _xy_m_to_lonlat(x, y, lon0, lat0):
    R = 6371000.0
    lon = lon0 + np.rad2deg(x / (R * np.cos(np.deg2rad(lat0))))
    lat = lat0 + np.rad2deg(y / R)
    return lon, lat

def _snap_point_to_segment(px, py, ax, ay, bx, by):
    """
    Snap point P to segment AB in XY meters. Returns snapped point S and parameter t (0..1).
    """
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    denom = abx * abx + aby * aby
    if denom == 0:
        return ax, ay, 0.0
    t = (apx * abx + apy * aby) / denom
    t = max(0.0, min(1.0, t))
    sx = ax + t * abx
    sy = ay + t * aby
    return sx, sy, t

def snap_point_to_paths(lon, lat, paths, lon0, lat0):
    """
    Snap (lon,lat) to the nearest point on any polyline in `paths`.
    paths: list of polylines, each polyline is [[lon,lat], [lon,lat], ...]
    Returns snapped (lon,lat) and the local tangent direction (tx,ty) in meters (unit vector).
    """
    px, py = _lonlat_to_xy_m(lon, lat, lon0, lat0)

    best = None
    best_d2 = float("inf")

    for path in paths:
        xy = [_lonlat_to_xy_m(p[0], p[1], lon0, lat0) for p in path]
        for i in range(len(xy) - 1):
            ax, ay = xy[i]
            bx, by = xy[i + 1]
            sx, sy, _ = _snap_point_to_segment(px, py, ax, ay, bx, by)
            d2 = (px - sx) ** 2 + (py - sy) ** 2
            if d2 < best_d2:
                tx, ty = bx - ax, by - ay
                norm = np.hypot(tx, ty)
                if norm == 0:
                    tx, ty = 1.0, 0.0
                else:
                    tx, ty = tx / norm, ty / norm
                best_d2 = d2
                best = (sx, sy, tx, ty)

    sx, sy, tx, ty = best
    slon, slat = _xy_m_to_lonlat(sx, sy, lon0, lat0)
    return slon, slat, tx, ty

def offset_along_dir(lon, lat, dx, dy, distance_m, lon0, lat0):
    """
    Move from (lon,lat) by distance_m along direction (dx,dy) in meters (unit vector).
    """
    x, y = _lonlat_to_xy_m(lon, lat, lon0, lat0)
    ox = x + dx * distance_m
    oy = y + dy * distance_m
    return _xy_m_to_lonlat(ox, oy, lon0, lat0)


# =========================================================
# 1) Dummy major corridors (replace with your real major corridors / GeoJSON later)
#    NOTE: Paths must be [ [lon,lat], [lon,lat], ... ]
# =========================================================
corridors = pd.DataFrame([
    {"name": "Corridor-1", "path": [[80.18, 13.08], [80.26, 13.06], [80.30, 13.03]]},
    {"name": "Corridor-2", "path": [[80.19, 13.00], [80.22, 13.01], [80.26, 13.02]]},
])

corridor_paths = corridors["path"].tolist()

# Reference center for meter conversion (Chennai-ish center)
lon0, lat0 = 80.2500, 13.0500


# =========================================================
# 2) Dummy intersections (overall congestion) - will be snapped to corridor paths
# =========================================================
# congestion_level: 0.0 (free) -> 1.0 (oversaturated)
intersections_raw = pd.DataFrame([
    {"id": "JCT-001", "name": "Anna Salai / Mount Rd", "lat": 13.0604, "lon": 80.2496, "congestion_level": 0.85},
    {"id": "JCT-002", "name": "Guindy",               "lat": 13.0107, "lon": 80.2206, "congestion_level": 0.55},
    {"id": "JCT-003", "name": "Koyambedu",            "lat": 13.0732, "lon": 80.1960, "congestion_level": 0.25},
])

# Snap intersections onto nearest corridor polyline and store tangent (tx,ty)
snapped_rows = []
for _, r in intersections_raw.iterrows():
    slon, slat, tx, ty = snap_point_to_paths(r["lon"], r["lat"], corridor_paths, lon0, lat0)
    snapped_rows.append({**r.to_dict(), "lon": slon, "lat": slat, "tx": tx, "ty": ty})

intersections = pd.DataFrame(snapped_rows)

# =========================================================
# 3) Generate approach markers automatically (aligned with corridor tangent)
# =========================================================
# distance from intersection to place approach dots (meters)
distance_m = 35

approach_rows = []
for _, j in intersections.iterrows():
    tx, ty = float(j["tx"]), float(j["ty"])
    # Perpendicular direction
    px, py = -ty, tx

    # Dummy approach congestion levels (replace with ATCS approach-level values later)
    base = float(j["congestion_level"])
    levels = {
        "UP": min(1.0, base + 0.05),
        "DN": max(0.0, base - 0.10),
        "LT": min(1.0, base + 0.10),
        "RT": max(0.0, base - 0.05),
    }

    lon_up, lat_up = offset_along_dir(j["lon"], j["lat"], tx, ty,  distance_m, lon0, lat0)
    lon_dn, lat_dn = offset_along_dir(j["lon"], j["lat"], tx, ty, -distance_m, lon0, lat0)
    lon_lt, lat_lt = offset_along_dir(j["lon"], j["lat"], px, py,  distance_m, lon0, lat0)
    lon_rt, lat_rt = offset_along_dir(j["lon"], j["lat"], px, py, -distance_m, lon0, lat0)

    approach_rows += [
        {"jct_id": j["id"], "approach": "UP", "lon": lon_up, "lat": lat_up, "approach_congestion_level": levels["UP"]},
        {"jct_id": j["id"], "approach": "DN", "lon": lon_dn, "lat": lat_dn, "approach_congestion_level": levels["DN"]},
        {"jct_id": j["id"], "approach": "LT", "lon": lon_lt, "lat": lat_lt, "approach_congestion_level": levels["LT"]},
        {"jct_id": j["id"], "approach": "RT", "lon": lon_rt, "lat": lat_rt, "approach_congestion_level": levels["RT"]},
    ]

approaches = pd.DataFrame(approach_rows)

# =========================================================
# 4) Controls
# =========================================================
st.sidebar.header("Filters")
threshold = st.sidebar.slider("Oversaturation threshold", 0.0, 1.0, 0.80, 0.05)
show_only_oversat = st.sidebar.checkbox("Show only oversaturated intersections", value=False)

# approach marker distance tuning
distance_m_ui = st.sidebar.slider("Approach marker distance (m)", 10, 80, int(distance_m), 5)
if distance_m_ui != distance_m:
    distance_m = distance_m_ui
    # regenerate approaches with the new distance
    approach_rows = []
    for _, j in intersections.iterrows():
        tx, ty = float(j["tx"]), float(j["ty"])
        px, py = -ty, tx

        base = float(j["congestion_level"])
        levels = {
            "UP": min(1.0, base + 0.05),
            "DN": max(0.0, base - 0.10),
            "LT": min(1.0, base + 0.10),
            "RT": max(0.0, base - 0.05),
        }

        lon_up, lat_up = offset_along_dir(j["lon"], j["lat"], tx, ty,  distance_m, lon0, lat0)
        lon_dn, lat_dn = offset_along_dir(j["lon"], j["lat"], tx, ty, -distance_m, lon0, lat0)
        lon_lt, lat_lt = offset_along_dir(j["lon"], j["lat"], px, py,  distance_m, lon0, lat0)
        lon_rt, lat_rt = offset_along_dir(j["lon"], j["lat"], px, py, -distance_m, lon0, lat0)

        approach_rows += [
            {"jct_id": j["id"], "approach": "UP", "lon": lon_up, "lat": lat_up, "approach_congestion_level": levels["UP"]},
            {"jct_id": j["id"], "approach": "DN", "lon": lon_dn, "lat": lat_dn, "approach_congestion_level": levels["DN"]},
            {"jct_id": j["id"], "approach": "LT", "lon": lon_lt, "lat": lat_lt, "approach_congestion_level": levels["LT"]},
            {"jct_id": j["id"], "approach": "RT", "lon": lon_rt, "lat": lat_rt, "approach_congestion_level": levels["RT"]},
        ]
    approaches = pd.DataFrame(approach_rows)

df_jct = intersections.copy()
if show_only_oversat:
    df_jct = df_jct[df_jct["congestion_level"] >= threshold].reset_index(drop=True)

# =========================================================
# 5) Color helper: green -> red (simple)
# =========================================================
def level_to_rgba(level: float):
    r = int(220 * level)
    g = int(200 * (1 - level))
    b = 0
    return [r, g, b, 180]

df_jct["color"] = df_jct["congestion_level"].apply(level_to_rgba)
df_jct["radius"] = (200 + 1200 * df_jct["congestion_level"]).astype(int)

approaches["color"] = approaches["approach_congestion_level"].apply(level_to_rgba)
approaches["radius"] = (80 + 400 * approaches["approach_congestion_level"]).astype(int)

# =========================================================
# 6) PyDeck Layers
#    - Base map hidden: map_style = None
# =========================================================
corridor_layer = pdk.Layer(
    "PathLayer",
    corridors,
    get_path="path",
    get_width=10,          # thicker line
    width_min_pixels=4,
    get_color=[30, 144, 255, 200],
    pickable=True,
)

intersection_layer = pdk.Layer(
    "ScatterplotLayer",
    df_jct,
    get_position="[lon, lat]",
    get_fill_color="color",
    get_radius="radius",
    pickable=True,
)

approach_layer = pdk.Layer(
    "ScatterplotLayer",
    approaches,
    get_position="[lon, lat]",
    get_fill_color="color",
    get_radius="radius",
    pickable=True,
)

# View: center around Chennai
view_state = pdk.ViewState(latitude=13.0500, longitude=80.2500, zoom=10, pitch=0, bearing=0)

tooltip = {
    "html": """
    <b>ID:</b> {id}{jct_id}<br/>
    <b>Name:</b> {name}<br/>
    <b>Approach:</b> {approach}<br/>
    <b>Congestion:</b> {congestion_level}{approach_congestion_level}
    """,
    "style": {"backgroundColor": "black", "color": "white"},
}

deck = pdk.Deck(
    layers=[corridor_layer, intersection_layer, approach_layer],
    initial_view_state=view_state,
    map_style=None,  # hide base map
    tooltip=tooltip,
)

st.pydeck_chart(deck, use_container_width=True)

# =========================================================
# 7) Oversaturation list (incident candidates)
# =========================================================
st.subheader("Oversaturated Intersections (incident candidates)")
alerts = intersections[intersections["congestion_level"] >= threshold][["id", "name", "congestion_level"]].sort_values(
    "congestion_level", ascending=False
)
st.dataframe(alerts, use_container_width=True)

# Debug (optional)
with st.expander("Debug: snapped intersection coordinates"):
    st.dataframe(intersections[["id", "name", "lon", "lat", "tx", "ty", "congestion_level"]], use_container_width=True)
