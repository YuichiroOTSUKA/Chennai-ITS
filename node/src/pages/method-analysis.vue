<script setup lang="ts">
const runtimeConfig = useRuntimeConfig();
const API = runtimeConfig.public.apiBase || "http://localhost:8100";

const loading   = ref(true);
const data      = ref<any>(null);
const selected  = ref<string | null>(null);
const heatmapMode = ref<"diff" | "absdiff">("diff");
const sortKey   = ref<"id" | "corr" | "mad" | "avg_n_trav" | "gps_avg" | "tt_avg" | "vol_ratio">("mad");
const sortAsc   = ref(false);
const scatterHover = ref<any>(null);

async function fetchData() {
  loading.value = true;
  try { data.value = await $fetch(API + "/traffic/method-comparison"); }
  catch { data.value = null; }
  finally { loading.value = false; }
}
onMounted(fetchData);

// ── Color helpers ─────────────────────────────────────────────────────────────
const CONF_COLOR: Record<string, string> = { high: "#22c55e", medium: "#eab308", low: "#ef4444" };
const REC_COLOR:  Record<string, string> = { tt: "#a855f7", blend: "#3b82f6", gps: "#22c55e" };
const REC_BG:     Record<string, string> = {
  tt:    "rgba(168,85,247,0.15)", blend: "rgba(59,130,246,0.15)", gps: "rgba(34,197,94,0.15)"
};
function congColor(v: number) {
  if (v >= 0.75) return "#ef4444";
  if (v >= 0.55) return "#f97316";
  if (v >= 0.33) return "#eab308";
  return "#22c55e";
}
function diffColor(d: number): string {
  const a = Math.abs(d);
  if (d >  0.20) return "rgba(239,68,68,0.90)";
  if (d >  0.10) return "rgba(249,115,22,0.85)";
  if (d >  0.04) return "rgba(234,179,8,0.75)";
  if (d >= -0.04) return "rgba(40,60,80,0.55)";
  if (d >= -0.10) return "rgba(56,189,248,0.75)";
  if (d >= -0.20) return "rgba(59,130,246,0.85)";
  return "rgba(99,102,241,0.90)";
}
function absDiffColor(d: number): string {
  const a = Math.abs(d);
  if (a > 0.20) return "rgba(239,68,68,0.90)";
  if (a > 0.10) return "rgba(249,115,22,0.80)";
  if (a > 0.04) return "rgba(234,179,8,0.70)";
  return "rgba(40,60,80,0.45)";
}
function corrColor(c: number): string {
  if (c >= 0.7)  return "#22c55e";
  if (c >= 0.4)  return "#84cc16";
  if (c >= 0.1)  return "#eab308";
  if (c >= -0.1) return "#64748b";
  return "#ef4444";
}
function pct(v: number) { return (v * 100).toFixed(1) + "%" }

// ── Sorted table ──────────────────────────────────────────────────────────────
const KEY_MAP: Record<string, string> = {
  id: "id", corr: "correlation", mad: "mad",
  avg_n_trav: "avg_n_trav", gps_avg: "gps_avg", tt_avg: "tt_avg", vol_ratio: "vol_ratio"
};
const sortedLinks = computed(() => {
  if (!data.value) return [];
  const links = [...data.value.links];
  const field = KEY_MAP[sortKey.value] ?? "mad";
  links.sort((a: any, b: any) => {
    const av = a[field]; const bv = b[field];
    if (typeof av === "string") return sortAsc.value ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortAsc.value ? av - bv : bv - av;
  });
  return links;
});
function setSort(k: typeof sortKey.value) {
  if (sortKey.value === k) sortAsc.value = !sortAsc.value;
  else { sortKey.value = k; sortAsc.value = false; }
}
function sortArrow(k: string) { return sortKey.value === k ? (sortAsc.value ? " ↑" : " ↓") : "" }

// ── Selected link ─────────────────────────────────────────────────────────────
const selLink = computed(() => data.value?.links.find((l: any) => l.id === selected.value) ?? null);

