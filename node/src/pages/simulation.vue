<script setup lang="ts">
const runtimeConfig = useRuntimeConfig();
const API = runtimeConfig.public.apiBase || "http://localhost:8100";

const loading   = ref(true);
const gpsData   = ref<any>(null);
const ttData    = ref<any>(null);
const sumoData  = ref<any>(null);
const scenario  = ref<"baseline" | "low_demand" | "high_demand">("baseline");
const binIdx    = ref(7);

async function fetchAll() {
  loading.value = true;
  try {
    const [gps, tt, sumo] = await Promise.all([
      $fetch(API + "/traffic/schematic-snapshots?method=gps"),
      $fetch(API + "/traffic/schematic-snapshots?method=tt"),
      $fetch(API + "/traffic/sumo-scenarios").catch(() => null),
    ]);
    gpsData.value  = gps;
    ttData.value   = tt;
    sumoData.value = sumo;
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
}
onMounted(fetchAll);

const LINK_ORDER = Array.from({ length: 64 }, (_, i) => `l${String(i + 1).padStart(2, "0")}`);
const N_BINS     = 15;
const TIME_LABELS = Array.from({ length: N_BINS }, (_, i) => {
  const m = 16 * 60 + 10 + i * 2;
  return `${Math.floor(m / 60) % 24}:${String(m % 60).padStart(2, "0")}`;
});

// ── Per-link value at selected bin ───────────────────────────────────────────
function gpsAtBin(lid: string): number {
  if (!gpsData.value) return 0.35;
  const snap = gpsData.value.snapshots?.[binIdx.value];
  return snap?.links?.[lid] ?? 0.35;
}
function ttAtBin(lid: string): number {
  if (!ttData.value) return 0.35;
  const snap = ttData.value.snapshots?.[binIdx.value];
  return snap?.links?.[lid] ?? 0.35;
}
function sumoAtBin(lid: string): number {
  if (!sumoData.value) return 0.35;
  const ts = sumoData.value.scenarios?.[scenario.value]?.links?.[lid];
  return ts?.[binIdx.value] ?? 0.35;
}

// ── Color helpers ─────────────────────────────────────────────────────────────
function congColor(v: number): string {
  if (v >= 0.75) return "#ef4444";
  if (v >= 0.55) return "#f97316";
  if (v >= 0.33) return "#eab308";
  return "#22c55e";
}
function congBg(v: number): string {
  const r = Math.round(34 + (239 - 34) * Math.min(1, v / 0.98));
  const g = Math.round(197 - (197 - 68) * Math.min(1, v / 0.98));
  return `rgb(${r},${g},68)`;
}

// ── Net time series (for SVG chart) ──────────────────────────────────────────
const gpsNetTs = computed<number[]>(() => {
  if (!gpsData.value) return Array(N_BINS).fill(0.35);
  return gpsData.value.snapshots.map((s: any) => {
    const vals = Object.values(s.links) as number[];
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0.35;
  });
});
const ttNetTs = computed<number[]>(() => {
  if (!ttData.value) return Array(N_BINS).fill(0.35);
  return ttData.value.snapshots.map((s: any) => {
    const vals = Object.values(s.links) as number[];
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0.35;
  });
});
const sumoNetTs = computed<number[]>(() => {
  if (!sumoData.value) return Array(N_BINS).fill(0.1);
  return sumoData.value.scenarios?.[scenario.value]?.net_ts ?? Array(N_BINS).fill(0.1);
});

// ── SVG chart builder ─────────────────────────────────────────────────────────
const NET_W = 560;
const NET_H = 100;
const PAD_L = 32;
const PAD_R = 8;
const PAD_T = 8;
const PAD_B = 20;
const CW = NET_W - PAD_L - PAD_R;
const CH = NET_H - PAD_T - PAD_B;

function tsToPoints(ts: number[], maxV: number): string {
  return ts
    .map((v, i) => {
      const x = PAD_L + (i / (N_BINS - 1)) * CW;
      const y = PAD_T + CH - (v / maxV) * CH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

const chartData = computed(() => {
  const allVals = [...gpsNetTs.value, ...ttNetTs.value, ...sumoNetTs.value];
  const maxV = Math.max(...allVals, 0.5);
  return {
    maxV,
    gps:  tsToPoints(gpsNetTs.value, maxV),
    tt:   tsToPoints(ttNetTs.value,  maxV),
    sumo: tsToPoints(sumoNetTs.value, maxV),
    yLabels: [0, 0.25, 0.5, 0.75].filter(v => v <= maxV).map(v => ({
      v,
      y: PAD_T + CH - (v / maxV) * CH,
      label: v.toFixed(2),
    })),
    xBin: PAD_L + (binIdx.value / (N_BINS - 1)) * CW,
  };
});

// ── Per-link diff stats ───────────────────────────────────────────────────────
const linkStats = computed(() => {
  return LINK_ORDER.map(lid => {
    const gpsVals  = (gpsData.value?.snapshots ?? []).map((s: any) => s.links?.[lid] ?? 0.35) as number[];
    const ttVals   = (ttData.value?.snapshots  ?? []).map((s: any) => s.links?.[lid] ?? 0.35) as number[];
    const sumoVals = sumoData.value?.scenarios?.[scenario.value]?.links?.[lid] ?? Array(N_BINS).fill(0.35) as number[];
    const avg = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
    const gpsAvg  = avg(gpsVals);
    const ttAvg   = avg(ttVals);
    const sumoAvg = avg(sumoVals);
    const diffGps  = sumoAvg - gpsAvg;
    return { lid, gpsAvg, ttAvg, sumoAvg, diffGps };
  });
});

const SCENARIOS = [
  { key: "baseline",    label: "BASELINE",    color: "#f97316" },
  { key: "low_demand",  label: "LOW DEMAND",  color: "#22c55e" },
  { key: "high_demand", label: "HIGH DEMAND", color: "#ef4444" },
] as const;

const sumoAvailable = computed(() => !!sumoData.value);
</script>

<template>
  <div class="sim-page">
    <NavSidebar />
    <!-- Header -->
    <header class="sim-header">
      <div class="sim-header-left">
        <NuxtLink to="/" class="nav-link">← MAIN</NuxtLink>
        <NuxtLink to="/compare" class="nav-link">▶ COMPARE</NuxtLink>
        <NuxtLink to="/method-analysis" class="nav-link">▶ METHOD</NuxtLink>
      </div>
      <h1 class="sim-title">SUMO SIMULATION</h1>
      <div class="sim-header-right">
        <span class="subtitle">Chennai ITS · Traffic Demand Scenarios</span>
      </div>
    </header>

    <div v-if="loading" class="loading">Loading simulation data …</div>
    <div v-else class="sim-body">

      <!-- ── Scenario Tabs ─────────────────────────────────────────────────── -->
      <section class="scenario-bar">
        <button
          v-for="sc in SCENARIOS" :key="sc.key"
          class="sc-btn"
          :class="{ 'sc-active': scenario === sc.key }"
          :style="scenario === sc.key ? { borderColor: sc.color, color: sc.color } : {}"
          @click="scenario = sc.key"
        >{{ sc.label }}</button>
        <div class="sc-note">
          <span v-if="!sumoAvailable" class="warn">⚠ SUMO data not available — run preprocess_sumo.py</span>
          <span v-else class="ok">✓ SUMO 1.27 · OSM Chennai · 30-min simulation</span>
        </div>
      </section>

      <!-- ── Time Slider ────────────────────────────────────────────────────── -->
      <section class="time-bar">
        <span class="time-label">TIME:</span>
        <input
          type="range" min="0" :max="N_BINS - 1" step="1"
          v-model.number="binIdx"
          class="time-slider"
        />
        <span class="time-val">{{ TIME_LABELS[binIdx] }} IST</span>
        <div class="time-ticks">
          <span v-for="(t, i) in TIME_LABELS" :key="i"
            class="tick" :class="{ 'tick-active': i === binIdx }"
            @click="binIdx = i"
          >{{ t }}</span>
        </div>
      </section>

      <!-- ── Three-Panel Comparison ─────────────────────────────────────────── -->
      <section class="panels">
        <div class="panel">
          <div class="panel-head" style="color:#22c55e">GPS PROBE</div>
          <div class="grid64">
            <div
              v-for="lid in LINK_ORDER" :key="lid"
              class="cell64"
              :style="{ background: congBg(gpsAtBin(lid)) }"
              :title="`${lid}: ${gpsAtBin(lid).toFixed(3)}`"
            />
          </div>
          <div class="panel-avg">avg {{ (gpsNetTs[binIdx] ?? 0).toFixed(3) }}</div>
        </div>

        <div class="panel">
          <div class="panel-head" style="color:#a855f7">TT PROBE</div>
          <div class="grid64">
            <div
              v-for="lid in LINK_ORDER" :key="lid"
              class="cell64"
              :style="{ background: congBg(ttAtBin(lid)) }"
              :title="`${lid}: ${ttAtBin(lid).toFixed(3)}`"
            />
          </div>
          <div class="panel-avg">avg {{ (ttNetTs[binIdx] ?? 0).toFixed(3) }}</div>
        </div>

        <div class="panel">
          <div class="panel-head" :style="{ color: SCENARIOS.find(s => s.key === scenario)?.color }">
            SUMO · {{ scenario.replace('_', ' ').toUpperCase() }}
          </div>
          <div class="grid64">
            <div
              v-for="lid in LINK_ORDER" :key="lid"
              class="cell64"
              :style="{ background: congBg(sumoAtBin(lid)) }"
              :title="`${lid}: ${sumoAtBin(lid).toFixed(3)}`"
            />
          </div>
          <div class="panel-avg">avg {{ (sumoNetTs[binIdx] ?? 0).toFixed(3) }}</div>
        </div>
      </section>

      <!-- ── Legend ─────────────────────────────────────────────────────────── -->
      <div class="legend-row">
        <span class="leg-item" v-for="(l, c) in [['FREE','#22c55e'],['MOD','#eab308'],['HEAVY','#f97316'],['SEVERE','#ef4444']]" :key="l">
          <span class="leg-dot" :style="{ background: c }"/>{{ l }}
        </span>
        <span class="leg-note">64 schematic links · 8×8 grid</span>
      </div>

      <!-- ── Network Time Series ────────────────────────────────────────────── -->
      <section class="chart-section">
        <div class="chart-title">Network-Wide Congestion · 16:10–16:38 IST</div>
        <svg :width="NET_W" :height="NET_H" class="chart-svg">
          <!-- Y-axis labels -->
          <g v-for="yl in chartData.yLabels" :key="yl.v">
            <text :x="PAD_L - 4" :y="yl.y + 4" text-anchor="end" class="axis-txt">{{ yl.label }}</text>
            <line :x1="PAD_L" :y1="yl.y" :x2="PAD_L + CW" :y2="yl.y" stroke="#333" stroke-dasharray="2,4"/>
          </g>
          <!-- Bin cursor -->
          <line :x1="chartData.xBin" :y1="PAD_T" :x2="chartData.xBin" :y2="PAD_T + CH" stroke="#666" stroke-width="1" stroke-dasharray="3,3"/>
          <!-- GPS line -->
          <polyline :points="chartData.gps"  fill="none" stroke="#22c55e" stroke-width="2"/>
          <!-- TT line -->
          <polyline :points="chartData.tt"   fill="none" stroke="#a855f7" stroke-width="2"/>
          <!-- SUMO line -->
          <polyline :points="chartData.sumo" fill="none" stroke="#f97316" stroke-width="2.5" stroke-dasharray="6,3"/>
          <!-- X labels -->
          <text v-for="(t, i) in [0, 4, 9, 14]" :key="i"
            :x="PAD_L + (t / (N_BINS - 1)) * CW"
            :y="NET_H - 4"
            text-anchor="middle" class="axis-txt"
          >{{ TIME_LABELS[t] }}</text>
        </svg>
        <div class="chart-legend">
          <span class="cl-gps">● GPS</span>
          <span class="cl-tt">● TT</span>
          <span class="cl-sumo">╌ SUMO ({{ scenario.replace('_',' ') }})</span>
        </div>
      </section>

      <!-- ── All Scenarios Net-TS ───────────────────────────────────────────── -->
      <section class="chart-section">
        <div class="chart-title">SUMO Scenarios Comparison</div>
        <svg :width="NET_W" :height="NET_H" class="chart-svg">
          <g v-for="yl in chartData.yLabels" :key="yl.v">
            <line :x1="PAD_L" :y1="yl.y" :x2="PAD_L + CW" :y2="yl.y" stroke="#333" stroke-dasharray="2,4"/>
          </g>
          <polyline v-if="sumoData"
            :points="tsToPoints(sumoData.scenarios.low_demand.net_ts,  chartData.maxV)"
            fill="none" stroke="#22c55e" stroke-width="2"/>
          <polyline v-if="sumoData"
            :points="tsToPoints(sumoData.scenarios.baseline.net_ts,    chartData.maxV)"
            fill="none" stroke="#f97316" stroke-width="2"/>
          <polyline v-if="sumoData"
            :points="tsToPoints(sumoData.scenarios.high_demand.net_ts, chartData.maxV)"
            fill="none" stroke="#ef4444" stroke-width="2"/>
          <text v-for="(t, i) in [0, 4, 9, 14]" :key="i"
            :x="PAD_L + (t / (N_BINS - 1)) * CW"
            :y="NET_H - 4"
            text-anchor="middle" class="axis-txt"
          >{{ TIME_LABELS[t] }}</text>
        </svg>
        <div class="chart-legend">
          <span style="color:#22c55e">● LOW DEMAND</span>
          <span style="color:#f97316">● BASELINE</span>
          <span style="color:#ef4444">● HIGH DEMAND</span>
        </div>
      </section>

      <!-- ── Per-Link Diff Table ────────────────────────────────────────────── -->
      <section class="diff-section">
        <div class="diff-title">Per-Link Average Congestion · GPS vs TT vs SUMO ({{ scenario.replace('_',' ') }})</div>
        <div class="diff-table-wrap">
          <table class="diff-table">
            <thead>
              <tr>
                <th>Link</th>
                <th>GPS avg</th>
                <th>TT avg</th>
                <th>SUMO avg</th>
                <th>SUMO−GPS</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in linkStats" :key="row.lid">
                <td class="td-lid">{{ row.lid }}</td>
                <td :style="{ color: congColor(row.gpsAvg) }">{{ row.gpsAvg.toFixed(3) }}</td>
                <td :style="{ color: congColor(row.ttAvg) }">{{ row.ttAvg.toFixed(3) }}</td>
                <td :style="{ color: congColor(row.sumoAvg) }">{{ row.sumoAvg.toFixed(3) }}</td>
                <td :class="row.diffGps > 0.05 ? 'pos-diff' : row.diffGps < -0.05 ? 'neg-diff' : 'neu-diff'">
                  {{ (row.diffGps >= 0 ? '+' : '') + row.diffGps.toFixed(3) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="diff-note">
          SUMO uses uncalibrated random demand — lower absolute congestion is expected vs real probe data.
          Focus on <em>relative</em> differences across links and scenarios.
        </div>
      </section>

    </div>
  </div>
</template>

<style scoped>
.sim-page { background: #020818; min-height: 100vh; color: #e2e8f0; font-family: 'Courier New', monospace; padding-left: 52px; }

.sim-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; background: #111; border-bottom: 1px solid #1e293b;
}
.sim-header-left { display: flex; gap: 12px; }
.sim-header-right { font-size: 11px; color: #64748b; }
.nav-link { color: #64748b; text-decoration: none; font-size: 11px; padding: 4px 8px; border: 1px solid #333; border-radius: 3px; }
.nav-link:hover { color: #94a3b8; border-color: #475569; }
.sim-title { font-size: 16px; font-weight: 700; letter-spacing: 3px; color: #f97316; }
.subtitle { font-size: 11px; }

.loading { text-align: center; padding: 60px; color: #475569; font-size: 14px; }

.sim-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 16px; }

/* Scenario tabs */
.scenario-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sc-btn {
  padding: 6px 14px; font-family: inherit; font-size: 11px; font-weight: 700;
  background: #111; border: 1px solid #333; color: #64748b; cursor: pointer;
  border-radius: 3px; letter-spacing: 1px; transition: all 0.15s;
}
.sc-btn:hover { color: #94a3b8; border-color: #475569; }
.sc-active { background: #1a1a1a !important; }
.sc-note { margin-left: 12px; font-size: 11px; }
.warn { color: #f59e0b; }
.ok   { color: #22c55e; }

/* Time bar */
.time-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.time-label { font-size: 11px; color: #64748b; font-weight: 700; }
.time-slider { width: 200px; accent-color: #f97316; cursor: pointer; }
.time-val { font-size: 13px; color: #f97316; font-weight: 700; min-width: 50px; }
.time-ticks { display: flex; gap: 2px; flex-wrap: wrap; }
.tick {
  font-size: 9px; padding: 2px 4px; color: #475569; cursor: pointer;
  border-radius: 2px; transition: all 0.1s;
}
.tick:hover { color: #94a3b8; background: #1e293b; }
.tick-active { color: #f97316; background: #1a1200; font-weight: 700; }

/* Three panels */
.panels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.panel { background: #111; border: 1px solid #1e293b; border-radius: 6px; padding: 10px; }
.panel-head { font-size: 11px; font-weight: 700; letter-spacing: 2px; margin-bottom: 8px; text-align: center; }
.grid64 { display: grid; grid-template-columns: repeat(8, 1fr); gap: 2px; }
.cell64 { aspect-ratio: 1; border-radius: 1px; min-height: 12px; cursor: default; }
.panel-avg { margin-top: 6px; font-size: 11px; color: #64748b; text-align: center; }

/* Legend */
.legend-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 11px; }
.leg-item { display: flex; align-items: center; gap: 4px; }
.leg-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.leg-note { color: #475569; margin-left: auto; }

/* Charts */
.chart-section { background: #111; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; }
.chart-title { font-size: 11px; color: #64748b; letter-spacing: 1px; margin-bottom: 8px; }
.chart-svg { display: block; overflow: visible; }
.axis-txt { fill: #475569; font-size: 9px; font-family: 'Courier New', monospace; }
.chart-legend { display: flex; gap: 16px; margin-top: 6px; font-size: 11px; }
.cl-gps  { color: #22c55e; }
.cl-tt   { color: #a855f7; }
.cl-sumo { color: #f97316; }

/* Diff table */
.diff-section { background: #111; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; }
.diff-title { font-size: 11px; color: #64748b; letter-spacing: 1px; margin-bottom: 8px; }
.diff-table-wrap { max-height: 260px; overflow-y: auto; }
.diff-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.diff-table th { padding: 4px 8px; text-align: right; color: #475569; border-bottom: 1px solid #1e293b; font-weight: 400; position: sticky; top: 0; background: #111; }
.diff-table th:first-child, .diff-table td:first-child { text-align: left; }
.diff-table td { padding: 3px 8px; text-align: right; border-bottom: 1px solid #0f172a; }
.td-lid { color: #64748b; font-weight: 700; }
.pos-diff { color: #f97316; }
.neg-diff { color: #22c55e; }
.neu-diff { color: #475569; }
.diff-note { font-size: 10px; color: #475569; margin-top: 8px; font-style: italic; }
.diff-note em { color: #94a3b8; font-style: normal; }
</style>
