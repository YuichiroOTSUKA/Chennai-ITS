<script setup lang="ts">
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const props = defineProps<{
  api: string;
  intersections: any[];
  roadSnaps: Array<{ index: number; time_ist: string; segments: Record<string, number> }> | null;
  snapIndex: number;   // -1 = live, ≥0 = replay
}>();

const mapContainer = ref<HTMLElement | null>(null);
let map: maplibregl.Map | null = null;
let popup: maplibregl.Popup | null = null;
let refreshTimer: ReturnType<typeof setInterval> | null = null;

const statusMsg = ref("Loading map…");
const roadsData = ref<any>(null);  // base GeoJSON (probe-seeded, kept in memory for replay)

const legendItems = [
  { color: "#00ff88", label: "Free" },
  { color: "#ffdd00", label: "Moderate" },
  { color: "#ff8800", label: "Heavy" },
  { color: "#ff2200", label: "Severe" },
];

const incidents = computed(() => {
  const incs: Array<{ type: string; sev: string; location: string }> = [];

  if (roadsData.value?.features) {
    const byName: Record<string, number[]> = {};
    for (const f of roadsData.value.features) {
      const name = f.properties?.name;
      if (!name) continue;
      const c: number = f.properties?.congestion ?? 0;
      if (!byName[name]) byName[name] = [];
      byName[name].push(c);
    }
    for (const [name, vals] of Object.entries(byName)) {
      const sevR   = vals.filter((v) => v >= 0.75).length / vals.length;
      const heavyR = vals.filter((v) => v >= 0.55).length / vals.length;
      if (sevR > 0.5)
        incs.push({ type: "幹線渋滞", sev: "CRITICAL", location: name });
      else if (heavyR > 0.5)
        incs.push({ type: "局所渋滞", sev: "HIGH", location: name });
    }
  }

  for (const n of props.intersections) {
    if (n.congestion >= 0.75)
      incs.push({ type: "交差点飽和", sev: "CRITICAL", location: n.name });
  }

  return incs
    .sort((a, b) => (a.sev === "CRITICAL" && b.sev !== "CRITICAL" ? -1 : 1))
    .slice(0, 12);
});

function congColor(c: number) {
  if (c >= 0.75) return "#ff2200";
  if (c >= 0.55) return "#ff8800";
  if (c >= 0.45) return "#ffdd00";
  if (c >= 0.25) return "#44cc66";
  return "#00ff88";
}
function congLabel(c: number) {
  if (c >= 0.75) return "Severe";
  if (c >= 0.55) return "Heavy";
  if (c >= 0.45) return "Moderate";
  if (c >= 0.25) return "Light";
  return "Free Flow";
}

// Apply a road snapshot (replay mode): merge segment congestion into base GeoJSON
function applyRoadSnap(idx: number) {
  if (!roadsData.value || !props.roadSnaps) return;
  const snap = props.roadSnaps[idx];
  if (!snap) return;
  const segs = snap.segments;
  const features = roadsData.value.features.map((f: any) => {
    const fid = String(f.id);
    if (fid in segs)
      return { ...f, properties: { ...f.properties, congestion: segs[fid] } };
    return f;
  });
  const newGeoJSON = { type: "FeatureCollection", features };
  const src = map?.getSource("roads") as maplibregl.GeoJSONSource | undefined;
  if (src) src.setData(newGeoJSON);
  roadsData.value = newGeoJSON;
}

watch(
  () => props.snapIndex,
  (idx) => {
    if (idx >= 0) applyRoadSnap(idx);
  }
);