// ── SVG helpers ───────────────────────────────────────────────────────────────
function sparkPath(ts: number[], W: number, H: number, pad: number): string {
  if (!ts || ts.length < 2) return "";
  const mn = Math.min(...ts) - 0.02;
  const mx = Math.max(...ts) + 0.02;
  const xStep = (W - pad * 2) / (ts.length - 1);
  const y = (v: number) => pad + (1 - (v - mn) / (mx - mn)) * (H - pad * 2);
  return "M" + ts.map((v, i) => `${pad + i * xStep},${y(v)}`).join(" L");
}
function sparkPoint(ts: number[], i: number, W: number, H: number, pad: number): [number, number] {
  const mn = Math.min(...ts) - 0.02;
  const mx = Math.max(...ts) + 0.02;
  const xStep = (W - pad * 2) / (ts.length - 1);
  return [pad + i * xStep, pad + (1 - (ts[i] - mn) / (mx - mn)) * (H - pad * 2)];
}

// Network dual time series path (normalized 0-1 for shared axes)
const NET_W = 560, NET_H = 80, NET_PAD = 8;
function netPath(ts: number[]): string {
  if (!data.value) return "";
  // Use same axis as both GPS and TT together
  const all = [...data.value.network.gps_ts, ...data.value.network.tt_ts];
  const mn = Math.min(...all) - 0.01;
  const mx = Math.max(...all) + 0.01;
  const xStep = (NET_W - NET_PAD * 2) / (ts.length - 1);
  const y = (v: number) => NET_PAD + (1 - (v - mn) / (mx - mn)) * (NET_H - NET_PAD * 2);
  return "M" + ts.map((v: number, i: number) => `${NET_PAD + i * xStep},${y(v)}`).join(" L");
}

// Reliability scatter
const SCA_W = 260, SCA_H = 200, SCA_PX = 36, SCA_PY = 16;
const scatterPts = computed(() => {
  if (!data.value) return [];
  return data.value.links.map((lk: any) => {
    const maxN = Math.max(...data.value.links.map((l: any) => l.avg_n_trav));
    const x = SCA_PX + (lk.avg_n_trav / (maxN || 1)) * (SCA_W - SCA_PX - 12);
    const y = SCA_PY + (1 - (lk.correlation + 1) / 2) * (SCA_H - SCA_PY - 20);
    return { ...lk, cx: x, cy: y, fill: REC_COLOR[lk.recommendation] };
  });
});
const maxNTrav = computed(() =>
  data.value ? Math.max(...data.value.links.map((l: any) => l.avg_n_trav)) : 100
);
</script>

