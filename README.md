# Chennai ITS — Intelligent Transportation System

## Overview

A real-time traffic management center (TMC) platform for Chennai, India. Integrates GPS probe data and travel-time probe data across 42 intersections and 64 schematic links, with SUMO microsimulation comparison and BPR-based demand forecasting.

**Local:** `http://localhost:8090` (port 8090 via nginx)

---

## Architecture

```
[GPS Probe Vehicles]   [Travel-Time Sensors]
        ↓                      ↓
[FastAPI Server :8100]  ←  precomputed JSON snapshots
        ↓
[Nuxt 3 Frontend :3010]
        ↓
[Nginx :8090]  (reverse proxy)
```

### Services (Docker Compose)

| Container | Role | Port |
|---|---|---|
| `chennai-nginx` | Reverse proxy | 8090 |
| `chennai-node` | Nuxt 3 frontend | 3010 |
| `chennai-server` | FastAPI REST API | 8100 |

---

## Pages

| Page | Path | Description |
|---|---|---|
| Main Map | `/` | Real-time schematic map, live/replay mode, congestion overlay |
| Compare | `/compare` | GPS vs Travel-Time side-by-side + scatter plot |
| Analytics | `/analytics` | Corridor analytics, time-series sparklines, link table |
| Method Analysis | `/method-analysis` | GPS vs TT statistical comparison, MAD/RMSE/correlation |
| Simulation | `/simulation` | SUMO scenario comparison (baseline/low/high demand) |
| Forecast | `/forecast` | BPR-based demand forecasting, bottleneck ranking |
| Route | `/route` | Dijkstra multi-criteria route comparison (3 criteria) |

---

## Key Technical Concepts

### Congestion Measurement Methods
- **GPS Probe:** Instantaneous speed from GPS-equipped vehicles
- **Travel-Time Probe:** Space-mean speed from link traversal times
- **SUMO Simulation:** Microsimulation with OSM road network

### BPR Model
```
cong(m) = 1 - 1 / (1 + 0.15 × (m × v/c)^4)
```
Calibrated from GPS+TT probe data (2026-03-18 16:10 IST).

### Route Algorithm
Dijkstra on 42-node intersection graph (64 bidirectional links).  
3 criteria: shortest distance / minimum congestion / fastest time.

---

## Design System

Same as NKLINK: `#020818` background, `#38bdf8` primary, `#6366f1` accent.  
Left sidebar navigation (NavSidebar, 52px → 156px hover).

---

## Setup

```bash
docker compose up -d
# Access: http://localhost:8090
# API docs: http://localhost:8100/docs
```

---

## Directory Structure

```
chennai/
├── docker-compose.yml
├── nginx.conf
├── server/             # FastAPI backend
│   ├── main.py
│   └── src/data/       # Precomputed JSON snapshots
└── node/               # Nuxt 3 frontend
    └── src/
        ├── pages/      # 7 pages
        └── components/
            └── NavSidebar.vue
```

---

## Data

- **42 intersections** across Chennai metropolitan area
- **64 schematic links** (bidirectional)
- **15 time snapshots** (16:10–16:38 IST, 2-min intervals)
- **3 SUMO scenarios:** baseline, low demand, high demand