async function loadRoads() {
  if (!map) return;
  // In replay mode, skip live fetch (base GeoJSON already loaded)
  if (props.snapIndex >= 0 && roadsData.value) {
    applyRoadSnap(props.snapIndex);
    return;
  }
  try {
    const data: any = await $fetch(props.api + "/traffic/roads");
    roadsData.value = data;
    const src = map.getSource("roads") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(data);
    } else {
      map.addSource("roads", { type: "geojson", data });

      map.addLayer({
        id: "roads-casing",
        type: "line",
        source: "roads",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#020810",
          "line-width": ["interpolate", ["linear"], ["zoom"], 10, 5, 14, 10],
          "line-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "roads-glow",
        type: "line",
        source: "roads",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": [
            "interpolate", ["linear"], ["get", "congestion"],
            0.00, "#00ff88",
            0.55, "#ff8800",
            0.75, "#ff2200",
          ],
          "line-width": ["interpolate", ["linear"], ["zoom"], 10, 6, 14, 14],
          "line-opacity": 0.07,
          "line-blur": 5,
        },
      });

      map.addLayer({
        id: "roads-fill",
        type: "line",
        source: "roads",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": [
            "interpolate", ["linear"], ["get", "congestion"],
            0.00, "#00ff88",
            0.25, "#44cc66",
            0.45, "#ffdd00",
            0.55, "#ff8800",
            0.75, "#ff2200",
            0.98, "#cc1100",
          ],
          "line-width": ["interpolate", ["linear"], ["zoom"], 10, 2, 14, 5],
          "line-opacity": 0.95,
        },
      });

      map.on("click", "roads-fill", (e) => {
        if (!e.features?.length) return;
        const f = e.features[0];
        const p = f.properties as any;
        const c = p.congestion as number;
        const label = congLabel(c);
        const color = congColor(c);
        popup?.remove();
        popup = new maplibregl.Popup({ closeButton: false, className: "tms-popup" })
          .setLngLat(e.lngLat)
          .setHTML(`
            <div style="font-family:monospace;padding:9px 11px;min-width:170px">
              <div style="font-size:.78rem;font-weight:700;color:#a8c8e8;margin-bottom:3px;letter-spacing:.5px">${p.name || "Unknown Road"}</div>
              <div style="font-size:.65rem;color:#2a5070;margin-bottom:7px;letter-spacing:.3px">${p.highway || ""}</div>
              <div style="display:flex;align-items:center;gap:8px">
                <div style="width:18px;height:3px;border-radius:1px;background:${color};box-shadow:0 0 5px ${color}88;flex-shrink:0"></div>
                <span style="font-size:.72rem;color:${color};font-weight:700">${label}</span>
                <span style="font-size:.68rem;color:#1e3a5a;margin-left:auto">${(c * 100).toFixed(0)}%</span>
              </div>
            </div>
          `)
          .addTo(map!);
      });

      map.on("mouseenter", "roads-fill", () => {
        if (map) map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "roads-fill", () => {
        if (map) map.getCanvas().style.cursor = "";
      });
    }
    statusMsg.value = "";
  } catch {
    statusMsg.value = "Failed to load road data";
  }
}

onMounted(async () => {
  await nextTick();
  if (!mapContainer.value) return;

  map = new maplibregl.Map({
    container: mapContainer.value,
    style: {
      version: 8,
      glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors",
        },
      },
      layers: [
        {
          id: "osm-tiles",
          type: "raster",
          source: "osm",
          paint: {
            "raster-opacity": 0.5,
            "raster-saturation": -1,
            "raster-brightness-min": 0,
            "raster-brightness-max": 0.3,
          },
        },
      ],
    },
    center: [80.237617, 13.067439],
    zoom: 11,
    minZoom: 9,
    maxZoom: 17,
  });

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 100, unit: "metric" }), "bottom-left");

  map.on("load", () => {
    loadRoads();
    refreshTimer = setInterval(() => {
      if (props.snapIndex < 0) loadRoads();  // live mode only
    }, 30000);
  });
});

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer);
  popup?.remove();
  map?.remove();
});
</script>

