import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random

st.set_page_config(page_title="WMS Landing (Ideal)", layout="wide")

# -----------------------------
# Dummy data generators
# -----------------------------
STATUS = ["OK", "WARN", "ALARM", "OFFLINE"]
STATUS_COLOR = {
    "OK": "#2e7d32",
    "WARN": "#f9a825",
    "ALARM": "#c62828",
    "OFFLINE": "#546e7a",
}

def gen_stations():
    # A small canal network (dummy)
    nodes = [
        {"id": "HW", "label": "Headworks", "type": "Hub"},
        {"id": "B.Sd.1", "label": "B.Sd.1", "type": "TC"},
        {"id": "B.Sd.3", "label": "B.Sd.3", "type": "SPC"},
        {"id": "B.Cpl.1.4", "label": "B.Cpl.1.4", "type": "SPC"},
        {"id": "B.Bt.15", "label": "B.Bt.15", "type": "SPC"},
        {"id": "B.Ut.10", "label": "B.Ut.10", "type": "SPC"},
        {"id": "B.Cpl.5", "label": "B.Cpl.5", "type": "TC"},
        {"id": "B.Gs.11", "label": "B.Gs.11", "type": "SPC"},
        {"id": "B.Bt.4", "label": "B.Bt.4", "type": "Gate"},
        {"id": "B.Bt.21", "label": "B.Bt.21", "type": "Gate"},
    ]

    # Assign random statuses (but keep HW mostly OK)
    for n in nodes:
        if n["id"] == "HW":
            n["status"] = "OK"
        else:
            n["status"] = random.choices(STATUS, weights=[70, 15, 10, 5])[0]

        # Additional operational context (dummy)
        n["mode"] = random.choices(
            ["AUTO", "MANUAL", "PROGRAM"], weights=[65, 20, 15]
        )[0]
        n["last_update"] = datetime.now() - timedelta(seconds=random.randint(5, 1800))
        n["comm_rtt_ms"] = random.randint(20, 450) if n["status"] != "OFFLINE" else None

    edges = [
        ("HW", "B.Sd.1"),
        ("HW", "B.Sd.3"),
        ("B.Sd.3", "B.Cpl.1.4"),
        ("B.Cpl.1.4", "B.Bt.15"),
        ("B.Bt.15", "B.Ut.10"),
        ("HW", "B.Cpl.5"),
        ("B.Cpl.5", "B.Gs.11"),
        ("B.Gs.11", "B.Bt.4"),
        ("B.Gs.11", "B.Bt.21"),
    ]
    return nodes, edges

def gen_alarms(nodes):
    rows = []
    now = datetime.now()
    alarm_types = ["COMM_LOSS", "WL_HIGH", "WL_LOW", "MODE_MISMATCH", "POWER", "SENSOR_FAULT"]
    for _ in range(25):
        n = random.choice(nodes)
        sev = random.choices(["CRITICAL", "WARNING"], weights=[35, 65])[0]
        ack = random.choices([True, False], weights=[70, 30])[0]
        rows.append({
            "Time": now - timedelta(minutes=random.randint(1, 1440)),
            "Station": n["id"],
            "Severity": sev,
            "Type": random.choice(alarm_types),
            "Message": f"{random.choice(alarm_types)} detected at {n['id']}",
            "Ack": "Yes" if ack else "No",
        })
    df = pd.DataFrame(rows).sort_values("Time", ascending=False)
    return df

def gen_direction_targets():
    # Direction-level control targets (dummy)
    directions = ["Direction A", "Direction B", "Direction C"]
    rows = []
    for d in directions:
        q_plan = random.randint(80, 140)
        q_act = q_plan + random.randint(-20, 25)
        dev = (q_act - q_plan) / q_plan * 100
        rows.append({
            "Direction": d,
            "Q_plan (m3/s)": q_plan,
            "Q_actual (m3/s)": q_act,
            "Deviation (%)": round(dev, 1),
        })
    return pd.DataFrame(rows)

# -----------------------------
# UI helpers
# -----------------------------
def status_badge(status: str) -> str:
    c = STATUS_COLOR.get(status, "#607d8b")
    return f"<span style='background:{c};color:white;padding:2px 8px;border-radius:12px;font-size:12px;'>{status}</span>"

