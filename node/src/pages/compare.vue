<script setup lang="ts">
const runtimeConfig = useRuntimeConfig();
const API = runtimeConfig.public.apiBase || "http://localhost:8100";

// ── データ取得 ────────────────────────────────────────────────────────────────
const gpsLinks   = ref<any[]>([]);
const ttLinks    = ref<any[]>([]);
const isections  = ref<any[]>([]);
const loading    = ref(true);

async function fetchAll() {
  loading.value = true;
  try {
    const [gps, tt, isc]: [any, any, any] = await Promise.all([
      $fetch(API + "/traffic/schematic?method=gps"),
      $fetch(API + "/traffic/schematic?method=tt"),
      $fetch(API + "/traffic/intersections"),
    ]);
    gpsLinks.value  = gps.links  ?? [];
    ttLinks.value   = tt.links   ?? [];
    isections.value = isc.result ?? [];
  } finally {
    loading.value = false;
  }
}

onMounted(fetchAll);

// ── 共通関数 ──────────────────────────────────────────────────────────────────
const congestionColor = (v: number) => {
  if (v >= 0.75) return "#ff2200";
  if (v >= 0.55) return "#ff8800";
  if (v >= 0.45) return "#ffdd00";
  if (v >= 0.25) return "#44cc66";
  return "#00ff88";
};
const congestionLabel = (v: number) => {
  if (v >= 0.75) return "Severe";
  if (v >= 0.55) return "Heavy";
  if (v >= 0.45) return "Moderate";
  if (v >= 0.25) return "Light";
  return "Free";
};

// ── リンク別平均 congestion ────────────────────────────────────────────────────
function linkAvgMap(links: any[]): Record<string, { avg: number; from: string; to: string }> {
  const m: Record<string, { avg: number; from: string; to: string }> = {};
  for (const l of links) {
    const fwd: number[] = l.forward ?? [];
    const avg = fwd.length ? fwd.reduce((a: number, b: number) => a + b, 0) / fwd.length : 0;
    m[l.id] = { avg: Math.round(avg * 1000) / 1000, from: l.from, to: l.to };
  }
  return m;
}

const gpsAvg = computed(() => linkAvgMap(gpsLinks.value));
const ttAvg  = computed(() => linkAvgMap(ttLinks.value));

// ── 差分テーブル (|diff| 降順) ─────────────────────────────────────────────────
const diffRows = computed(() => {
  const rows: Array<{
    id: string; from: string; to: string;
    gps: number; tt: number; diff: number; absDiff: number;
  }> = [];
  for (const [id, g] of Object.entries(gpsAvg.value)) {
    const t = ttAvg.value[id];
    if (!t) continue;
    const diff = Math.round((t.avg - g.avg) * 1000) / 1000;
    rows.push({ id, from: g.from, to: g.to, gps: g.avg, tt: t.avg, diff, absDiff: Math.abs(diff) });
  }
  return rows.sort((a, b) => b.absDiff - a.absDiff);
});

// ── サマリー統計 ───────────────────────────────────────────────────────────────
const summary = computed(() => {
  const rows = diffRows.value;
  if (!rows.length) return null;
  const gpsVals  = rows.map(r => r.gps);
  const ttVals   = rows.map(r => r.tt);
  const diffs    = rows.map(r => r.diff);
  const absDiffs = rows.map(r => r.absDiff);
  const avg = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
  const ttHigher  = rows.filter(r => r.diff >  0.05).length;
  const gpsHigher = rows.filter(r => r.diff < -0.05).length;
  const similar   = rows.length - ttHigher - gpsHigher;
  return {
    n: rows.length,
    gpsAvg:  Math.round(avg(gpsVals)  * 1000) / 1000,
    ttAvg:   Math.round(avg(ttVals)   * 1000) / 1000,
    meanDiff: Math.round(avg(diffs)   * 1000) / 1000,
    meanAbsDiff: Math.round(avg(absDiffs) * 1000) / 1000,
    maxAbsDiff: Math.round(Math.max(...absDiffs) * 1000) / 1000,
    ttHigher, gpsHigher, similar,
  };
});