<template>
  <div class="map-wrap">
    <div ref="mapContainer" class="map-canvas" />
    <div v-if="statusMsg" class="map-status">{{ statusMsg }}</div>

    <!-- Right panel overlay -->
    <div class="right-panel">
      <div class="panel-hdr">
        <span class="panel-hdr-title">INCIDENT MGT</span>
        <span v-if="incidents.length" class="evt-badge">{{ incidents.length }} EVT</span>
      </div>

      <div class="incident-list">
        <div v-if="!incidents.length" class="all-clear">── ALL CLEAR ──</div>
        <div
          v-for="inc in incidents"
          :key="inc.location + inc.type"
          class="inc-row"
          :class="inc.sev === 'CRITICAL' ? 'inc-crit' : 'inc-high'"
        >
          <div
            class="inc-sev-dot"
            :style="{
              background: inc.sev === 'CRITICAL' ? '#ff2200' : '#ff8800',
              boxShadow: inc.sev === 'CRITICAL' ? '0 0 6px #ff2200' : '0 0 4px #ff8800',
            }"
          />
          <div class="inc-info">
            <div
              class="inc-type"
              :style="{ color: inc.sev === 'CRITICAL' ? '#ff7755' : '#ffbb55' }"
            >{{ inc.type }}</div>
            <div class="inc-loc">{{ inc.location }}</div>
          </div>
          <span
            class="inc-sev-lbl"
            :style="{ color: inc.sev === 'CRITICAL' ? '#ff5533' : '#ff9944' }"
          >{{ inc.sev === "CRITICAL" ? "CRIT" : "HIGH" }}</span>
        </div>
      </div>

      <div class="legend-section">
        <div class="legend-title">CONGESTION INDEX</div>
        <div v-for="item in legendItems" :key="item.label" class="legend-item">
          <div
            class="legend-line"
            :style="{ background: item.color, boxShadow: `0 0 4px ${item.color}44` }"
          />
          <span class="legend-lbl">{{ item.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes blink-crit {
  0%, 49%   { opacity: 1; }
  50%, 100% { opacity: 0.4; }
}

.map-wrap { width: 100%; height: 100%; position: relative; }
.map-canvas { width: 100%; height: 100%; background: #020810; }
.map-status {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  color: #1e3a5a; font-size: 0.8rem; font-family: monospace; pointer-events: none;
}

/* ── Right panel ── */
.right-panel {
  position: absolute; top: 12px; right: 12px; z-index: 30;
  background: rgba(2, 5, 14, 0.96);
  border: 1px solid #0f2040;
  border-radius: 6px;
  padding: 10px 13px;
  width: 210px;
  box-shadow: 0 0 28px rgba(0, 60, 180, 0.14), inset 0 0 20px rgba(0, 20, 60, 0.3);
}

.panel-hdr {
  display: flex; align-items: center; gap: 6px;
  border-bottom: 1px solid #0a1830;
  padding-bottom: 6px; margin-bottom: 7px;
}
.panel-hdr-title {
  color: #a8c8e8; font-size: 10px; font-weight: 700;
  letter-spacing: 1.2px; font-family: monospace;
}
.evt-badge {
  margin-left: auto;
  background: rgba(160, 20, 0, 0.85); color: #ffcccc;
  font-size: 8px; font-weight: 700; font-family: monospace;
  border-radius: 3px; padding: 1px 5px;
  animation: blink-crit 1.5s infinite; letter-spacing: 0.5px;
}

.incident-list {
  max-height: 160px; overflow-y: auto; margin-bottom: 8px;
  scrollbar-width: thin; scrollbar-color: #0a2040 transparent;
}
.all-clear {
  color: #0d2030; font-size: 9px; font-family: monospace;
  text-align: center; padding: 10px 0; letter-spacing: 0.5px;
}
.inc-row {
  display: flex; align-items: center; gap: 5px;
  margin-bottom: 5px; padding: 4px 5px; border-radius: 3px;
}
.inc-crit { background: rgba(80, 10, 0, 0.4);  border: 1px solid #3a0800; }
.inc-high  { background: rgba(60, 30, 0, 0.3);  border: 1px solid #3a2000; }
.inc-sev-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.inc-info { flex: 1; min-width: 0; }
.inc-type { font-size: 9px; font-family: monospace; font-weight: 700; }
.inc-loc {
  font-size: 8px; font-family: monospace; color: #2a5070;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.inc-sev-lbl { font-size: 7px; font-weight: 700; font-family: monospace; flex-shrink: 0; letter-spacing: 0.3px; }

/* ── Legend ── */
.legend-section { border-top: 1px solid #0a1830; padding-top: 7px; }
.legend-title {
  color: #1e3a5a; font-size: 9px; font-family: monospace;
  font-weight: 700; letter-spacing: 0.8px; margin-bottom: 6px;
}
.legend-item { display: flex; align-items: center; gap: 7px; margin-bottom: 5px; }
.legend-line { width: 22px; height: 3px; border-radius: 1px; }
.legend-lbl { color: #2a5070; font-size: 9px; font-family: monospace; }
</style>

<style>
.maplibregl-ctrl-bottom-right { bottom: 8px !important; right: 8px !important; }
.maplibregl-ctrl-bottom-left  { bottom: 8px !important; left: 8px !important; }
.maplibregl-ctrl-group {
  background: rgba(2, 5, 14, 0.92) !important;
  border: 1px solid #0f2040 !important;
  border-radius: 6px !important;
}
.maplibregl-ctrl-group button {
  background: transparent !important;
  color: #2a5070 !important;
  border-bottom-color: #0a1830 !important;
}
.maplibregl-ctrl-group button:hover {
  background: rgba(0, 60, 180, 0.08) !important;
  color: #6699ee !important;
}
.maplibregl-ctrl-scale {
  background: rgba(2, 5, 14, 0.85) !important;
  border-color: #0f2040 !important;
  color: #1e3a5a !important;
  font-size: 0.65rem !important;
  font-family: monospace !important;
}
.maplibregl-popup-content {
  background: rgba(2, 5, 14, 0.98) !important;
  border: 1px solid #0f2040 !important;
  border-radius: 6px !important;
  padding: 0 !important;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6) !important;
}
.maplibregl-popup-tip { display: none !important; }
.maplibregl-popup-close-button { color: #1e3a5a !important; }
</style>