def mode_badge(mode: str) -> str:
    m = {"AUTO":"#1565c0","MANUAL":"#6a1b9a","PROGRAM":"#2e7d32"}.get(mode, "#455a64")
    return f"<span style='background:{m};color:white;padding:2px 8px;border-radius:12px;font-size:12px;'>{mode}</span>"

def build_graphviz(nodes, edges, highlight=None):
    # Graphviz DOT with colored nodes by status
    lines = ["digraph G {", "rankdir=LR;", "splines=true;", "nodesep=0.5;", "ranksep=0.7;"]
    lines.append('node [shape=circle style=filled fontname="Helvetica" fontsize=10];')

    for n in nodes:
        fill = STATUS_COLOR[n["status"]]
        border = "#000000"
        penw = 3 if highlight and n["id"] == highlight else 1
        label = f'{n["id"]}\\n{n["type"]}'
        lines.append(f'"{n["id"]}" [label="{label}" fillcolor="{fill}" color="{border}" penwidth={penw}];')

    # Edge color by "link health" (simplified: if either endpoint offline -> grey)
    node_map = {n["id"]: n for n in nodes}
    for a, b in edges:
        ca = node_map[a]["status"]
        cb = node_map[b]["status"]
        if "OFFLINE" in (ca, cb):
            ec = "#90a4ae"
            style = "dashed"
        elif "ALARM" in (ca, cb):
            ec = "#c62828"
            style = "bold"
        elif "WARN" in (ca, cb):
            ec = "#f9a825"
            style = "bold"
        else:
            ec = "#1e88e5"
            style = "solid"
        lines.append(f'"{a}" -> "{b}" [color="{ec}" style="{style}"];')

    lines.append("}")
    return "\n".join(lines)

# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.title("WMS Control System")
refresh = st.sidebar.button("Refresh (Dummy Update)")
filter_status = st.sidebar.multiselect("Filter by Status", STATUS, default=STATUS)
filter_mode = st.sidebar.multiselect("Filter by Mode", ["AUTO", "MANUAL", "PROGRAM"], default=["AUTO","MANUAL","PROGRAM"])
search_station = st.sidebar.text_input("Search Station ID", value="")

# -----------------------------
# Data init
# -----------------------------
if "seed" not in st.session_state:
    st.session_state.seed = 1
if refresh:
    st.session_state.seed += 1
random.seed(st.session_state.seed)

nodes, edges = gen_stations()
alarms = gen_alarms(nodes)
direction_df = gen_direction_targets()

# Apply filters
filtered_nodes = []
for n in nodes:
    if n["status"] not in filter_status:
        continue
    if n["mode"] not in filter_mode:
        continue
    if search_station and search_station.lower() not in n["id"].lower():
        continue
    filtered_nodes.append(n)

# For visualization, keep edges whose nodes remain
filtered_ids = {n["id"] for n in filtered_nodes}
filtered_edges = [(a,b) for (a,b) in edges if a in filtered_ids and b in filtered_ids]

# KPI calculation
def count_by(nodes, key, value):
    return sum(1 for n in nodes if n.get(key) == value)

now = datetime.now()
last_update = max([n["last_update"] for n in nodes])
staleness_sec = int((now - last_update).total_seconds())

critical_cnt = (alarms["Severity"] == "CRITICAL").sum()
warning_cnt = (alarms["Severity"] == "WARNING").sum()
unack_cnt = (alarms["Ack"] == "No").sum()

offline_cnt = count_by(nodes, "status", "OFFLINE")
alarm_node_cnt = count_by(nodes, "status", "ALARM")
warn_node_cnt = count_by(nodes, "status", "WARN")
ok_node_cnt = count_by(nodes, "status", "OK")

# -----------------------------
# Header
# -----------------------------
left, mid, right = st.columns([2, 5, 2])
with left:
    st.markdown("### CYBER CONTROL")
with mid:
    st.markdown(
        f"**{now.strftime('%d/%m/%Y, %H:%M:%S')}** &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Last Data Update: **{last_update.strftime('%H:%M:%S')}** "
        f"(staleness **{staleness_sec}s**)"
    )
with right:
    st.markdown("**System Status:** Active")
    st.caption("Mode: Monitoring")

