# app.py
# WMS Landing Page (Operator-Centric) - Streamlit Prototype
# Purpose: A “beautiful”, operationally useful landing screen with dummy data.
# - System Health / Comms / Alarms / Modes / Direction Targets / Action List / Drill-down
# - Single-file implementation for easiest demo.
#
# Run:
#   pip install streamlit pandas numpy plotly
#   streamlit run app.py

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import plotly.express as px

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="WMS Landing (Ops)", layout="wide")

# -----------------------------
# Styling (simple “polished” UI)
# -----------------------------
CSS = """
<style>
:root{
  --bg:#0b1220;
  --card:#111b2d;
  --card2:#0f172a;
  --text:#e6edf7;
  --muted:#9fb0c7;
  --line:#24324a;
  --ok:#22c55e;
  --warn:#f59e0b;
  --alarm:#ef4444;
  --offline:#64748b;
  --info:#60a5fa;
  --accent:#7c3aed;
}

html, body, [class*="css"]  {
  color: var(--text) !important;
}

.stApp {
  background: radial-gradient(1200px 600px at 20% 0%, #162340 0%, var(--bg) 55%, #070b14 100%) !important;
}

.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

hr { border-color: var(--line) !important; }

.small-muted { color: var(--muted); font-size: 12px; }
.h-title { font-size: 20px; font-weight: 700; letter-spacing: 0.2px; }
.h-sub { color: var(--muted); font-size: 13px; }

.card {
  background: rgba(17, 27, 45, 0.82);
  border: 1px solid rgba(36, 50, 74, 0.8);
  border-radius: 16px;
  padding: 14px 14px 12px 14px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.25);
}

.card-tight { padding: 12px 12px 10px 12px; }

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid rgba(255,255,255,0.08);
}

.dot {
  width: 8px; height: 8px; border-radius: 50%;
  display: inline-block;
}

.kpi-title { color: var(--muted); font-size: 12px; margin-bottom: 2px; }
.kpi-value { font-size: 22px; font-weight: 800; line-height: 1.1; }
.kpi-foot { color: var(--muted); font-size: 11px; margin-top: 4px; }

.row { display: flex; gap: 12px; flex-wrap: wrap; }
.col { flex: 1 1 220px; min-width: 220px; }

.table-note { color: var(--muted); font-size: 11px; }

.stDataFrame, .stTable { background: transparent !important; }

section[data-testid="stSidebar"] {
  background: rgba(8, 12, 22, 0.70);
  border-right: 1px solid rgba(36, 50, 74, 0.8);
}

div[data-testid="stSidebar"] .stMarkdown { color: var(--text) !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# -----------------------------
# Constants / helpers
# -----------------------------
STATUS = ["OK", "WARN", "ALARM", "OFFLINE"]
STATUS_COLOR = {
    "OK": "#22c55e",
    "WARN": "#f59e0b",
    "ALARM": "#ef4444",
    "OFFLINE": "#64748b",
}
MODE = ["AUTO", "MANUAL", "PROGRAM"]
MODE_COLOR = {
    "AUTO": "#60a5fa",
    "MANUAL": "#a78bfa",
    "PROGRAM": "#34d399",
}

SYS_STATE = ["Active", "Degraded", "Partial Down", "Down"]

def badge(label: str, color: str):
    return f"""
    <span class="badge" style="background:rgba(255,255,255,0.04);">
      <span class="dot" style="background:{color};"></span>
      {label}
    </span>
    """

def system_state_from_counts(offline_cnt, alarm_cnt, total):
    # Simple rule for prototype
    if offline_cnt >= max(1, int(total * 0.4)):
        return "Down"
    if offline_cnt > 0 and alarm_cnt > 0:
        return "Partial Down"
    if alarm_cnt > 0 or offline_cnt > 0:
        return "Degraded"
    return "Active"

def freshness_label(staleness_s: int):
    if staleness_s <= 60:
        return ("Fresh", "#22c55e")
    if staleness_s <= 300:
        return ("Slight Delay", "#f59e0b")
    return ("Stale", "#ef4444")

def dev_level(dev_pct: float):
    a = abs(dev_pct)
    if a >= 15:
        return ("High", "#ef4444")
    if a >= 8:
        return ("Medium", "#f59e0b")
    return ("Low", "#22c55e")

# -----------------------------
# Dummy data generators
# -----------------------------
def gen_nodes(seed: int):
    random.seed(seed)

    nodes = [
        {"id": "HW", "label": "Headworks", "type": "Hub"},
        {"id": "B.Sd.1", "label": "B.Sd.1", "type": "TC"},
        {"id": "B.Cpl.5", "label": "B.Cpl.5", "type": "TC"},
        {"id": "B.Sd.3", "label": "B.Sd.3", "type": "SPC"},
        {"id": "B.Gs.11", "label": "B.Gs.11", "type": "SPC"},
        {"id": "B.Cpl.1.4", "label": "B.Cpl.1.4", "type": "SPC"},
        {"id": "B.Bt.15", "label": "B.Bt.15", "type": "SPC"},
        {"id": "B.Ut.10", "label": "B.Ut.10", "type": "SPC"},
        {"id": "B.Bt.4", "label": "B.Bt.4", "type": "Gate"},
        {"id": "B.Bt.21", "label": "B.Bt.21", "type": "Gate"},
        {"id": "B.Bt.9", "label": "B.Bt.9", "type": "Gate"},
        {"id": "B.Bt.17", "label": "B.Bt.17", "type": "Gate"},
    ]

    # Assign status/mode and operational metadata
    for n in nodes:
        if n["id"] == "HW":
            n["status"] = "OK"
            n["mode"] = "AUTO"
        else:
            n["status"] = random.choices(STATUS, weights=[72, 14, 10, 4])[0]
            n["mode"] = random.choices(MODE, weights=[65, 22, 13])[0]

        # comm / data freshness
        n["last_update"] = datetime.now() - timedelta(seconds=random.randint(5, 2400))
        n["comm_rtt_ms"] = None if n["status"] == "OFFLINE" else random.randint(20, 520)

        # manual duration (if manual)
        if n["mode"] == "MANUAL":
            n["manual_since_min"] = random.randint(5, 360)
        else:
            n["manual_since_min"] = 0

    edges = [
        ("HW", "B.Sd.1"),
        ("HW", "B.Cpl.5"),
        ("HW", "B.Sd.3"),
        ("B.Sd.3", "B.Cpl.1.4"),
        ("B.Cpl.1.4", "B.Bt.15"),
        ("B.Bt.15", "B.Ut.10"),
        ("B.Cpl.5", "B.Gs.11"),
        ("B.Gs.11", "B.Bt.4"),
        ("B.Gs.11", "B.Bt.21"),
        ("B.Gs.11", "B.Bt.9"),
        ("B.Gs.11", "B.Bt.17"),
    ]
    return nodes, edges

def gen_alarms(nodes, seed: int):
    random.seed(seed + 1000)
    now = datetime.now()
    alarm_types = [
        ("COMM_LOSS", "Communication loss detected"),
        ("COMM_DELAY", "Communication latency threshold exceeded"),
        ("WL_HIGH", "Water level high alarm"),
        ("WL_LOW", "Water level low alarm"),
        ("MODE_MISMATCH", "Local/Remote mode mismatch"),
        ("POWER", "Power supply abnormal"),
        ("SENSOR_FAULT", "Sensor fault / out-of-range"),
    ]
    rows = []
    for _ in range(36):
        n = random.choice(nodes[1:])  # exclude HW for realism
        sev = random.choices(["CRITICAL", "WARNING"], weights=[35, 65])[0]
        ack = random.choices([True, False], weights=[68, 32])[0]
        t, msg = random.choice(alarm_types)
        rows.append({
            "Time": now - timedelta(minutes=random.randint(1, 2880)),
            "Station": n["id"],
            "Severity": sev,
            "Type": t,
            "Message": f"{msg} at {n['id']}",
            "Ack": "Yes" if ack else "No",
        })
    df = pd.DataFrame(rows).sort_values("Time", ascending=False).reset_index(drop=True)
    return df

def gen_direction_targets(seed: int):
    random.seed(seed + 2000)
    directions = ["Direction A", "Direction B", "Direction C", "Direction D"]
    rows = []
    for d in directions:
        q_plan = random.randint(70, 150)
        q_act = q_plan + random.randint(-25, 28)
        dev = (q_act - q_plan) / q_plan * 100
        rows.append({
            "Direction": d,
            "Q_plan (m³/s)": float(q_plan),
            "Q_actual (m³/s)": float(q_act),
            "Deviation (%)": round(dev, 1),
        })
    df = pd.DataFrame(rows)
    df["Deviation Level"] = df["Deviation (%)"].apply(lambda x: dev_level(x)[0])
    return df

def gen_trend(seed: int, hours=24):
    random.seed(seed + 3000)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    ts = [now - timedelta(hours=(hours - 1 - i)) for i in range(hours)]
    # generate stable-ish plan and noisy actual
    base_plan = random.randint(85, 135)
    plan = np.array([base_plan + int(4*np.sin(i/3)) for i in range(hours)], dtype=float)
    actual = plan + np.random.normal(0, 8, size=hours)
    df = pd.DataFrame({"Time": ts, "Q_plan": plan, "Q_actual": actual})
    df["Deviation_%"] = (df["Q_actual"] - df["Q_plan"]) / df["Q_plan"] * 100
    return df

# -----------------------------
# Sidebar (Operational controls)
# -----------------------------
st.sidebar.markdown("### WMS Operator Panel")
st.sidebar.caption("Landing page prototype (dummy data).")

if "seed" not in st.session_state:
    st.session_state.seed = 10

col_sb1, col_sb2 = st.sidebar.columns([1, 1])
with col_sb1:
    if st.button("Refresh", use_container_width=True):
        st.session_state.seed += 1
with col_sb2:
    auto = st.checkbox("Auto-refresh", value=False)

refresh_rate_s = st.sidebar.slider("Auto-refresh interval (s)", 5, 60, 15, disabled=not auto)

st.sidebar.markdown("---")
st.sidebar.markdown("**Filters**")
flt_status = st.sidebar.multiselect("Status", STATUS, default=STATUS)
flt_mode = st.sidebar.multiselect("Mode", MODE, default=MODE)
search = st.sidebar.text_input("Search Station ID", "")

st.sidebar.markdown("---")
season = st.sidebar.selectbox("Operational Phase", ["Dry", "Wet", "Flood"], index=0)
special_mode = st.sidebar.selectbox("Special Operation", ["Normal", "Drought Response", "Flood Alert"], index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("**Thresholds (for actions)**")
thr_stale_s = st.sidebar.number_input("Stale data threshold (s)", min_value=60, max_value=7200, value=600, step=60)
thr_manual_min = st.sidebar.number_input("Manual duration threshold (min)", min_value=5, max_value=1440, value=120, step=5)
thr_dev_pct = st.sidebar.number_input("Direction deviation threshold (%)", min_value=1, max_value=50, value=10, step=1)

if auto:
    st.sidebar.caption(f"Auto-refresh enabled: every {refresh_rate_s} seconds.")
    st.autorefresh(interval=refresh_rate_s * 1000, key="wms_autorefresh")

# -----------------------------
# Data build
# -----------------------------
seed = st.session_state.seed
nodes, edges = gen_nodes(seed)
alarms = gen_alarms(nodes, seed)
direction_df = gen_direction_targets(seed)
trend_df = gen_trend(seed, hours=24)

# Apply filters
filtered_nodes = []
for n in nodes:
    if n["status"] not in flt_status:
        continue
    if n["mode"] not in flt_mode:
        continue
    if search and search.lower() not in n["id"].lower():
        continue
    filtered_nodes.append(n)

filtered_ids = {n["id"] for n in filtered_nodes}
filtered_edges = [(a, b) for (a, b) in edges if a in filtered_ids and b in filtered_ids]

# KPIs
total_nodes = len(nodes)
ok_cnt = sum(1 for n in nodes if n["status"] == "OK")
warn_cnt = sum(1 for n in nodes if n["status"] == "WARN")
alarm_cnt = sum(1 for n in nodes if n["status"] == "ALARM")
offline_cnt = sum(1 for n in nodes if n["status"] == "OFFLINE")

auto_cnt = sum(1 for n in nodes if n["mode"] == "AUTO")
man_cnt = sum(1 for n in nodes if n["mode"] == "MANUAL")
prog_cnt = sum(1 for n in nodes if n["mode"] == "PROGRAM")

critical_cnt = int((alarms["Severity"] == "CRITICAL").sum())
warning_cnt = int((alarms["Severity"] == "WARNING").sum())
unack_cnt = int((alarms["Ack"] == "No").sum())
oldest_unack = alarms.loc[alarms["Ack"] == "No", "Time"].max() if unack_cnt > 0 else None  # latest among unack? adjust below
if unack_cnt > 0:
    oldest_unack = alarms.loc[alarms["Ack"] == "No", "Time"].min()

# Freshness
last_update_global = max(n["last_update"] for n in nodes)
staleness_s = int((datetime.now() - last_update_global).total_seconds())
fresh_label, fresh_color = freshness_label(staleness_s)

sys_state = system_state_from_counts(offline_cnt, alarm_cnt, total_nodes)

# -----------------------------
# Action list (operational suggestions)
# -----------------------------
actions = []

# 1) Offline stations
offline_list = [n["id"] for n in nodes if n["status"] == "OFFLINE"]
if offline_list:
    actions.append(("CRITICAL", f"Communication loss: {len(offline_list)} station(s) OFFLINE", offline_list))

# 2) Unack alarms
if unack_cnt > 0:
    actions.append(("WARNING" if unack_cnt < 5 else "CRITICAL", f"{unack_cnt} unacknowledged alarm(s) require acknowledgement", []))

# 3) Stale data
if staleness_s >= thr_stale_s:
    actions.append(("WARNING" if staleness_s < thr_stale_s * 2 else "CRITICAL",
                    f"System data freshness is STALE ({staleness_s}s since last update)", []))

# 4) Long manual
long_manual = [n["id"] for n in nodes if n["mode"] == "MANUAL" and n["manual_since_min"] >= thr_manual_min]
if long_manual:
    actions.append(("WARNING", f"Manual operation exceeding {thr_manual_min} min: {len(long_manual)} gate(s)", long_manual))

# 5) Direction deviation
dir_over = direction_df.loc[direction_df["Deviation (%)"].abs() >= thr_dev_pct].sort_values("Deviation (%)", key=lambda s: s.abs(), ascending=False)
if len(dir_over) > 0:
    top = dir_over.iloc[0]
    actions.append(("WARNING" if abs(top["Deviation (%)"]) < thr_dev_pct * 1.5 else "CRITICAL",
                    f"Direction deviation exceeds {thr_dev_pct}%: {top['Direction']} ({top['Deviation (%)']}%)", [top["Direction"]]))

# If no actions
if not actions:
    actions.append(("OK", "No urgent action suggested (based on current thresholds).", []))

# -----------------------------
# Graphviz DOT (status-aware schema)
# -----------------------------
def dot_schema(nodes_in, edges_in, highlight=None):
    # More “card-like” graph style with node colors.
    lines = [
        "digraph G {",
        "rankdir=LR;",
        "splines=true;",
        "nodesep=0.55;",
        "ranksep=0.75;",
        'graph [bgcolor="transparent"];',
        'node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=10 margin="0.08,0.06"];',
        'edge [penwidth=2 arrowsize=0.7];',
    ]
    node_map = {n["id"]: n for n in nodes_in}

    def node_label(n):
        s = n["status"]
        m = n["mode"]
        return f'{n["id"]}\\n{n["type"]} | {m}'

    for n in nodes_in:
        fill = STATUS_COLOR.get(n["status"], "#64748b")
        penw = 3 if highlight and n["id"] == highlight else 1
        # Slightly different fill for manual (overlay concept via label only)
        lines.append(
            f'"{n["id"]}" [label="{node_label(n)}" fillcolor="{fill}" color="#0b1220" penwidth={penw} fontcolor="#0b1220"];'
        )

    for a, b in edges_in:
        sa = node_map[a]["status"]
        sb = node_map[b]["status"]
        if "OFFLINE" in (sa, sb):
            ec, stl = "#64748b", "dashed"
        elif "ALARM" in (sa, sb):
            ec, stl = "#ef4444", "bold"
        elif "WARN" in (sa, sb):
            ec, stl = "#f59e0b", "bold"
        else:
            ec, stl = "#60a5fa", "solid"
        lines.append(f'"{a}" -> "{b}" [color="{ec}" style="{stl}"];')

    lines.append("}")
    return "\n".join(lines)

# -----------------------------
# Header row
# -----------------------------
now = datetime.now()
hdr_left, hdr_mid, hdr_right = st.columns([3, 6, 3], vertical_alignment="center")

with hdr_left:
    st.markdown(
        f"""
        <div class="card">
          <div class="h-title">WMS Landing Page</div>
          <div class="h-sub">Operator-centric overview and actions</div>
          <div style="margin-top:10px;">
            {badge(f"System: {sys_state}", {"Active":"#22c55e","Degraded":"#f59e0b","Partial Down":"#ef4444","Down":"#ef4444"}[sys_state])}
            &nbsp; {badge(f"Freshness: {fresh_label}", fresh_color)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with hdr_mid:
    st.markdown(
        f"""
        <div class="card">
          <div class="row">
            <div class="col">
              <div class="kpi-title">Local Time</div>
              <div class="kpi-value">{now.strftime('%d/%m/%Y %H:%M:%S')}</div>
              <div class="kpi-foot">Phase: <b>{season}</b> / Special: <b>{special_mode}</b></div>
            </div>
            <div class="col">
              <div class="kpi-title">Last Data Update</div>
              <div class="kpi-value">{last_update_global.strftime('%H:%M:%S')}</div>
              <div class="kpi-foot">Staleness: <b>{staleness_s}s</b> (threshold: {thr_stale_s}s)</div>
            </div>
            <div class="col">
              <div class="kpi-title">DSS Q_plan (dummy)</div>
              <div class="kpi-value">{(now - timedelta(minutes= random.randint(5,90))).strftime('%H:%M')}</div>
              <div class="kpi-foot">Latest receipt time (prototype)</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with hdr_right:
    unack_text = "None" if unack_cnt == 0 else oldest_unack.strftime("%m/%d %H:%M")
    st.markdown(
        f"""
        <div class="card">
          <div class="kpi-title">Alarm Summary</div>
          <div class="row">
            <div class="col">
              <div class="kpi-title">Critical / Warning</div>
              <div class="kpi-value">{critical_cnt} / {warning_cnt}</div>
              <div class="kpi-foot">Unack: <b>{unack_cnt}</b> | Oldest unack: <b>{unack_text}</b></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------
# KPI band (cards)
# -----------------------------
st.markdown("<div class='row'>", unsafe_allow_html=True)

def kpi_card(title, value, foot, color):
    st.markdown(
        f"""
        <div class="card card-tight col">
          <div class="kpi-title">{title}</div>
          <div class="kpi-value" style="color:{color}">{value}</div>
          <div class="kpi-foot">{foot}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

kpi_cols = st.columns(6)
with kpi_cols[0]:
    kpi_card("Stations OK", ok_cnt, f"of {total_nodes}", STATUS_COLOR["OK"])
with kpi_cols[1]:
    kpi_card("Stations WARN", warn_cnt, "attention required", STATUS_COLOR["WARN"])
with kpi_cols[2]:
    kpi_card("Stations ALARM", alarm_cnt, "abnormal condition", STATUS_COLOR["ALARM"])
with kpi_cols[3]:
    kpi_card("Stations OFFLINE", offline_cnt, "communication lost", STATUS_COLOR["OFFLINE"])
with kpi_cols[4]:
    kpi_card("Modes (Auto)", auto_cnt, f"Manual {man_cnt} / Program {prog_cnt}", MODE_COLOR["AUTO"])
with kpi_cols[5]:
    kpi_card("Unack Alarms", unack_cnt, "to be acknowledged", "#fca5a5" if unack_cnt else STATUS_COLOR["OK"])

st.markdown("</div>", unsafe_allow_html=True)
st.markdown("---")

# -----------------------------
# Main layout: Schema + Operator Console
# -----------------------------
left, right = st.columns([7, 4], gap="large")

with left:
    st.markdown(
        """
        <div class="card">
          <div class="h-title">System Schema</div>
          <div class="h-sub">Topology view with operational status (colors) and drill-down selection</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Drill-down selection
    sel_cols = st.columns([3, 2, 2, 3])
    station_ids = [n["id"] for n in nodes]
    with sel_cols[0]:
        selected_station = st.selectbox("Select Station", options=["(none)"] + station_ids, index=0)
    with sel_cols[1]:
        show_filtered = st.checkbox("Apply Filters", value=True)
    with sel_cols[2]:
        show_legend = st.checkbox("Show Legend", value=True)
    with sel_cols[3]:
        st.caption("Tip: Use filters in sidebar to focus on problematic stations/modes.")

    schema_nodes = filtered_nodes if show_filtered else nodes
    schema_edges = filtered_edges if show_filtered else edges

    dot = dot_schema(schema_nodes, schema_edges, None if selected_station == "(none)" else selected_station)
    st.graphviz_chart(dot, use_container_width=True)

    if show_legend:
        st.markdown(
            f"""
            <div class="card card-tight">
              <div class="h-sub"><b>Legend</b></div>
              <div style="margin-top:8px; display:flex; gap:10px; flex-wrap:wrap;">
                {badge("OK", STATUS_COLOR["OK"])}
                {badge("WARN", STATUS_COLOR["WARN"])}
                {badge("ALARM", STATUS_COLOR["ALARM"])}
                {badge("OFFLINE", STATUS_COLOR["OFFLINE"])}
                <span class="small-muted" style="margin-left:6px;">Node color = status</span>
              </div>
              <div style="margin-top:8px;" class="small-muted">
                Edge styling reflects combined endpoint health (solid=normal, bold=warn/alarm, dashed=offline).
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Direction targets (core operational KPI)
    st.markdown(
        """
        <div class="card" style="margin-top:12px;">
          <div class="h-title">Direction Control Targets (Plan vs Actual)</div>
          <div class="h-sub">Direction-level performance for immediate operational prioritization</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Create a compact deviation chart
    direction_df_sorted = direction_df.sort_values("Deviation (%)", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    fig_dev = px.bar(
        direction_df_sorted,
        x="Direction",
        y="Deviation (%)",
        title=None,
        text="Deviation (%)",
    )
    fig_dev.update_traces(textposition="outside")
    fig_dev.update_layout(
        height=310,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e6edf7",
        xaxis_title=None,
        yaxis_title="Deviation (%)",
        yaxis_gridcolor="rgba(36,50,74,0.7)",
        xaxis_gridcolor="rgba(36,50,74,0.0)",
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_dev, use_container_width=True)

    # Styled table
    def highlight_dev(v):
        level, color = dev_level(v)
        alpha = 0.20 if level == "High" else (0.12 if level == "Medium" else 0.08)
        return f"background-color: rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},{alpha}); color: #e6edf7;"

    st.dataframe(
        direction_df_sorted.style.applymap(highlight_dev, subset=["Deviation (%)"]),
        use_container_width=True,
        hide_index=True,
    )

    st.caption("Operational rule of thumb: prioritize Directions exceeding the defined deviation threshold and persistent deviation.")

with right:
    st.markdown(
        """
        <div class="card">
          <div class="h-title">Operator Console</div>
          <div class="h-sub">Actions, alarms, mode distribution, and station drill-down</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Action List
    st.markdown(
        """
        <div class="card" style="margin-top:12px;">
          <div class="h-title">Action List (Suggested)</div>
          <div class="h-sub">Generated from current status and thresholds</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for sev, msg, items in actions[:6]:
        color = {"OK": STATUS_COLOR["OK"], "WARNING": STATUS_COLOR["WARN"], "CRITICAL": STATUS_COLOR["ALARM"]}.get(sev, "#60a5fa")
        st.markdown(f"{badge(sev, color)} &nbsp; <b>{msg}</b>", unsafe_allow_html=True)
        if items:
            st.caption(f"Related: {', '.join(items[:10])}{' ...' if len(items) > 10 else ''}")

    # Mode distribution chart
    st.markdown(
        """
        <div class="card" style="margin-top:12px;">
          <div class="h-title">Operation Mode Distribution</div>
          <div class="h-sub">Quick check to prevent mode-related operational errors</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    mode_df = pd.DataFrame({"Mode": ["AUTO", "MANUAL", "PROGRAM"], "Count": [auto_cnt, man_cnt, prog_cnt]})
    fig_mode = px.pie(mode_df, names="Mode", values="Count", hole=0.55)
    fig_mode.update_layout(
        height=290,
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e6edf7",
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.05, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig_mode, use_container_width=True)

    # Recent alarms table
    st.markdown(
        """
        <div class="card" style="margin-top:12px;">
          <div class="h-title">Recent Alarms</div>
          <div class="h-sub">Top 10 alarms for first-level assessment</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    top10 = alarms.head(10).copy()
    top10["Time"] = top10["Time"].dt.strftime("%m/%d %H:%M")
    st.dataframe(top10, use_container_width=True, hide_index=True)

    # Station detail drill-down
    st.markdown(
        """
        <div class="card" style="margin-top:12px;">
          <div class="h-title">Station Drill-down</div>
          <div class="h-sub">Operational summary for the selected station</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if selected_station != "(none)":
        n = next(x for x in nodes if x["id"] == selected_station)
        st.markdown(
            f"""
            <div class="card card-tight">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap;">
                <div>
                  <div class="h-title">{n['id']}</div>
                  <div class="h-sub">{n['type']}</div>
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                  {badge(f"Status: {n['status']}", STATUS_COLOR[n['status']])}
                  {badge(f"Mode: {n['mode']}", MODE_COLOR.get(n['mode'], '#60a5fa'))}
                </div>
              </div>
              <div style="margin-top:10px;" class="small-muted">
                Last update: <b>{n['last_update'].strftime('%Y-%m-%d %H:%M:%S')}</b><br/>
                Comm RTT: <b>{'N/A' if n['comm_rtt_ms'] is None else str(n['comm_rtt_ms']) + ' ms'}</b><br/>
                Manual duration: <b>{n['manual_since_min']} min</b>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Quick buttons (prototype placeholders)
        c1, c2, c3 = st.columns(3)
        c1.button("Open Gate Control", use_container_width=True)
        c2.button("Open Monitoring", use_container_width=True)
        c3.button("Open Alarm Viewer", use_container_width=True)

        # Show station-related alarms (filter)
        st.caption("Station-related alarms (latest 8)")
        st.dataframe(
            alarms.loc[alarms["Station"] == n["id"]].head(8).assign(Time=lambda d: d["Time"].dt.strftime("%m/%d %H:%M")),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Select a station (left panel) to display operational details here.")

# -----------------------------
# Bottom: Trend (context)
# -----------------------------
st.markdown("---")
st.markdown(
    """
    <div class="card">
      <div class="h-title">Temporal Context (Trend)</div>
      <div class="h-sub">Helps operators distinguish “not yet reflected” vs “control failure” (prototype)</div>
    </div>
    """,
    unsafe_allow_html=True,
)

trend_long = trend_df.melt(id_vars=["Time"], value_vars=["Q_plan", "Q_actual"], var_name="Series", value_name="Value")
fig_trend = px.line(trend_long, x="Time", y="Value", color="Series")
fig_trend.update_layout(
    height=320,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#e6edf7",
    margin=dict(l=10, r=10, t=10, b=10),
    yaxis_gridcolor="rgba(36,50,74,0.7)",
)
st.plotly_chart(fig_trend, use_container_width=True)

# Optional: show deviation distribution
fig_dev_hist = px.histogram(trend_df, x="Deviation_%", nbins=18)
fig_dev_hist.update_layout(
    height=260,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#e6edf7",
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis_title="Deviation (%)",
    yaxis_title="Count",
    yaxis_gridcolor="rgba(36,50,74,0.7)",
)
st.plotly_chart(fig_dev_hist, use_container_width=True)

st.caption(
    "Prototype note: All values are dummy. Replace generators with real API/DB feeds (TM/TC/SPC status, alarms, DSS Q_plan, direction definitions)."
)
