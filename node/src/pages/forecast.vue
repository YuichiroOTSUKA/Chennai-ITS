<script setup lang="ts">
const runtimeConfig = useRuntimeConfig();
const API = runtimeConfig.public.apiBase || "http://localhost:8100";

// ── State ──────────────────────────────────────────────────────────────────────
const bprData   = ref<any>(null);
const demand    = ref(1.0);
const loading   = ref(true);
const computing = ref(false);

const LINK_ORDER = Array.from({ length: 64 }, (_, i) => `l${String(i + 1).padStart(2, "0")}`);

// ── BPR precomputed table (all demand levels) ─────────────────────────────────
async function fetchBpr() {
  loading.value = true;
  try {
    bprData.value = await $fetch(API + "/traffic/bpr-params");
  } catch (e) {
    bprData.value = null;
  } finally {
    loading.value = false;
  }
}
onMounted(fetchBpr);

// ── Predict congestion from precomputed table ─────────────────────────────────
function nearestKey(d: number): string {
  const q = Math.max(0.5, Math.min(3.0, d));
  return (Math.round(q / 0.05) * 0.05).toFixed(2);
}

const forecastLinks = computed<Record<string, number>>(() => {
  if (!bprData.value) return {};
  const key = nearestKey(demand.value);
  const out: Record<string, number> = {};
  for (const lid of LINK_ORDER) {
    const p = bprData.value[lid];
    out[lid] = p ? (p.forecast[key] ?? p.real_cong) : 0.35;
  }
  return out;
});

const netReal = computed(() => {
  if (!bprData.value) return 0;
  const vals = LINK_ORDER.map(l => bprData.value[l]?.real_cong ?? 0.35);
  return vals.reduce((a, b) => a + b, 0) / vals.length;
});
const netPred = computed(() => {
  const vals = Object.values(forecastLinks.value);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
});

// ── Bottleneck table ──────────────────────────────────────────────────────────
const bottlenecks = computed(() => {
  if (!bprData.value) return [];
  return LINK_ORDER
    .map(lid => ({ lid, ...bprData.value[lid] }))
    .sort((a, b) => (a.sat_threshold ?? 99) - (b.sat_threshold ?? 99));
});

// ── Year estimation (5% annual growth) ───────────────────────────────────────
function demandToYear(d: number): string {
  if (d <= 1.0) return "TODAY";
  const years = Math.log(d) / Math.log(1.05);
  const y = Math.round(2026 + years);
  return `~${y}`;
}

// ── Color helpers ─────────────────────────────────────────────────────────────
function congColor(v: number): string {
  if (v >= 0.75) return "#ef4444";
  if (v >= 0.55) return "#f97316";
  if (v >= 0.33) return "#eab308";
  return "#22c55e";
}
function congBg(v: number): string {
  const t = Math.min(1, v / 0.98);
  const r = Math.round(34  + (239 - 34)  * t);
  const g = Math.round(197 - (197 - 68)  * t);
  return `rgb(${r},${g},68)`;
}
function satColor(sat: number | null): string {
  if (sat === null)  return "#22c55e";
  if (sat <= 1.25)   return "#ef4444";
  if (sat <= 1.5)    return "#f97316";
  if (sat <= 2.0)    return "#eab308";
  return "#22c55e";
}
function satLabel(sat: number | null): string {
  if (sat === null)  return "SAFE";
  if (sat <= 1.25)   return "CRITICAL";
  if (sat <= 1.5)    return "HIGH";
  if (sat <= 2.0)    return "MOD";
  return "LOW";
}

// ── Severe count at current demand slider ────────────────────────────────────
const severeCount = computed(() =>
  Object.values(forecastLinks.value).filter(v => v >= 0.75).length
);
const heavyCount = computed(() =>
  Object.values(forecastLinks.value).filter(v => v >= 0.55 && v < 0.75).length
);

// ── SVG: congestion vs demand curve for selected link ────────────────────────
const selectedLink = ref<string | null>(null);

const CURVE_W = 320;
const CURVE_H = 120;
const PAD_L = 36; const PAD_R = 8;
const PAD_T = 8;  const PAD_B = 22;
const CW = CURVE_W - PAD_L - PAD_R;
const CH = CURVE_H - PAD_T - PAD_B;

