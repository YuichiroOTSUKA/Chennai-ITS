# app.py
import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np

st.set_page_config(page_title="Chennai Intersection Congestion - Schematic Map", layout="wide")

st.title("Chennai Metropolitan Area - Intersection Congestion (Schematic Map)")

# -----------------------------
# 1) Dummy data (replace with ATCS-derived dataset later)
# -----------------------------
# Intersections (overall congestion)
# congestion_level: 0.0 (free) -> 1.0 (oversaturated)
intersections = pd.DataFrame([
    {"id": "JCT-001", "name": "Anna Salai / Mount Rd", "lat": 13.0604, "lon": 80.2496, "congestion_level": 0.85},
    {"id": "JCT-002", "name": "Guindy",              "lat": 13.0107, "lon": 80.2206, "congestion_level": 0.55},
    {"id": "JCT-003", "name": "Koyambedu",           "lat": 13.0732, "lon": 80.1960, "congestion_level": 0.25},
])

# Approach-level congestion (example: N/E/S/W)
# approach_congestion_level: 0.0 -> 1.0
approaches = pd.DataFrame([
    {"jct_id": "JCT-001", "approach": "N", "lat": 13.0612, "lon": 80.2496, "approach_congestion_level": 0.90},
    {"jct_id": "JCT-001", "approach": "E", "lat": 13.0604, "lon": 80.2505, "approach_congestion_level": 0.80},
    {"jct_id": "JCT-001", "approach": "S", "lat": 13.0596, "lon": 80.2496, "approach_congestion_level": 0.70},
    {"jct_id": "JCT-001", "approach": "W", "lat": 13.0604, "lon": 80.2487, "approach_congestion_level": 0.95},

    {"jct_id": "JCT-002", "approach": "N", "lat": 13.0115, "lon": 80.2206, "approach_congestion_level": 0.60},
    {"jct_id": "JCT-002", "approach": "E", "lat": 13.0107, "lon": 80.2215, "approach_congestion_level": 0.45},
    {"jct_id": "JCT-002", "approach": "S", "lat": 13.0099, "lon": 80.2206, "approach_congestion_level": 0.50},
    {"jct_id": "JCT-002", "approach": "W", "lat": 13.0107, "lon": 80.2197, "approach_congestion_level": 0.65},
])

# Major corridors (schematic thick lines) - example as simple line segments.
# In practice, use GeoJSON polylines from your defined major corridors.
corridors = pd.DataFrame([
    {"path": [[80.18, 13.08], [80.26, 13.06], [80.30, 13.03]]},  # lon/lat pairs
    {"path": [[80.19, 13.00], [80.22, 13.01], [80.26, 13.02]]},
])

# -----------------------------
# 2) Controls
# -----------------------------
st.sidebar.header("Filters")
threshold = st.sidebar.slider("Oversaturation threshold", 0.0, 1.0, 0.80, 0.05)
show_only_oversat = st.sidebar.checkbox("Show only oversaturated intersections", value=False)

df_jct = intersections.copy()
if show_only_oversat:
    df_jct = df_jct[df_jct["congestion_level"] >= threshold].reset_index(drop=True)

# Color helper: green -> yellow -> red (simple)
def level_to_rgb(level: float):
    # 0: green (0,200,0) ; 1: red (220,0,0)
    r = int(220 * level)
    g = int(200 * (1 - level))
    b = 0
    return [r, g, b, 180]

df_jct["color"] = df_jct["congestion_level"].apply(level_to_rgb)
df_jct["radius"] = (200 + 1200 * df_jct["congestion_level"]).astype(int)

approaches["color"] = approaches["approach_congestion_level"].apply(level_to_rgb)
approaches["radius"] = (80 + 400 * approaches["approach_congestion_level"]).astype(int)

# -----------------------------
# 3) PyDeck Layers
#    - Base map hidden: map_style = None
# -----------------------------
corridor_layer = pdk.Layer(
    "PathLayer",
    corridors,
    get_path="path",
    get_width=8,              # thick line
    width_min_pixels=3,
    get_color=[30, 144, 255, 180],  # corridor color (you can standardize)
    pickable=False,
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
    <b>ID:</b> {id}<br/>
    <b>Name:</b> {name}<br/>
    <b>Congestion:</b> {congestion_level}
    """,
    "style": {"backgroundColor": "black", "color": "white"},
}

# Approach tooltip (different fields). PyDeck uses single tooltip; keep simple:
tooltip2 = {
    "html": """
    <b>JCT:</b> {jct_id}<br/>
    <b>Approach:</b> {approach}<br/>
    <b>Congestion:</b> {approach_congestion_level}
    """,
    "style": {"backgroundColor": "black", "color": "white"},
}

# Render: to allow both tooltips, we show one combined tooltip (approach fields may be empty for jct layer)
combined_tooltip = {
    "html": """
    <b>JCT:</b> {id}{jct_id}<br/>
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
    tooltip=combined_tooltip,
)

st.pydeck_chart(deck, use_container_width=True)

# -----------------------------
# 4) Alerts list (for operations / incident mgmt)
# -----------------------------
st.subheader("Oversaturated Intersections (as candidates for incident)")
alerts = intersections[intersections["congestion_level"] >= threshold][["id", "name", "congestion_level"]].sort_values("congestion_level", ascending=False)
st.dataframe(alerts, use_container_width=True)