// ── 散布図データ ──────────────────────────────────────────────────────────────
const SCATTER_W = 260;
const SCATTER_H = 260;
const PAD = 32;

const scatterPoints = computed(() =>
  diffRows.value.map(r => ({
    id: r.id, from: r.from, to: r.to,
    cx: PAD + r.gps * (SCATTER_W - PAD * 2),
    cy: SCATTER_H - PAD - r.tt * (SCATTER_H - PAD * 2),
    fill: diffColor(r.diff),
    gps: r.gps, tt: r.tt, diff: r.diff,
  }))
);

const hoveredPt = ref<any>(null);

// ── 差分カラー ────────────────────────────────────────────────────────────────
function diffColor(diff: number): string {
  if (diff >  0.30) return "#ff2200";
  if (diff >  0.15) return "#ff8800";
  if (diff >  0.05) return "#ffdd00";
  if (diff >= -0.05) return "#556677";
  if (diff >= -0.15) return "#44aaff";
  if (diff >= -0.30) return "#2255ff";
  return "#0022cc";
}
function diffLabel(diff: number): string {
  if (diff >  0.15) return "TT >> GPS";
  if (diff >  0.05) return "TT > GPS";
  if (diff >= -0.05) return "≈ 同等";
  if (diff >= -0.15) return "GPS > TT";
  return "GPS >> TT";
}
function pct(v: number): string { return (v * 100).toFixed(1) + "%"; }
</script>