# -----------------------------
# Top KPIs
# -----------------------------
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Stations OK", ok_node_cnt)
k2.metric("Stations WARN", warn_node_cnt)
k3.metric("Stations ALARM", alarm_node_cnt)
k4.metric("Stations OFFLINE", offline_cnt)
k5.metric("Alarms (CRIT/WARN)", f"{critical_cnt}/{warning_cnt}")
k6.metric("Unack Alarms", unack_cnt)

st.divider()

# -----------------------------
# Main layout
# -----------------------------
colA, colB = st.columns([7, 4])

with colA:
    st.markdown("## SYSTEM SCHEMA")
    st.caption("Interactive (Prototype): status-colored topology + drill-down selection")

    # Selection (simulate click by dropdown for now)
    station_ids = [n["id"] for n in nodes]
    selected = st.selectbox("Select Station (Drill-down)", options=["(none)"] + station_ids, index=0)

    dot = build_graphviz(filtered_nodes, filtered_edges, highlight=None if selected=="(none)" else selected)
    st.graphviz_chart(dot, use_container_width=True)

    st.markdown("### Direction Control Targets (Plan vs Actual)")
    # Show Direction targets with visual cues
    def dev_style(v):
        if abs(v) >= 15: return "background-color: rgba(198,40,40,0.15);"
        if abs(v) >= 8:  return "background-color: rgba(249,168,37,0.15);"
        return "background-color: rgba(46,125,50,0.10);"
    styled = direction_df.style.applymap(lambda v: dev_style(v) if isinstance(v, (int,float)) else "", subset=["Deviation (%)"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

with colB:
    st.markdown("## Operator Console")

    # Quick status panel
    st.markdown("### Quick Situation")
    st.write(
        f"- Communication: **{len(nodes)-offline_cnt}/{len(nodes)} online**\n"
        f"- Alarms: **{critical_cnt} critical**, **{warning_cnt} warning**, **{unack_cnt} unack**\n"
        f"- Data Freshness: **{staleness_sec}s** since last update"
    )

    # Actionable tasks (dummy rules)
    st.markdown("### Action List (Suggested)")
    actions = []
    if offline_cnt > 0:
        actions.append(f"Check communication: **{offline_cnt} station(s) OFFLINE**")
    if unack_cnt > 0:
        actions.append(f"Acknowledge alarms: **{unack_cnt} unacknowledged**")
    # Direction deviation suggestions
    worst = direction_df.iloc[(direction_df["Deviation (%)"].abs()).argsort()[::-1]].head(1).iloc[0]
    if abs(worst["Deviation (%)"]) >= 10:
        actions.append(f"Investigate deviation: **{worst['Direction']}** ({worst['Deviation (%)']}%)")
    if not actions:
        actions = ["No urgent action suggested (dummy)."]
    for a in actions[:5]:
        st.write(f"• {a}")

    st.divider()

    # Recent alarms
    st.markdown("### Recent Alarms (Top 10)")
    top10 = alarms.head(10).copy()
    top10["Time"] = top10["Time"].dt.strftime("%m/%d %H:%M")
    st.dataframe(top10, use_container_width=True, hide_index=True)

    st.divider()

    # Selected station details
    st.markdown("### Station Detail")
    if selected != "(none)":
        n = next(x for x in nodes if x["id"] == selected)
        st.markdown(
            f"**Station:** {n['id']} &nbsp;&nbsp; "
            f"**Type:** {n['type']} &nbsp;&nbsp; "
            f"**Status:** {status_badge(n['status'])} &nbsp;&nbsp; "
            f"**Mode:** {mode_badge(n['mode'])}",
            unsafe_allow_html=True
        )
        st.write(f"- Last update: {n['last_update'].strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"- Comm RTT: {n['comm_rtt_ms']} ms" if n["comm_rtt_ms"] else "- Comm RTT: (N/A)")
        st.write("- Shortcut: Gate Control / Monitoring / Alarm Viewer (to be wired)")
        c1, c2, c3 = st.columns(3)
        c1.button("Open Gate Control", use_container_width=True)
        c2.button("Open Monitoring", use_container_width=True)
        c3.button("Open Alarms", use_container_width=True)
    else:
        st.caption("Select a station to show details and drill-down actions.")

st.caption("Prototype note: This is a UI skeleton with dummy data. Replace generators with API/DB later.")