const curvePoints = computed(() => {
  if (!bprData.value || !selectedLink.value) return "";
  const p = bprData.value[selectedLink.value];
  if (!p) return "";
  const qs = Object.keys(p.forecast).map(Number).sort((a, b) => a - b);
  return qs
    .map(q => {
      const x = PAD_L + ((q - 0.5) / 2.5) * CW;
      const y = PAD_T + CH - (p.forecast[q.toFixed(2)] / 1.0) * CH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
});
const cursorX = computed(() => {
  return PAD_L + ((demand.value - 0.5) / 2.5) * CW;
});
const satLineX = computed(() => {
  if (!bprData.value || !selectedLink.value) return null;
  const sat = bprData.value[selectedLink.value]?.sat_threshold;
  if (!sat) return null;
  return PAD_L + ((sat - 0.5) / 2.5) * CW;
});
</script>

<template>
  <div class="fc-page">
    <!-- Header -->
    <header class="fc-header">
      <div class="fc-nav">
        <NuxtLink to="/" class="nav-link">← MAIN</NuxtLink>
        <NuxtLink to="/compare" class="nav-link">▶ COMPARE</NuxtLink>
        <NuxtLink to="/simulation" class="nav-link">▶ SIMULATION</NuxtLink>
      </div>
      <h1 class="fc-title">DEMAND FORECAST</h1>
      <div class="fc-subtitle">BPR Curve · Chennai ITS · Future Traffic Analysis</div>
    </header>

    <div v-if="loading" class="fc-loading">Loading BPR parameters …</div>
    <div v-else-if="!bprData" class="fc-loading" style="color:#ef4444">
      BPR data not available. Run <code>preprocess_bpr.py</code> first.
    </div>
    <div v-else class="fc-body">

      <!-- ── Demand Slider ──────────────────────────────────────────────────── -->
      <section class="demand-section">
        <div class="demand-row">
          <span class="demand-label">DEMAND MULTIPLIER</span>
          <input
            type="range" min="1.0" max="3.0" step="0.05"
            v-model.number="demand"
            class="demand-slider"
          />
          <div class="demand-display">
            <span class="demand-val">×{{ demand.toFixed(2) }}</span>
            <span class="demand-year">{{ demandToYear(demand) }}</span>
          </div>
        </div>
        <div class="demand-hint">
          <span>×1.00 = TODAY</span>
          <span>×1.28 = +5yr</span>
          <span>×1.63 = +10yr</span>
          <span>×2.08 = +15yr</span>
          <span>×2.65 = +20yr</span>
          <span class="hint-note">@ 5% annual vehicle growth</span>
        </div>
      </section>

      <!-- ── KPI Bar ────────────────────────────────────────────────────────── -->
      <section class="kpi-bar">
        <div class="kpi">
          <div class="kpi-val" :style="{ color: congColor(netReal) }">{{ netReal.toFixed(3) }}</div>
          <div class="kpi-label">NET CONG (NOW)</div>
        </div>
        <div class="kpi-arrow">→</div>
        <div class="kpi">
          <div class="kpi-val" :style="{ color: congColor(netPred) }">{{ netPred.toFixed(3) }}</div>
          <div class="kpi-label">NET CONG (×{{ demand.toFixed(2) }})</div>
        </div>
        <div class="kpi-sep"/>
        <div class="kpi">
          <div class="kpi-val" style="color:#ef4444">{{ severeCount }}</div>
          <div class="kpi-label">SEVERE LINKS</div>
        </div>
        <div class="kpi">
          <div class="kpi-val" style="color:#f97316">{{ heavyCount }}</div>
          <div class="kpi-label">HEAVY LINKS</div>
        </div>
        <div class="kpi-sep"/>
        <div class="kpi">
          <div class="kpi-val" style="color:#eab308">
            {{ bottlenecks.filter(b => (b.sat_threshold ?? 99) <= demand).length }}
          </div>
          <div class="kpi-label">SATURATED</div>
        </div>
        <div class="kpi">
          <div class="kpi-val" style="color:#64748b">
            {{ bottlenecks.filter(b => b.sat_threshold === null).length }}
          </div>
          <div class="kpi-label">NEVER SAT.</div>
        </div>
      </section>

      <!-- ── Main Layout: Grid + Table ─────────────────────────────────────── -->
      <div class="fc-main">

        <!-- 64-link forecast grid -->
        <section class="grid-section">
          <div class="grid-title">
            64-LINK FORECAST · ×{{ demand.toFixed(2) }} DEMAND
            <span class="grid-year">{{ demandToYear(demand) }}</span>
          </div>
          <div class="grid64">
            <div
              v-for="lid in LINK_ORDER" :key="lid"
              class="cell64"
              :class="{ 'cell-selected': selectedLink === lid }"
              :style="{ background: congBg(forecastLinks[lid] ?? 0.35) }"
              :title="`${lid}: ${(forecastLinks[lid] ?? 0.35).toFixed(3)}`"
              @click="selectedLink = selectedLink === lid ? null : lid"
            >
              <span v-if="(bprData[lid]?.sat_threshold ?? 99) <= demand" class="sat-dot">!</span>
            </div>
          </div>
          <div class="grid-legend">
            <span v-for="[l,c] in [['FREE','#22c55e'],['MOD','#eab308'],['HEAVY','#f97316'],['SEVERE','#ef4444']]" :key="l" class="leg-item">
              <span class="leg-dot" :style="{ background: c }"/>{{ l }}
            </span>
            <span class="leg-item"><span class="sat-dot-ex">!</span>SATURATED</span>
          </div>

          <!-- Selected link detail + BPR curve -->
          <div v-if="selectedLink && bprData[selectedLink]" class="link-detail">
            <div class="ld-title">
              {{ selectedLink }} · {{ bprData[selectedLink]?.real_cong != null ? '' : '' }}
              <span style="color:#64748b">{{ bprData[selectedLink]?.from ?? '' }}→{{ bprData[selectedLink]?.to ?? '' }}</span>
            </div>
            <div class="ld-stats">
              <span>NOW: <b :style="{color: congColor(bprData[selectedLink].real_cong)}">{{ bprData[selectedLink].real_cong.toFixed(3) }}</b></span>
              <span>PRED: <b :style="{color: congColor(forecastLinks[selectedLink] ?? 0)}">{{ (forecastLinks[selectedLink] ?? 0).toFixed(3) }}</b></span>
              <span>v/c: <b style="color:#94a3b8">{{ bprData[selectedLink].vc_ratio.toFixed(3) }}</b></span>
              <span>SAT: <b :style="{color: satColor(bprData[selectedLink].sat_threshold)}">
                {{ bprData[selectedLink].sat_threshold ? '×' + bprData[selectedLink].sat_threshold : 'SAFE' }}
              </b></span>
            </div>
            <!-- BPR curve SVG -->
            <svg :width="CURVE_W" :height="CURVE_H" class="curve-svg">
              <!-- Grid lines -->
              <line v-for="v in [0.25, 0.5, 0.75]" :key="v"
                :x1="PAD_L" :y1="PAD_T + CH - v*CH"
                :x2="PAD_L+CW" :y2="PAD_T + CH - v*CH"
                :stroke="v === 0.75 ? '#7f1d1d' : '#1e293b'" stroke-dasharray="3,4"/>
              <text v-for="v in [0, 0.25, 0.5, 0.75, 1.0]" :key="'y'+v"
                :x="PAD_L-4" :y="PAD_T+CH-v*CH+4"
                text-anchor="end" class="axis-txt">{{ v.toFixed(2) }}</text>
              <!-- Saturation threshold line -->
              <line v-if="satLineX !== null"
                :x1="satLineX" :y1="PAD_T" :x2="satLineX" :y2="PAD_T+CH"
                stroke="#ef4444" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>
              <!-- BPR curve -->
              <polyline :points="curvePoints" fill="none" stroke="#f97316" stroke-width="2"/>
              <!-- Current demand cursor -->
              <line :x1="cursorX" :y1="PAD_T" :x2="cursorX" :y2="PAD_T+CH"
                stroke="#94a3b8" stroke-width="1" stroke-dasharray="2,3"/>
              <!-- X labels -->
              <text v-for="q in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]" :key="q"
                :x="PAD_L + ((q-0.5)/2.5)*CW" :y="CURVE_H-4"
                text-anchor="middle" class="axis-txt">×{{ q.toFixed(1) }}</text>
              <!-- Axis labels -->
              <text :x="PAD_L-2" :y="PAD_T-2" text-anchor="end" class="axis-txt" fill="#64748b">CONG</text>
            </svg>
          </div>
        </section>

        <!-- Bottleneck table -->
        <section class="bt-section">
          <div class="bt-title">BOTTLENECK RANKING <span class="bt-note">sorted by saturation threshold</span></div>
          <div class="bt-table-wrap">
            <table class="bt-table">
              <thead>
                <tr>
                  <th>Link</th>
                  <th>Route</th>
                  <th>Now</th>
                  <th>×{{ demand.toFixed(1) }}</th>
                  <th>SAT@</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in bottlenecks" :key="row.lid"
                  :class="{ 'row-saturated': (row.sat_threshold ?? 99) <= demand, 'row-selected': selectedLink === row.lid }"
                  @click="selectedLink = selectedLink === row.lid ? null : row.lid"
                >
                  <td class="td-lid">{{ row.lid }}</td>
                  <td class="td-route">
                    <span v-if="bprData[row.lid]">{{ bprData[row.lid]?.from ?? '?' }}→{{ bprData[row.lid]?.to ?? '?' }}</span>
                  </td>
                  <td :style="{ color: congColor(row.real_cong) }">{{ row.real_cong.toFixed(3) }}</td>
                  <td :style="{ color: congColor(forecastLinks[row.lid] ?? 0) }">{{ (forecastLinks[row.lid] ?? 0).toFixed(3) }}</td>
                  <td>
                    <span v-if="row.sat_threshold"
                      :style="{ color: satColor(row.sat_threshold) }"
                    >×{{ row.sat_threshold }}</span>
                    <span v-else style="color:#22c55e">—</span>
                  </td>
                  <td>
                    <span class="risk-badge" :style="{
                      background: satColor(row.sat_threshold) + '22',
                      color: satColor(row.sat_threshold),
                      border: '1px solid ' + satColor(row.sat_threshold) + '44'
                    }">{{ satLabel(row.sat_threshold) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <!-- ── Method note ────────────────────────────────────────────────────── -->
      <div class="method-note">
        BPR model: <code>cong(m) = 1 − 1/(1 + 0.15·(m·v/c)₀^4)</code>
        · Current v/c calibrated from GPS+TT probe data (2026-03-18 16:10 IST)
        · Growth rate assumption: 5%/yr · Click any cell or row to show BPR curve
      </div>

    </div>
  </div>
</template>

<style scoped>
.fc-page { background: #0a0a0a; min-height: 100vh; color: #e2e8f0; font-family: 'Courier New', monospace; }

.fc-header {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
  padding: 12px 20px; background: #111; border-bottom: 1px solid #1e293b;
}
.fc-nav { display: flex; gap: 8px; }
.nav-link { color: #64748b; text-decoration: none; font-size: 11px; padding: 4px 8px; border: 1px solid #333; border-radius: 3px; }
.nav-link:hover { color: #94a3b8; border-color: #475569; }
.fc-title { font-size: 16px; font-weight: 700; letter-spacing: 3px; color: #6366f1; }
.fc-subtitle { font-size: 10px; color: #475569; }

.fc-loading { text-align: center; padding: 60px; color: #475569; }
.fc-loading code { color: #f97316; }

.fc-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }

/* Demand slider */
.demand-section { background: #111; border: 1px solid #1e293b; border-radius: 6px; padding: 14px 16px; }
.demand-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.demand-label { font-size: 11px; color: #64748b; font-weight: 700; letter-spacing: 1px; min-width: 140px; }
.demand-slider { flex: 1; max-width: 360px; accent-color: #6366f1; cursor: pointer; }
.demand-display { display: flex; align-items: baseline; gap: 10px; }
.demand-val { font-size: 22px; font-weight: 700; color: #6366f1; }
.demand-year { font-size: 13px; color: #94a3b8; font-weight: 700; }
.demand-hint { display: flex; gap: 12px; font-size: 10px; color: #475569; flex-wrap: wrap; }
.hint-note { margin-left: auto; color: #334155; }

/* KPI bar */
.kpi-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  background: #111; border: 1px solid #1e293b; border-radius: 6px; padding: 12px 16px;
}
.kpi { text-align: center; min-width: 70px; }
.kpi-val { font-size: 20px; font-weight: 700; }
.kpi-label { font-size: 9px; color: #475569; letter-spacing: 0.5px; }
.kpi-arrow { font-size: 18px; color: #334155; }
.kpi-sep { width: 1px; height: 36px; background: #1e293b; margin: 0 4px; }

/* Main layout */
.fc-main { display: grid; grid-template-columns: auto 1fr; gap: 14px; align-items: start; }
@media (max-width: 900px) { .fc-main { grid-template-columns: 1fr; } }

/* Grid */
.grid-section { background: #111; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; width: fit-content; }
.grid-title { font-size: 11px; color: #64748b; letter-spacing: 1px; margin-bottom: 8px; }
.grid-year { color: #6366f1; margin-left: 8px; }
.grid64 { display: grid; grid-template-columns: repeat(8, 1fr); gap: 3px; }
.cell64 {
  width: 28px; height: 28px; border-radius: 2px; cursor: pointer; position: relative;
  border: 1px solid transparent; transition: border-color 0.1s;
}
.cell64:hover { border-color: #94a3b8; }
.cell-selected { border-color: #6366f1 !important; }
.sat-dot { position: absolute; top: 1px; right: 2px; font-size: 8px; color: #fff; font-weight: 900; line-height: 1; }
.grid-legend { display: flex; gap: 12px; margin-top: 8px; font-size: 10px; flex-wrap: wrap; }
.leg-item { display: flex; align-items: center; gap: 4px; }
.leg-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.sat-dot-ex { font-size: 10px; font-weight: 900; color: #fff; background: #666; border-radius: 2px; padding: 0 2px; margin-right: 2px; }

/* Link detail */
.link-detail { margin-top: 12px; border-top: 1px solid #1e293b; padding-top: 10px; }
.ld-title { font-size: 11px; color: #94a3b8; margin-bottom: 6px; }
.ld-stats { display: flex; gap: 14px; font-size: 11px; color: #64748b; margin-bottom: 8px; flex-wrap: wrap; }
.ld-stats b { font-weight: 700; }
.curve-svg { display: block; overflow: visible; }
.axis-txt { fill: #475569; font-size: 9px; font-family: 'Courier New', monospace; }

/* Bottleneck table */
.bt-section { background: #111; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; }
.bt-title { font-size: 11px; color: #64748b; letter-spacing: 1px; margin-bottom: 8px; }
.bt-note { color: #334155; font-weight: 400; margin-left: 8px; }
.bt-table-wrap { max-height: 480px; overflow-y: auto; }
.bt-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.bt-table th { padding: 4px 8px; text-align: left; color: #475569; border-bottom: 1px solid #1e293b; font-weight: 400; position: sticky; top: 0; background: #111; white-space: nowrap; }
.bt-table th:nth-child(n+3) { text-align: right; }
.bt-table td { padding: 3px 8px; border-bottom: 1px solid #0f172a; white-space: nowrap; }
.bt-table td:nth-child(n+3) { text-align: right; }
.td-lid { color: #64748b; font-weight: 700; }
.td-route { color: #475569; font-size: 10px; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
.row-saturated { background: rgba(239,68,68,0.04); }
.row-saturated .td-lid { color: #ef4444; }
.row-selected { background: rgba(99,102,241,0.06) !important; }
.bt-table tr:hover { background: rgba(30,41,59,0.5); cursor: pointer; }
.risk-badge { font-size: 9px; padding: 1px 5px; border-radius: 2px; font-weight: 700; letter-spacing: 0.5px; }

/* Method note */
.method-note { font-size: 10px; color: #334155; line-height: 1.6; }
.method-note code { color: #64748b; }
</style>