<template>
  <div class="cmp-root">
    <NavSidebar />
    <!-- ヘッダー -->
    <header class="cmp-header">
      <NuxtLink to="/" class="back-btn">← BACK</NuxtLink>
      <div class="cmp-title">CHENNAI ITS — GPS vs TRAVEL TIME 比較</div>
      <NuxtLink to="/method-analysis"
        style="font-size:9px;font-family:monospace;color:#2a5070;border:1px solid #0f2040;padding:4px 10px;border-radius:3px;text-decoration:none;transition:color 0.12s;"
        onmouseover="this.style.color='#aa66ff'" onmouseout="this.style.color='#2a5070'">
        ▶ DEEP ANALYSIS
      </NuxtLink>
      <NuxtLink to="/simulation"
        style="font-size:9px;font-family:monospace;color:#7c3a00;border:1px solid #3a1a00;padding:4px 10px;border-radius:3px;text-decoration:none;transition:color 0.12s;"
        onmouseover="this.style.color='#f97316'" onmouseout="this.style.color='#7c3a00'">
        ▶ SIMULATION
      </NuxtLink>
      <button class="refresh-btn" @click="fetchAll" :disabled="loading">
        {{ loading ? "…" : "↺ REFRESH" }}
      </button>
    </header>

    <div v-if="loading" class="loading-overlay">LOADING DATA…</div>

    <div v-else class="cmp-body">

      <!-- ── サマリーバー ── -->
      <div class="summary-bar" v-if="summary">
        <div class="scard">
          <span class="slabel">リンク数</span>
          <span class="sval">{{ summary.n }}</span>
        </div>
        <div class="scard gps-card">
          <span class="slabel">GPS 平均混雑</span>
          <span class="sval">{{ pct(summary.gpsAvg) }}</span>
        </div>
        <div class="scard tt-card">
          <span class="slabel">TT 平均混雑</span>
          <span class="sval">{{ pct(summary.ttAvg) }}</span>
        </div>
        <div class="scard">
          <span class="slabel">平均差分 (TT-GPS)</span>
          <span class="sval" :style="{ color: summary.meanDiff > 0 ? '#ff8800' : '#44aaff' }">
            {{ summary.meanDiff >= 0 ? '+' : '' }}{{ pct(summary.meanDiff) }}
          </span>
        </div>
        <div class="scard">
          <span class="slabel">平均|差分|</span>
          <span class="sval">{{ pct(summary.meanAbsDiff) }}</span>
        </div>
        <div class="scard">
          <span class="slabel">最大|差分|</span>
          <span class="sval warn">{{ pct(summary.maxAbsDiff) }}</span>
        </div>
        <div class="verdict-chips">
          <span class="chip tt-chip">TT &gt; GPS × {{ summary.ttHigher }}</span>
          <span class="chip eq-chip">≈同等 × {{ summary.similar }}</span>
          <span class="chip gps-chip">GPS &gt; TT × {{ summary.gpsHigher }}</span>
        </div>
      </div>

      <!-- ── メインエリア ── -->
      <div class="cmp-main">

        <!-- 左: 2スケマティック並列 -->
        <div class="sch-col">
          <div class="sch-pane">
            <div class="pane-label gps-label">● GPS SPEED</div>
            <div class="sch-wrap">
              <SchematicMap
                :intersections="isections"
                :schematic-links="gpsLinks"
                :congestion-color="congestionColor"
                :congestion-label="congestionLabel"
                :compact="true"
              />
            </div>
          </div>
          <div class="sch-pane">
            <div class="pane-label tt-label">▶ TRAVEL TIME SPEED</div>
            <div class="sch-wrap">
              <SchematicMap
                :intersections="isections"
                :schematic-links="ttLinks"
                :congestion-color="congestionColor"
                :congestion-label="congestionLabel"
                :compact="true"
              />
            </div>
          </div>
        </div>

        <!-- 右: 散布図 + テーブル -->
        <div class="right-col">

          <!-- 散布図 -->
          <div class="scatter-section">
            <div class="section-title">GPS vs TT 散布図（各点 = 1リンク）</div>
            <div class="scatter-wrap">
              <svg :width="SCATTER_W" :height="SCATTER_H" class="scatter-svg">
                <!-- 軸背景 -->
                <rect :x="PAD" :y="PAD" :width="SCATTER_W-PAD*2" :height="SCATTER_H-PAD*2"
                      fill="rgba(4,12,30,0.8)" stroke="#0f2040" stroke-width="1"/>

                <!-- グリッド線 -->
                <g v-for="i in [0.25,0.5,0.75]" :key="i">
                  <line :x1="PAD + i*(SCATTER_W-PAD*2)" :y1="PAD"
                        :x2="PAD + i*(SCATTER_W-PAD*2)" :y2="SCATTER_H-PAD"
                        stroke="#0f2040" stroke-width="0.5"/>
                  <line :x1="PAD" :y1="SCATTER_H-PAD - i*(SCATTER_H-PAD*2)"
                        :x2="SCATTER_W-PAD" :y2="SCATTER_H-PAD - i*(SCATTER_H-PAD*2)"
                        stroke="#0f2040" stroke-width="0.5"/>
                </g>

                <!-- 対角線 (GPS=TT) -->
                <line :x1="PAD" :y1="SCATTER_H-PAD" :x2="SCATTER_W-PAD" :y2="PAD"
                      stroke="rgba(56,189,248,0.25)" stroke-width="1" stroke-dasharray="4 4"/>
                <text :x="SCATTER_W-PAD-2" :y="PAD+10" font-size="7" fill="rgba(56,189,248,0.3)"
                      text-anchor="end" font-family="monospace">GPS=TT</text>

                <!-- データ点 -->
                <circle v-for="pt in scatterPoints" :key="pt.id"
                        :cx="pt.cx" :cy="pt.cy" r="4"
                        :fill="pt.fill" opacity="0.82"
                        stroke="rgba(0,0,0,0.4)" stroke-width="0.5"
                        class="scatter-dot"
                        @mouseenter="hoveredPt = pt"
                        @mouseleave="hoveredPt = null"/>

                <!-- 軸ラベル -->
                <text :x="SCATTER_W/2" :y="SCATTER_H-4" text-anchor="middle"
                      font-size="8" fill="#2a5070" font-family="monospace">GPS 混雑度 →</text>
                <text :x="8" :y="SCATTER_H/2" text-anchor="middle"
                      font-size="8" fill="#2a5070" font-family="monospace"
                      :transform="`rotate(-90,8,${SCATTER_H/2})`">TT 混雑度 →</text>

                <!-- 軸目盛 -->
                <text v-for="v in [0,0.25,0.5,0.75,1.0]" :key="v"
                      :x="PAD + v*(SCATTER_W-PAD*2)" :y="SCATTER_H-PAD+10"
                      text-anchor="middle" font-size="6" fill="#1e3a5a" font-family="monospace">
                  {{ (v*100).toFixed(0) }}
                </text>
                <text v-for="v in [0.25,0.5,0.75,1.0]" :key="v"
                      :x="PAD-3" :y="SCATTER_H-PAD - v*(SCATTER_H-PAD*2) + 3"
                      text-anchor="end" font-size="6" fill="#1e3a5a" font-family="monospace">
                  {{ (v*100).toFixed(0) }}
                </text>
              </svg>

              <!-- ホバートゥールチップ -->
              <div v-if="hoveredPt" class="scatter-tooltip">
                <div class="tt-link-name">{{ hoveredPt.from }} → {{ hoveredPt.to }}</div>
                <div class="tt-row">
                  <span class="tt-key gps-col">GPS</span>
                  <span class="tt-val">{{ pct(hoveredPt.gps) }}</span>
                </div>
                <div class="tt-row">
                  <span class="tt-key tt-col">TT</span>
                  <span class="tt-val">{{ pct(hoveredPt.tt) }}</span>
                </div>
                <div class="tt-row">
                  <span class="tt-key">diff</span>
                  <span class="tt-val" :style="{ color: diffColor(hoveredPt.diff) }">
                    {{ hoveredPt.diff >= 0 ? '+' : '' }}{{ pct(hoveredPt.diff) }}
                  </span>
                </div>
              </div>

              <!-- 凡例 -->
              <div class="scatter-legend">
                <div v-for="[col,lbl] in [
                  ['#ff2200','TT >> GPS (>+30%)'],
                  ['#ff8800','TT > GPS (+15〜30%)'],
                  ['#ffdd00','TT > GPS (+5〜15%)'],
                  ['#556677','≈同等 (±5%)'],
                  ['#44aaff','GPS > TT (5〜15%)'],
                  ['#2255ff','GPS > TT (15〜30%)'],
                  ['#0022cc','GPS >> TT (>30%)'],
                ]" :key="lbl" class="leg-row">
                  <span class="leg-dot" :style="{ background: col }"/>
                  <span class="leg-text">{{ lbl }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 差分テーブル -->
          <div class="table-section">
            <div class="section-title">
              リンク別比較（|差分| 降順）
              <span class="tbl-hint">TT−GPS = 正 → TT が混雑高く推定</span>
            </div>
            <div class="tbl-wrap">
              <table class="diff-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>From → To</th>
                    <th class="gps-col">GPS</th>
                    <th class="tt-col">TT</th>
                    <th>差分</th>
                    <th class="bar-col">差分バー</th>
                    <th>判定</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in diffRows" :key="r.id"
                      :class="{ 'row-high': r.absDiff > 0.20 }">
                    <td class="id-cell">{{ r.id }}</td>
                    <td class="name-cell">{{ r.from }}<span class="arrow">→</span>{{ r.to }}</td>
                    <td class="val-cell gps-col">
                      <span class="val-badge" :style="{ background: congestionColor(r.gps) + '30', color: congestionColor(r.gps) }">
                        {{ pct(r.gps) }}
                      </span>
                    </td>
                    <td class="val-cell tt-col">
                      <span class="val-badge" :style="{ background: congestionColor(r.tt) + '30', color: congestionColor(r.tt) }">
                        {{ pct(r.tt) }}
                      </span>
                    </td>
                    <td class="diff-cell" :style="{ color: diffColor(r.diff) }">
                      {{ r.diff >= 0 ? '+' : '' }}{{ pct(r.diff) }}
                    </td>
                    <td class="bar-cell">
                      <div class="diff-bar-wrap">
                        <div class="diff-bar-center"/>
                        <div class="diff-bar-fill"
                             :style="{
                               width: Math.min(Math.abs(r.diff) * 200, 50) + '%',
                               left:  r.diff >= 0 ? '50%' : undefined,
                               right: r.diff <  0 ? '50%' : undefined,
                               background: diffColor(r.diff),
                             }"/>
                      </div>
                    </td>
                    <td class="verdict-cell" :style="{ color: diffColor(r.diff) }">
                      {{ diffLabel(r.diff) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

        </div><!-- /right-col -->
      </div><!-- /cmp-main -->
    </div><!-- /cmp-body -->
  </div>
</template>

<style scoped>
* { box-sizing: border-box; margin: 0; padding: 0; }

.cmp-root {
  width: 100vw; height: 100vh;
  background: #020818; color: #94a3b8;
  display: flex; flex-direction: column;
  font-family: "Segoe UI", system-ui, sans-serif;
  overflow: hidden;
  padding-left: 52px;
}

/* ── ヘッダー ── */
.cmp-header {
  display: flex; align-items: center; gap: 14px;
  padding: 7px 14px;
  background: rgba(2,8,24,0.97);
  border-bottom: 1px solid rgba(56,189,248,0.1);
  flex-shrink: 0;
}
.back-btn {
  font-size: 9px; font-family: monospace; color: #2a5070;
  text-decoration: none; border: 1px solid #0f2040;
  padding: 4px 10px; border-radius: 3px;
  transition: color 0.12s;
}
.back-btn:hover { color: #4488cc; }
.cmp-title {
  font-size: 11px; font-family: monospace; font-weight: 700;
  letter-spacing: 0.12em; color: #7090a0;
  flex: 1;
}
.refresh-btn {
  font-size: 9px; font-family: monospace; padding: 4px 10px;
  border-radius: 3px; cursor: pointer;
  background: rgba(4,12,30,0.9); border: 1px solid #0a2040;
  color: #2a5070; transition: all 0.12s;
}
.refresh-btn:hover:not(:disabled) { color: #4488cc; border-color: #1a4080; }
.refresh-btn:disabled { opacity: 0.4; cursor: default; }

.loading-overlay {
  flex: 1; display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-family: monospace; letter-spacing: 0.2em; color: #1e3a5a;
}

/* ── ボディ ── */
.cmp-body { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* ── サマリーバー ── */
.summary-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 6px 14px;
  background: rgba(4,10,26,0.9);
  border-bottom: 1px solid #0a1a30;
  flex-shrink: 0;
}
.scard {
  display: flex; flex-direction: column; align-items: center;
  padding: 4px 10px;
  background: rgba(6,14,32,0.8); border: 1px solid #0a1830; border-radius: 4px;
  min-width: 80px;
}
.scard.gps-card { border-color: #006630; }
.scard.tt-card  { border-color: #440088; }
.slabel { font-size: 7px; color: #1e3a5a; font-family: monospace; letter-spacing: 0.08em; }
.sval   { font-size: 13px; font-weight: 700; font-family: monospace; color: #7090a0; margin-top: 1px; }
.sval.warn { color: #ff8800; }

.verdict-chips { display: flex; gap: 5px; margin-left: 4px; }
.chip {
  font-size: 8px; font-family: monospace; font-weight: 700;
  padding: 3px 8px; border-radius: 3px; letter-spacing: 0.04em;
}
.tt-chip  { background: rgba(255,100,0,0.15); color: #ff8800; border: 1px solid #663300; }
.eq-chip  { background: rgba(40,60,80,0.3);   color: #445566; border: 1px solid #0f2030; }
.gps-chip { background: rgba(0,80,200,0.15);  color: #4488ff; border: 1px solid #002266; }

/* ── メインエリア ── */
.cmp-main {
  flex: 1; display: flex; overflow: hidden; gap: 0;
}

/* 左: スケマティック2連 */
.sch-col {
  width: 52%; display: flex; flex-direction: column;
  border-right: 1px solid #0a1a30;
  overflow: hidden;
}
.sch-pane {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  border-bottom: 1px solid #0a1a30;
}
.sch-pane:last-child { border-bottom: none; }
.pane-label {
  font-size: 8px; font-family: monospace; font-weight: 700; letter-spacing: 0.15em;
  padding: 4px 10px; flex-shrink: 0;
}
.gps-label { color: #00aa44; background: rgba(0,80,20,0.12); }
.tt-label  { color: #aa66ff; background: rgba(60,0,120,0.12); }
.sch-wrap  { flex: 1; overflow: hidden; }

/* 右: 散布図 + テーブル */
.right-col {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}

/* 散布図 */
.scatter-section {
  flex-shrink: 0;
  padding: 8px 12px;
  border-bottom: 1px solid #0a1a30;
}
.section-title {
  font-size: 8px; font-family: monospace; letter-spacing: 0.1em;
  color: rgba(56,189,248,0.3); margin-bottom: 6px;
  display: flex; align-items: baseline; gap: 10px;
}
.tbl-hint { font-size: 7px; color: #1a3050; }
.scatter-wrap { display: flex; gap: 10px; align-items: flex-start; }
.scatter-svg { flex-shrink: 0; }
.scatter-dot { cursor: crosshair; transition: r 0.1s; }
.scatter-dot:hover { r: 6; opacity: 1; }

.scatter-tooltip {
  background: rgba(2,8,24,0.96); border: 1px solid #0f2040;
  border-radius: 4px; padding: 7px 10px; min-width: 140px;
}
.tt-link-name {
  font-size: 8px; font-family: monospace; color: #94a3b8;
  margin-bottom: 5px; font-weight: 700;
}
.tt-row { display: flex; justify-content: space-between; gap: 8px; margin-top: 2px; }
.tt-key { font-size: 7px; font-family: monospace; color: #1e3a5a; }
.tt-val { font-size: 8px; font-family: monospace; font-weight: 700; color: #7090a0; }
.gps-col { color: #00cc55 !important; }
.tt-col  { color: #aa66ff !important; }

.scatter-legend {
  display: flex; flex-direction: column; gap: 3px; justify-content: center;
}
.leg-row { display: flex; align-items: center; gap: 5px; }
.leg-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  opacity: 0.85;
}
.leg-text { font-size: 7px; font-family: monospace; color: #1e3a5a; white-space: nowrap; }

/* テーブル */
.table-section {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  padding: 0 12px 8px;
}
.tbl-wrap {
  flex: 1; overflow-y: auto;
  border: 1px solid #0a1830; border-radius: 4px;
}
.diff-table {
  width: 100%; border-collapse: collapse;
  font-size: 8.5px; font-family: monospace;
}
.diff-table thead {
  position: sticky; top: 0; z-index: 2;
  background: rgba(4,10,28,0.98);
  border-bottom: 1px solid #0f2040;
}
.diff-table th {
  padding: 5px 8px; text-align: left;
  color: rgba(56,189,248,0.25); font-size: 7px; letter-spacing: 0.1em;
  font-weight: 700;
}
.diff-table td { padding: 4px 8px; border-bottom: 1px solid #06101e; }
.diff-table tr:last-child td { border-bottom: none; }
.diff-table tr:hover td { background: rgba(56,189,248,0.03); }
.diff-table tr.row-high td { background: rgba(255,80,0,0.04); }

.id-cell   { color: #1e3a5a; white-space: nowrap; }
.name-cell { color: #5a7a8a; max-width: 160px; }
.arrow     { color: #1e3a5a; margin: 0 3px; }
.val-cell  { text-align: right; }
.val-badge {
  display: inline-block; padding: 1px 5px; border-radius: 3px;
  font-size: 8px; font-weight: 700;
}
.diff-cell { text-align: right; font-weight: 700; }
.bar-col   { width: 100px; }
.bar-cell  { padding: 4px 8px; }
.diff-bar-wrap {
  position: relative; height: 5px;
  background: rgba(4,12,30,0.8); border-radius: 3px;
}
.diff-bar-center {
  position: absolute; left: 50%; top: 0;
  width: 1px; height: 100%; background: #0f2040;
}
.diff-bar-fill {
  position: absolute; top: 0; height: 100%;
  border-radius: 2px; opacity: 0.8;
  min-width: 2px;
}
.verdict-cell { color: #445566; font-size: 7.5px; white-space: nowrap; }

/* スクロールバー */
.tbl-wrap::-webkit-scrollbar { width: 4px; }
.tbl-wrap::-webkit-scrollbar-track { background: #020810; }
.tbl-wrap::-webkit-scrollbar-thumb { background: #0f2040; border-radius: 2px; }
</style>