<template>
  <div class="min-h-screen bg-[#020818] text-[#c8d8e8] font-mono" style="padding-left:52px">
    <NavSidebar />
    <!-- Header -->
    <header class="border-b border-[#1a2535] px-5 py-2.5 flex items-center gap-4">
      <NuxtLink to="/"
        class="text-[9px] text-[#2a5070] hover:text-[#00aaff] border border-[#1a2535] hover:border-[#00aaff] px-2 py-1 rounded transition-colors">
        ← MAIN
      </NuxtLink>
      <NuxtLink to="/compare"
        class="text-[9px] text-[#2a5070] hover:text-[#6688aa] border border-[#1a2535] px-2 py-1 rounded transition-colors">
        ⇄ COMPARE
      </NuxtLink>
      <div class="flex-1">
        <div class="text-[11px] font-bold text-[#6a9ab0] tracking-widest">GPS vs TRAVEL-TIME · METHOD ANALYSIS</div>
        <div class="text-[8px] text-[#2a4060]">64 LINKS · 15 TIME BINS (16:10–16:38 IST) · BUS PROBE 2026-03-18</div>
      </div>
      <button @click="fetchData" :disabled="loading"
        class="text-[9px] border border-[#1a2535] hover:border-[#00aaff] text-[#2a5070] hover:text-[#00aaff] px-3 py-1 rounded transition-colors disabled:opacity-40">
        ↺ REFRESH
      </button>
    </header>

    <div v-if="loading" class="flex items-center justify-center h-64 text-[#2a5070] text-xs animate-pulse">
      COMPUTING…
    </div>
    <div v-else-if="!data" class="flex items-center justify-center h-64 text-[#ef4444] text-xs">
      DATA UNAVAILABLE
    </div>

    <div v-else class="p-4 space-y-4">

      <!-- ── Network summary bar ── -->
      <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-3 flex flex-wrap items-center gap-3">
        <div v-for="[lbl, val, col] in [
          ['GPS AVG', pct(data.network.gps_avg), '#22c55e'],
          ['TT AVG',  pct(data.network.tt_avg),  '#a855f7'],
          ['MEAN |MAD|', pct(data.network.mean_mad), '#f97316'],
          ['MEAN RMSE',  pct(data.network.mean_rmse), '#ef4444'],
          ['MEAN CORR', data.network.mean_corr.toFixed(3), corrColor(data.network.mean_corr)],
        ]" :key="lbl"
          class="flex flex-col items-center px-4 py-2 bg-[#06101e] border border-[#1a2535] rounded min-w-[80px]">
          <div class="text-[7px] text-[#2a4060] tracking-widest">{{ lbl }}</div>
          <div class="text-lg font-bold mt-0.5" :style="{ color: col }">{{ val }}</div>
        </div>
        <div class="flex items-center gap-2 ml-auto">
          <div v-for="[rec, count] in [['tt', data.network.rec_tt], ['blend', data.network.rec_blend], ['gps', data.network.rec_gps]]"
            :key="rec"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded text-[9px] font-bold border"
            :style="{ color: REC_COLOR[rec], background: REC_BG[rec], borderColor: REC_COLOR[rec] + '50' }">
            <span class="text-[10px]">{{ { tt: '▶TT', blend: '⊕BLEND', gps: '●GPS' }[rec] }}</span>
            <span>× {{ count }}</span>
          </div>
        </div>
      </section>

      <!-- ── Network dual time series ── -->
      <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-3">
        <div class="text-[9px] font-bold text-[#4a7090] tracking-widest mb-2 flex items-center gap-4">
          NETWORK-WIDE TIME SERIES
          <span class="flex items-center gap-1.5 text-[#22c55e]"><span class="w-3 h-0.5 bg-[#22c55e] inline-block"></span>GPS</span>
          <span class="flex items-center gap-1.5 text-[#a855f7]"><span class="w-3 h-0.5 bg-[#a855f7] inline-block"></span>TT</span>
          <span class="text-[#2a4060] font-normal ml-auto">convergence/divergence over 16:10–16:38 window</span>
        </div>
        <svg :viewBox="`0 0 ${NET_W} ${NET_H}`" class="w-full h-20" preserveAspectRatio="none">
          <defs>
            <linearGradient id="gGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#22c55e" stop-opacity="0.15"/>
              <stop offset="100%" stop-color="#22c55e" stop-opacity="0"/>
            </linearGradient>
            <linearGradient id="tGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#a855f7" stop-opacity="0.12"/>
              <stop offset="100%" stop-color="#a855f7" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <line v-for="i in 3" :key="i"
            :x1="NET_PAD" :y1="NET_PAD + (i/4)*(NET_H - NET_PAD*2)"
            :x2="NET_W - NET_PAD" :y2="NET_PAD + (i/4)*(NET_H - NET_PAD*2)"
            stroke="#1a2535" stroke-width="0.5"/>
          <path :d="netPath(data.network.gps_ts) + ` L${NET_W - NET_PAD},${NET_H} L${NET_PAD},${NET_H} Z`"
            fill="url(#gGrad)"/>
          <path :d="netPath(data.network.tt_ts) + ` L${NET_W - NET_PAD},${NET_H} L${NET_PAD},${NET_H} Z`"
            fill="url(#tGrad)"/>
          <path :d="netPath(data.network.gps_ts)" fill="none" stroke="#22c55e" stroke-width="1.5"/>
          <path :d="netPath(data.network.tt_ts)"  fill="none" stroke="#a855f7" stroke-width="1.5"/>
        </svg>
        <div class="flex justify-between mt-0.5">
          <span v-for="(t, i) in data.time_labels" :key="i"
            class="text-[7px] text-[#1a2535]"
            :style="{ display: i % 2 === 0 ? 'block' : 'none' }">{{ t }}</span>
        </div>
      </section>

      <!-- ── Heatmap + Detail (side by side) ── -->
      <div class="flex gap-4">

        <!-- Difference heatmap -->
        <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-3 flex-1 min-w-0">
          <div class="flex items-center gap-3 mb-2">
            <span class="text-[9px] font-bold text-[#4a7090] tracking-widest">DIFFERENCE HEATMAP</span>
            <button v-for="m in [['diff','GPS−TT'], ['absdiff','|GPS−TT|']]" :key="m[0]"
              @click="heatmapMode = m[0] as any"
              class="text-[8px] px-2 py-0.5 rounded border transition-colors"
              :class="heatmapMode === m[0]
                ? 'bg-[#002040] border-[#00aaff] text-[#00aaff]'
                : 'border-[#1a2535] text-[#2a4060] hover:text-[#4a7090]'">
              {{ m[1] }}
            </button>
            <span class="text-[8px] text-[#2a4060] ml-auto">click row → detail</span>
          </div>

          <!-- Legend -->
          <div class="flex items-center gap-1 mb-1.5 text-[7px]">
            <template v-if="heatmapMode === 'diff'">
              <span class="w-3 h-2.5 rounded-sm" style="background:rgba(99,102,241,0.90)"></span><span class="text-[#2a4060]">GPS≫TT</span>
              <span class="w-3 h-2.5 rounded-sm ml-1" style="background:rgba(56,189,248,0.75)"></span><span class="text-[#2a4060]">GPS&gt;TT</span>
              <span class="w-3 h-2.5 rounded-sm ml-1" style="background:rgba(40,60,80,0.55)"></span><span class="text-[#2a4060]">≈equal</span>
              <span class="w-3 h-2.5 rounded-sm ml-1" style="background:rgba(234,179,8,0.75)"></span><span class="text-[#2a4060]">TT&gt;GPS</span>
              <span class="w-3 h-2.5 rounded-sm ml-1" style="background:rgba(239,68,68,0.90)"></span><span class="text-[#2a4060]">TT≫GPS</span>
            </template>
            <template v-else>
              <span class="w-3 h-2.5 rounded-sm" style="background:rgba(40,60,80,0.45)"></span><span class="text-[#2a4060]">≈0</span>
              <span class="w-3 h-2.5 rounded-sm ml-1" style="background:rgba(234,179,8,0.70)"></span><span class="text-[#2a4060]">&gt;4%</span>
              <span class="w-3 h-2.5 rounded-sm ml-1" style="background:rgba(249,115,22,0.80)"></span><span class="text-[#2a4060]">&gt;10%</span>
              <span class="w-3 h-2.5 rounded-sm ml-1" style="background:rgba(239,68,68,0.90)"></span><span class="text-[#2a4060]">&gt;20%</span>
            </template>
          </div>

          <!-- Time header -->
          <div class="flex gap-px mb-px pl-[104px]">
            <div v-for="t in data.time_labels" :key="t"
              class="flex-1 text-center text-[6px] text-[#1a2535] truncate">{{ t }}</div>
          </div>

          <!-- Link rows -->
          <div class="space-y-px">
            <div v-for="lk in data.links" :key="lk.id"
              class="flex gap-px items-center group cursor-pointer"
              @click="selected = selected === lk.id ? null : lk.id">
              <div class="w-[102px] shrink-0 text-right pr-1.5 text-[7px] truncate"
                :class="selected === lk.id ? 'text-[#00aaff]' : 'text-[#1a3050] group-hover:text-[#3a6080]'">
                {{ lk.from.split(' ')[0] }}–{{ lk.to.split(' ')[0] }}
              </div>
              <div v-for="(d, si) in lk.diff_ts" :key="si"
                class="flex-1 h-3.5 rounded-[1px] transition-opacity"
                :style="{
                  backgroundColor: heatmapMode === 'diff' ? diffColor(d) : absDiffColor(d),
                  opacity: selected && selected !== lk.id ? '0.3' : '1'
                }"
                :title="`${lk.id} @ ${data.time_labels[si]}: GPS=${lk.gps_ts[si].toFixed(3)} TT=${lk.tt_ts[si].toFixed(3)} diff=${d.toFixed(3)}`"
              />
            </div>
          </div>
        </section>

        <!-- Detail panel -->
        <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-3 w-72 shrink-0">
          <div class="text-[9px] font-bold text-[#4a7090] tracking-widest mb-2">LINK DETAIL</div>

          <div v-if="!selLink" class="text-[9px] text-[#1a3050] py-8 text-center">
            ← click a row in the heatmap
          </div>

          <div v-else>
            <!-- ID + recommendation badge -->
            <div class="flex items-center justify-between mb-2">
              <div>
                <div class="text-[10px] font-bold text-[#00aaff]">{{ selLink.id }}</div>
                <div class="text-[8px] text-[#4a7090]">{{ selLink.from }} → {{ selLink.to }}</div>
              </div>
              <div class="text-[9px] font-bold px-2 py-1 rounded border"
                :style="{ color: REC_COLOR[selLink.recommendation], background: REC_BG[selLink.recommendation], borderColor: REC_COLOR[selLink.recommendation] + '60' }">
                {{ { tt:'▶ USE TT', blend:'⊕ BLEND', gps:'● USE GPS' }[selLink.recommendation] }}
              </div>
            </div>

            <!-- GPS vs TT time series overlay -->
            <div class="text-[7px] text-[#2a4060] mb-1">GPS (green) vs TT (purple) over time</div>
            <svg viewBox="0 0 260 70" class="w-full h-16" preserveAspectRatio="none">
              <line v-for="i in 3" :key="i"
                x1="6" :y1="6 + i/4*58" x2="254" :y2="6 + i/4*58"
                stroke="#1a2535" stroke-width="0.5"/>
              <path :d="sparkPath(selLink.gps_ts, 260, 70, 6) + ` L254,70 L6,70 Z`"
                fill="rgba(34,197,94,0.07)"/>
              <path :d="sparkPath(selLink.tt_ts,  260, 70, 6) + ` L254,70 L6,70 Z`"
                fill="rgba(168,85,247,0.07)"/>
              <path :d="sparkPath(selLink.gps_ts, 260, 70, 6)" fill="none" stroke="#22c55e" stroke-width="1.5"/>
              <path :d="sparkPath(selLink.tt_ts,  260, 70, 6)" fill="none" stroke="#a855f7" stroke-width="1.5"/>
              <circle v-for="(v, i) in selLink.gps_ts" :key="`g${i}`"
                :cx="sparkPoint(selLink.gps_ts, i, 260, 70, 6)[0]"
                :cy="sparkPoint(selLink.gps_ts, i, 260, 70, 6)[1]"
                r="2" :fill="congColor(v)"/>
              <circle v-for="(v, i) in selLink.tt_ts" :key="`t${i}`"
                :cx="sparkPoint(selLink.tt_ts, i, 260, 70, 6)[0]"
                :cy="sparkPoint(selLink.tt_ts, i, 260, 70, 6)[1]"
                r="2" fill="#a855f7"/>
            </svg>
            <div class="flex justify-between">
              <span v-for="(t, i) in data.time_labels" :key="i"
                :style="{ display: i % 4 === 0 || i === data.time_labels.length-1 ? 'block' : 'none' }"
                class="text-[6px] text-[#1a2535]">{{ t }}</span>
            </div>

            <!-- n_trav bars -->
            <div class="text-[7px] text-[#2a4060] mt-2 mb-1">TT sample size per bin (n_trav)</div>
            <div class="flex items-end gap-px h-8">
              <div v-for="(n, i) in selLink.n_trav_ts" :key="i"
                class="flex-1 rounded-t-sm transition-all"
                :style="{
                  height: (n / (Math.max(...selLink.n_trav_ts) || 1) * 100) + '%',
                  minHeight: n > 0 ? '2px' : '0',
                  background: n >= 30 ? '#a855f7' : n >= 10 ? '#3b82f6' : n >= 2 ? '#eab308' : '#1a2535'
                }"
                :title="`${data.time_labels[i]}: n_trav=${n}`"/>
            </div>
            <div class="flex gap-2 mt-1 text-[6px] text-[#2a4060]">
              <span><span class="text-[#a855f7]">■</span> ≥30</span>
              <span><span class="text-[#3b82f6]">■</span> ≥10</span>
              <span><span class="text-[#eab308]">■</span> ≥2</span>
              <span><span class="text-[#1a2535]">■</span> 0</span>
            </div>

            <!-- Stats grid -->
            <div class="grid grid-cols-2 gap-1 mt-3 text-[8px]">
              <div v-for="[k, v, c] in [
                ['GPS avg', pct(selLink.gps_avg), '#22c55e'],
                ['TT avg',  pct(selLink.tt_avg),  '#a855f7'],
                ['GPS std', pct(selLink.gps_std), '#64748b'],
                ['TT std',  pct(selLink.tt_std),  '#64748b'],
                ['MAD',     pct(selLink.mad),      '#f97316'],
                ['RMSE',    pct(selLink.rmse),     '#ef4444'],
                ['Corr',    selLink.correlation.toFixed(3), corrColor(selLink.correlation)],
                ['avg n',   selLink.avg_n_trav.toFixed(1), '#6a9ab0'],
                ['vol ratio', selLink.vol_ratio.toFixed(2), selLink.vol_ratio > 1.2 ? '#ef4444' : selLink.vol_ratio < 0.8 ? '#22c55e' : '#64748b'],
                ['conf',    selLink.confidence, CONF_COLOR[selLink.confidence]],
              ]" :key="k"
                class="flex justify-between items-center px-2 py-1 bg-[#06101e] rounded border border-[#1a2535]">
                <span class="text-[#2a4060]">{{ k }}</span>
                <span class="font-bold" :style="{ color: c }">{{ v }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- ── Reliability scatter + Volatility ── -->
      <div class="flex gap-4">

        <!-- Reliability scatter: avg_n_trav vs correlation -->
        <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-3 w-80 shrink-0">
          <div class="text-[9px] font-bold text-[#4a7090] tracking-widest mb-2">
            RELIABILITY SCATTER
            <span class="text-[7px] font-normal text-[#2a4060] ml-2">X=avg n_trav · Y=correlation</span>
          </div>
          <svg :viewBox="`0 0 ${SCA_W} ${SCA_H}`" class="w-full" style="height:200px" preserveAspectRatio="xMidYMid meet">
            <!-- Grid -->
            <rect :x="SCA_PX" :y="SCA_PY" :width="SCA_W-SCA_PX-12" :height="SCA_H-SCA_PY-20"
              fill="rgba(4,10,24,0.6)" stroke="#1a2535" stroke-width="0.5"/>
            <line v-for="c in [-0.5, 0, 0.5]" :key="c"
              :x1="SCA_PX" :y1="SCA_PY + (1-(c+1)/2)*(SCA_H-SCA_PY-20)"
              :x2="SCA_W-12" :y2="SCA_PY + (1-(c+1)/2)*(SCA_H-SCA_PY-20)"
              :stroke="c === 0 ? '#2a5070' : '#1a2535'" stroke-width="0.5" stroke-dasharray="2 2"/>
            <text v-for="c in [-1, -0.5, 0, 0.5, 1]" :key="c"
              :x="SCA_PX - 2" :y="SCA_PY + (1-(c+1)/2)*(SCA_H-SCA_PY-20)+3"
              text-anchor="end" font-size="6" fill="#1a3050" font-family="monospace">{{ c }}</text>
            <!-- X axis labels -->
            <text v-for="(v, i) in [0, Math.round(maxNTrav/2), Math.round(maxNTrav)]" :key="i"
              :x="SCA_PX + (v/(maxNTrav||1))*(SCA_W-SCA_PX-12)"
              :y="SCA_H-4" text-anchor="middle" font-size="6" fill="#1a3050" font-family="monospace">{{ v }}</text>
            <!-- Threshold lines -->
            <line :x1="SCA_PX + (10/(maxNTrav||1))*(SCA_W-SCA_PX-12)" :y1="SCA_PY"
                  :x2="SCA_PX + (10/(maxNTrav||1))*(SCA_W-SCA_PX-12)" :y2="SCA_H-20"
                  stroke="#3b82f6" stroke-width="0.7" stroke-dasharray="3 2" opacity="0.4"/>
            <line :x1="SCA_PX + (30/(maxNTrav||1))*(SCA_W-SCA_PX-12)" :y1="SCA_PY"
                  :x2="SCA_PX + (30/(maxNTrav||1))*(SCA_W-SCA_PX-12)" :y2="SCA_H-20"
                  stroke="#a855f7" stroke-width="0.7" stroke-dasharray="3 2" opacity="0.4"/>
            <!-- Points -->
            <circle v-for="pt in scatterPts" :key="pt.id"
              :cx="pt.cx" :cy="pt.cy" r="4.5"
              :fill="pt.fill" opacity="0.75" stroke="rgba(0,0,0,0.3)" stroke-width="0.5"
              class="cursor-pointer"
              @mouseenter="scatterHover = pt"
              @mouseleave="scatterHover = null"
              @click="selected = selected === pt.id ? null : pt.id"/>
            <!-- Axis labels -->
            <text :x="SCA_PX + (SCA_W-SCA_PX-12)/2" :y="SCA_H-10"
              text-anchor="middle" font-size="7" fill="#1a3050" font-family="monospace">avg n_trav →</text>
          </svg>
          <!-- Hover tooltip -->
          <div v-if="scatterHover" class="text-[8px] mt-1 bg-[#06101e] border border-[#1a2535] rounded px-2 py-1.5">
            <div class="text-[#6a9ab0] font-bold">{{ scatterHover.id }} — {{ scatterHover.from }} → {{ scatterHover.to }}</div>
            <div class="flex gap-4 mt-0.5 text-[#2a4060]">
              <span>n_trav <span :style="{ color: '#6a9ab0' }">{{ scatterHover.avg_n_trav }}</span></span>
              <span>corr <span :style="{ color: corrColor(scatterHover.correlation) }">{{ scatterHover.correlation }}</span></span>
              <span>MAD <span class="text-[#f97316]">{{ pct(scatterHover.mad) }}</span></span>
            </div>
          </div>
          <!-- Legend -->
          <div class="flex gap-3 mt-2 text-[7px]">
            <span v-for="[rec, lbl] in [['tt','▶ TT'], ['blend','⊕ BLEND'], ['gps','● GPS']]" :key="rec"
              class="flex items-center gap-1" :style="{ color: REC_COLOR[rec] }">
              <span class="w-2 h-2 rounded-full inline-block" :style="{ background: REC_COLOR[rec] }"></span>
              {{ lbl }}
            </span>
          </div>
        </section>

        <!-- Stats table -->
        <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-3 flex-1 min-w-0">
          <div class="text-[9px] font-bold text-[#4a7090] tracking-widest mb-2">
            LINK COMPARISON TABLE
            <span class="text-[7px] font-normal text-[#2a4060] ml-2">click header to sort · click row to inspect</span>
          </div>
          <div class="overflow-auto max-h-64">
            <table class="w-full text-[8px] border-collapse">
              <thead class="sticky top-0 bg-[#0a0f1a]">
                <tr class="text-[#2a4060] border-b border-[#1a2535]">
                  <th class="text-left py-1 pr-2 font-normal cursor-pointer hover:text-[#00aaff]" @click="setSort('id')">
                    ID{{ sortArrow('id') }}</th>
                  <th class="text-left py-1 pr-2 font-normal text-[8px] max-w-[120px]">FROM → TO</th>
                  <th class="text-right py-1 pr-2 font-normal cursor-pointer hover:text-[#22c55e]" @click="setSort('gps_avg')"
                    :class="sortKey === 'gps_avg' ? 'text-[#22c55e]' : ''">GPS{{ sortArrow('gps_avg') }}</th>
                  <th class="text-right py-1 pr-2 font-normal cursor-pointer hover:text-[#a855f7]" @click="setSort('tt_avg')"
                    :class="sortKey === 'tt_avg' ? 'text-[#a855f7]' : ''">TT{{ sortArrow('tt_avg') }}</th>
                  <th class="text-right py-1 pr-2 font-normal cursor-pointer hover:text-[#00aaff]" @click="setSort('mad')"
                    :class="sortKey === 'mad' ? 'text-[#00aaff]' : ''">MAD{{ sortArrow('mad') }}</th>
                  <th class="text-right py-1 pr-2 font-normal cursor-pointer hover:text-[#00aaff]" @click="setSort('corr')"
                    :class="sortKey === 'corr' ? 'text-[#00aaff]' : ''">CORR{{ sortArrow('corr') }}</th>
                  <th class="text-right py-1 pr-2 font-normal cursor-pointer hover:text-[#00aaff]" @click="setSort('avg_n_trav')"
                    :class="sortKey === 'avg_n_trav' ? 'text-[#00aaff]' : ''">N{{ sortArrow('avg_n_trav') }}</th>
                  <th class="text-right py-1 pr-2 font-normal cursor-pointer hover:text-[#00aaff]" @click="setSort('vol_ratio')"
                    :class="sortKey === 'vol_ratio' ? 'text-[#00aaff]' : ''">VOL{{ sortArrow('vol_ratio') }}</th>
                  <th class="text-right py-1 font-normal">REC</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="lk in sortedLinks" :key="lk.id"
                  class="border-b border-[#060e1a] cursor-pointer transition-colors hover:bg-[#0e1520]"
                  :class="selected === lk.id ? 'bg-[#001830]' : ''"
                  @click="selected = selected === lk.id ? null : lk.id">
                  <td class="py-1 pr-2 text-[#2a5070]">{{ lk.id }}</td>
                  <td class="py-1 pr-2 text-[#3a5060] truncate max-w-[120px]">{{ lk.from.split(' ')[0] }}–{{ lk.to.split(' ')[0] }}</td>
                  <td class="py-1 pr-2 text-right" :style="{ color: congColor(lk.gps_avg) }">{{ pct(lk.gps_avg) }}</td>
                  <td class="py-1 pr-2 text-right" :style="{ color: congColor(lk.tt_avg) }">{{ pct(lk.tt_avg) }}</td>
                  <td class="py-1 pr-2 text-right font-bold" :style="{ color: lk.mad > 0.1 ? '#ef4444' : lk.mad > 0.04 ? '#f97316' : '#22c55e' }">
                    {{ pct(lk.mad) }}</td>
                  <td class="py-1 pr-2 text-right" :style="{ color: corrColor(lk.correlation) }">{{ lk.correlation.toFixed(2) }}</td>
                  <td class="py-1 pr-2 text-right text-[#4a7090]">{{ lk.avg_n_trav.toFixed(0) }}</td>
                  <td class="py-1 pr-2 text-right"
                    :style="{ color: lk.vol_ratio > 1.3 ? '#ef4444' : lk.vol_ratio < 0.7 ? '#22c55e' : '#64748b' }">
                    {{ lk.vol_ratio.toFixed(2) }}</td>
                  <td class="py-1 text-right">
                    <span class="text-[7px] font-bold px-1.5 py-0.5 rounded"
                      :style="{ color: REC_COLOR[lk.recommendation], background: REC_BG[lk.recommendation] }">
                      {{ { tt:'TT', blend:'BLD', gps:'GPS' }[lk.recommendation] }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- VOL ratio note -->
          <div class="text-[7px] text-[#1a3050] mt-2">
            VOL = TT std / GPS std — &lt;1 means TT more stable, &gt;1 means TT more volatile · CORR = Pearson r across 15 bins
          </div>
        </section>
      </div>

    </div><!-- /main -->
  </div>
</template>
