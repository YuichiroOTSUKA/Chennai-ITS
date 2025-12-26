# app.py
# WMS Landing Page (Operator-Centric) - Streamlit Prototype (NO plotly)
# Fixes applied:
# - Removed &nbsp; usage completely
# - Ensured ALL HTML blocks are rendered via st.markdown(..., unsafe_allow_html=True)
# - Cleaned up /div mismatches and reduced “dangling” HTML
#
# Run:
#   pip install streamlit pandas numpy
#   streamlit run app.py

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="WMS Landing (Ops)", layout="wide")

# -----------------------------
# Styling
# -----------------------------
CSS = """
<style>
:root{
  --bg:#0b1220;
  --card:#111b2d;
  --text:#e6edf7;
  --muted:#9fb0c7;
  --line:#24324a;
  --ok:#22c55e;
  --warn:#f59e0b;
  --alarm:#ef4444;
  --offline:#64748b;
  --info:#60a5fa;
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
  background: rgba(255,255,255,0.04);
}

.dot {
  width: 8px; height: 8px; border-radius: 50%;
  display: inline-block;
}

.kpi-title { color: var(--muted); font-size: 12px; margin-bottom: 2px; }
.kpi-value { font-size: 22px; font-weight: 800; line-height: 1.1; }
.kpi-foot { color: var(--muted); font-size: 11px; margin-top: 4px; }

section[data-testid="stSidebar"] {
  background: rgba(8, 12, 22, 0.70);
  border-right: 1px solid rgba(36, 50, 74, 0.8);
}
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
MODE_COLOR = {"AUTO": "#60a5fa", "MANUAL": "#a78bfa", "PROGRAM": "#34d399"}

def badge(label: str, color: str) -> str:
    return f"""
    <span class="badge">
      <span class="dot" style="background:{color};"></span>
      {label}
    </span>
    """

def system_state_from_counts(offline_cnt: int, alarm_cnt: int, total: int) -> str:
    if offline_cnt >= max(1, int(total * 0.4)):
        return "Down"
    if offline_cnt > 0 and alarm_cnt > 0:
        return "Partial Down"
    if alarm_cnt > 0 or offline_cnt > 0:
        return "Degraded"
    return "Active"

def freshness_label(staleness_s: int):
    if staleness_s <= 60:
        return ("Fresh", STATUS_COLOR["OK"])
    if staleness_s <= 300:
        return ("Slight Delay", STATUS_COLOR["WARN"])
    return ("Stale", STATUS_COLOR["ALARM"])

def dev_level(dev_pct: float):
    a = abs(dev_pct)
    if a >= 15:
        return ("High", STATUS_COLOR["ALARM"])
    if a >= 8:
        return ("Medium", STATUS_COLOR["WARN"])
    return ("Low", STATUS_COLOR["OK"])

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

    for n in nodes:
        if n["id"] == "HW":
            n["status"] = "OK"
            n["mode"] = "AUTO"
        else:
            n["status"] = random.choices(STATUS, weights=[72, 14, 10, 4])[0]
            n["mode"] = random.choices(MODE, weights=[65, 22, 13])[0]

        n["last_update"] = datetime.now() - timedelta(seconds=random.randint(5, 2400))
        n["comm_rtt_ms"] = None if n["status"] == "OFFLINE" else random.randint(20, 520)
        n["manual_since_min"] = random.randint(5, 360) if n["mode"] == "MANUAL" else 0

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
        n = random.choice(nodes[1:])
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
    base_plan = random.randint(85, 135)
    plan = np.array([base_plan + int(4*np.sin(i/3)) for i in range(hours)], dtype=float)
    actual = plan + np.random.normal(0, 8, size=hours)
    df = pd.DataFrame({"Time": ts, "Q_plan": plan, "Q_actual": actual})
    df["Deviation_%"] = (df["Q_actual"] - df["Q_plan"]) / df["Q_plan"] * 100
    return df

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.markdown("### WMS Operator Panel")
st.sidebar.caption("Landing page prototype (dummy data).")

if "seed" not in st.session_state:
    st.session_state.seed = 10

sb1, sb2 = st.sidebar.columns(2)
with sb1:
    if st.button("Refresh", use_container_width=True):
        st.session_state.seed += 1
with sb2:
    auto = st.checkbox("Auto", value=False)

refresh_rate_s = st.sidebar.slider("Auto refresh (s)", 5, 60, 15, disabled=not auto)
if auto:
    st.autorefresh(interval=refresh_rate_s * 1000, key="wms_autorefresh")

st.sidebar.markdown("---")
st.sidebar.markdown("**Filters**")
flt_status = st.sidebar.multiselect("Status", STATUS, default=STATUS)
flt_mode = st.sidebar.multiselect("Mode", MODE, default=MODE)
search = st.sidebar.text_input("Search Station ID", "")

st.sidebar.markdown("---")
season = st.sidebar.selectbox("Operational Phase", ["Dry", "Wet", "Flood"], index=0)
special_mode = st.sidebar.selectbox("Special Operation", ["Normal", "Drought Response", "Flood Alert"], index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("**Thresholds**")
thr_stale_s = st.sidebar.number_input("Stale data threshold (s)", 60, 7200, 600, 60)
thr_manual_min = st.sidebar.number_input("Manual duration threshold (min)", 5, 1440, 120, 5)
thr_dev_pct = st.sidebar.number_input("Direction deviation threshold (%)", 1, 50, 10, 1)

# -----------------------------
# Data
# -----------------------------
seed = st.session_state.seed
nodes, edges = gen_nodes(seed)
alarms = gen_alarms(nodes, seed)
direction_df = gen_direction_targets(seed)
trend_df = gen_trend(seed, 24)

# Filters
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
oldest_unack = alarms.loc[alarms["Ack"] == "No", "Time"].min() if unack_cnt > 0 else None

last_update_global = max(n["last_update"] for n in nodes)
staleness_s = int((datetime.now() - last_update_global).total_seconds())
fresh_label, fresh_color = freshness_label(staleness_s)

sys_state = system_state_from_counts(offline_cnt, alarm_cnt, total_nodes)

# Actions
actions = []
offline_list = [n["id"] for n in nodes if n["status"] == "OFFLINE"]
if offline_list:
    actions.append(("CRITICAL", f"Communication loss: {len(offline_list)} station(s) OFFLINE", offline_list))
if unack_cnt > 0:
    actions.append(("CRITICAL" if unack_cnt >= 5 else "WARNING",
                    f"{unack_cnt} unacknowledged alarm(s) require acknowledgement", []))
if staleness_s >= thr_stale_s:
    actions.append(("CRITICAL" if staleness_s >= thr_stale_s * 2 else "WARNING",
                    f"System data freshness is STALE ({staleness_s}s since last update)", []))
long_manual = [n["id"] for n in nodes if n["mode"] == "MANUAL" and n["manual_since_min"] >= thr_manual_min]
if long_manual:
    actions.append(("WARNING", f"Manual operation exceeding {thr_manual_min} min: {len(long_manual)} gate(s)", long_manual))
dir_over = direction_df.loc[direction_df["Deviation (%)"].abs() >= thr_dev_pct].copy()
if len(dir_over) > 0:
    dir_over["absdev"] = dir_over["Deviation (%)"].abs()
    top = dir_over.sort_values("absdev", ascending=False).iloc[0]
    actions.append(("CRITICAL" if abs(top["Deviation (%)"]) >= thr_dev_pct * 1.5 else "WARNING",
                    f"Direction deviation exceeds {thr_dev_pct}%: {top['Direction']} ({top['Deviation (%)']}%)", [top["Direction"]]))
if not actions:
    actions.append(("OK", "No urgent action suggested (based on current thresholds).", []))

# -----------------------------
# Graphviz schema
# -----------------------------
def dot_schema(nodes_in, edges_in, highlight=None):
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
        return f'{n["id"]}\\n{n["type"]} | {n["mode"]}'

    for n in nodes_in:
        fill = STATUS_COLOR.get(n["status"], STATUS_COLOR["OFFLINE"])
        penw = 3 if highlight and n["id"] == highlight else 1
        lines.append(
            f'"{n["id"]}" [label="{node_label(n)}" fillcolor="{fill}" color="#0b1220" penwidth={penw} fontcolor="#0b1220"];'
        )

    for a, b in edges_in:
        sa = node_map[a]["status"]
        sb = node_map[b]["status"]
        if "OFFLINE" in (sa, sb):
            ec, stl = STATUS_COLOR["OFFLINE"], "dashed"
        elif "ALARM" in (sa, sb):
            ec, stl = STATUS_COLOR["ALARM"], "bold"
        elif "WARN" in (sa, sb):
            ec, stl = STATUS_COLOR["WARN"], "bold"
        else:
            ec, stl = "#60a5fa", "solid"
        lines.append(f'"{a}" -> "{b}" [color="{ec}" style="{stl}"];')

    lines.append("}")
    return "\n".join(lines)

# -----------------------------
# Header
# -----------------------------
now = datetime.now()
hdr_left, hdr_mid, hdr_right = st.columns([3, 6, 3], vertical_alignment="center")

with hdr_left:
    state_color = {"Active": STATUS_COLOR["OK"], "Degraded": STATUS_COLOR["WARN"], "Partial Down": STATUS_COLOR["ALARM"], "Down": STATUS_COLOR["ALARM"]}[sys_state]
    st.markdown(
        f"""
        <div class="card">
          <div class="h-title">WMS Landing Page</div>
          <div class="h-sub">Operator-centric overview and actions</div>
          <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap;">
            {badge(f"System: {sys_state}", state_color)}
            {badge(f"Freshness: {fresh_label}", fresh_color)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with hdr_mid:
    st.markdown(
        f"""
        <div class="card">
          <div class="h-sub"><b>Local Time</b></div>
          <div class="h-title">{now.strftime('%d/%m/%Y %H:%M:%S')}</div>
          <div class="small-muted" style="margin-top:8px;">
            Phase: <b>{season}</b> / Special: <b>{special_mode}</b><br/>
            Last Data Update: <b>{last_update_global.strftime('%H:%M:%S')}</b>
            (Staleness: <b>{staleness_s}s</b>, threshold: {thr_stale_s}s)
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
          <div class="h-sub"><b>Alarm Summary</b></div>
          <div class="h-title">{critical_cnt} / {warning_cnt}</div>
          <div class="small-muted" style="margin-top:8px;">
            Critical / Warning<br/>
            Unack: <b>{unack_cnt}</b> | Oldest unack: <b>{unack_text}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# KPI row
kpi_cols = st.columns(6)

def kpi_box(container, title, value, foot, color):
    container.markdown(
        f"""
        <div class="card card-tight">
          <div class="kpi-title">{title}</div>
          <div class="kpi-value" style="color:{color}">{value}</div>
          <div class="kpi-foot">{foot}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

kpi_box(kpi_cols[0], "Stations OK", ok_cnt, f"of {total_nodes}", STATUS_COLOR["OK"])
kpi_box(kpi_cols[1], "Stations WARN", warn_cnt, "attention required", STATUS_COLOR["WARN"])
kpi_box(kpi_cols[2], "Stations ALARM", alarm_cnt, "abnormal condition", STATUS_COLOR["ALARM"])
kpi_box(kpi_cols[3], "Stations OFFLINE", offline_cnt, "communication lost", STATUS_COLOR["OFFLINE"])
kpi_box(kpi_cols[4], "Modes (Auto)", auto_cnt, f"Manual {man_cnt} / Program {prog_cnt}", MODE_COLOR["AUTO"])
kpi_box(kpi_cols[5], "Unack Alarms", unack_cnt, "to be acknowledged", STATUS_COLOR["WARN"] if unack_cnt else STATUS_COLOR["OK"])

st.markdown("---")

# -----------------------------
# Main layout
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

    sel_cols = st.columns([3, 2, 2, 3])
    station_ids = [n["id"] for n in nodes]
    with sel_cols[0]:
        selected_station = st.selectbox("Select Station", options=["(none)"] + station_ids, index=0)
    with sel_cols[1]:
        show_filtered = st.checkbox("Apply Filters", value=True)
    with sel_cols[2]:
        show_legend = st.checkbox("Show Legend", value=True)
    with sel_cols[3]:
        st.caption("Tip: Use sidebar filters to focus on problematic stations/modes.")

    schema_nodes = filtered_nodes if show_filtered else nodes
    schema_edges = filtered_edges if show_filtered else edges
    dot = dot_schema(schema_nodes, schema_edges, None if selected_station == "(none)" else selected_station)
    st.graphviz_chart(dot, use_container_width=True)

    if show_legend:
        st.markdown(
            f"""
            <div class="card card-tight">
              <div class="h-sub"><b>Legend</b></div>
              <div style="margin-top:8px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
                {badge("OK", STATUS_COLOR["OK"])}
                {badge("WARN", STATUS_COLOR["WARN"])}
                {badge("ALARM", STATUS_COLOR["ALARM"])}
                {badge("OFFLINE", STATUS_COLOR["OFFLINE"])}
                <span class="small-muted" style="margin-left:6px;">Node color = status</span>
              </div>
              <div style="margin-top:8px;" class="small-muted">
                Edge styling reflects combined endpoint health
                (solid = normal, bold = warn/alarm, dashed = offline).
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="card" style="margin-top:12px;">
          <div class="h-title">Direction Control Targets (Plan vs Actual)</div>
          <div class="h-sub">Direction-level performance for immediate operational prioritization</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    direction_sorted = direction_df.copy()
    direction_sorted["absdev"] = direction_sorted["Deviation (%)"].abs()
    direction_sorted = direction_sorted.sort_values("absdev", ascending=False).drop(columns=["absdev"]).reset_index(drop=True)

    # Bar chart (Deviation)
    st.bar_chart(direction_sorted.set_index("Direction")[["Deviation (%)"]], use_container_width=True)

    # Styled table
    def highlight_dev(v):
        _, color = dev_level(v)
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        alpha = 0.18
        return f"background-color: rgba({r},{g},{b},{alpha}); color: #e6edf7;"

    st.dataframe(
        direction_sorted.style.applymap(highlight_dev, subset=["Deviation (%)"]),
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.markdown(
        """
        <div class="card">
          <div class="h-title">Operator Console</div>
          <div class="h-sub">Actions, alarms, and station drill-down</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
        color = {"OK": STATUS_COLOR["OK"], "WARNING": STATUS_COLOR["WARN"], "CRITICAL": STATUS_COLOR["ALARM"]}.get(sev, STATUS_COLOR["OFFLINE"])
        st.markdown(f"{badge(sev, color)} &nbsp; <b>{msg}</b>", unsafe_allow_html=True)
        if items:
            st.caption(f"Related: {', '.join(items[:10])}{' ...' if len(items) > 10 else ''}")

    st.markdown(
        """
        <div class="card" style="margin-top:12px;">
          <div class="h-title">Operation Mode Distribution</div>
          <div class="h-sub">Quick check to prevent mode-related operational errors</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    mode_df = pd.DataFrame({"Mode": ["AUTO", "MANUAL", "PROGRAM"], "Count": [auto_cnt, man_cnt, prog_cnt]}).set_index("Mode")
    st.bar_chart(mode_df, use_container_width=True)

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
              <div class="small-muted" style="margin-top:10px;">
                Last update: <b>{n['last_update'].strftime('%Y-%m-%d %H:%M:%S')}</b><br/>
                Comm RTT: <b>{"N/A" if n["comm_rtt_ms"] is None else str(n["comm_rtt_ms"]) + " ms"}</b><br/>
                Manual duration: <b>{n["manual_since_min"]} min</b>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        b1, b2, b3 = st.columns(3)
        b1.button("Open Gate Control", use_container_width=True)
        b2.button("Open Monitoring", use_container_width=True)
        b3.button("Open Alarm Viewer", use_container_width=True)

        st.caption("Station-related alarms (latest 8)")
        st.dataframe(
            alarms.loc[alarms["Station"] == n["id"]].head(8).assign(Time=lambda d: d["Time"].dt.strftime("%m/%d %H:%M")),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Select a station (left panel) to display operational details here.")

# -----------------------------
# Trend (context)
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

st.line_chart(trend_df.set_index("Time")[["Q_plan", "Q_actual"]], use_container_width=True)
st.caption("Prototype note: All values are dummy. Replace generators with real API/DB feeds later.")
