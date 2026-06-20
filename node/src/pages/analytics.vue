<script setup lang="ts">
const runtimeConfig = useRuntimeConfig();
const API = runtimeConfig.public.apiBase || "http://localhost:8100";

const loading  = ref(true);
const data     = ref<any>(null);
const sortKey  = ref<"avg_cong" | "max_cong" | "std_cong" | "length_m">("avg_cong");
const sortAsc  = ref(false);
const selected = ref<string | null>(null);

async function fetchData() {
  loading.value = true;
  try {
    data.value = await $fetch(API + "/traffic/link-analytics");
  } catch (e) {
    data.value = null;
  } finally {
    loading.value = false;
  }
}
onMounted(fetchData);

// ── Color helpers ─────────────────────────────────────────────────────────────
function congColor(v: number): string {
  if (v >= 0.75) return "#ef4444";
  if (v >= 0.55) return "#f97316";
  if (v >= 0.33) return "#eab308";
  return "#22c55e";
}
function congBg(v: number): string {
  if (v >= 0.75) return "rgba(239,68,68,0.85)";
  if (v >= 0.55) return "rgba(249,115,22,0.80)";
  if (v >= 0.33) return "rgba(234,179,8,0.75)";
  return "rgba(34,197,94,0.70)";
}
function congLabel(v: number): string {
  if (v >= 0.75) return "SEVERE";
  if (v >= 0.55) return "HEAVY";
  if (v >= 0.33) return "MOD";
  return "FREE";
}

// ── Sorted link table ─────────────────────────────────────────────────────────
const sortedLinks = computed(() => {
  if (!data.value) return [];
  const links = [...data.value.links];
  links.sort((a: any, b: any) => {
    const av = a[sortKey.value] ?? 0;
    const bv = b[sortKey.value] ?? 0;
    return sortAsc.value ? av - bv : bv - av;
  });
  return links;
});

function setSort(key: typeof sortKey.value) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value;
  else { sortKey.value = key; sortAsc.value = false; }
}

// ── Network-wide sparkline (SVG path) ─────────────────────────────────────────
const netSparkPath = computed(() => {
  if (!data.value?.network_ts) return "";
  const ts: number[] = data.value.network_ts;
  const W = 600, H = 60, PAD = 4;
  const minV = Math.min(...ts) - 0.02;
  const maxV = Math.max(...ts) + 0.02;
  const xStep = (W - PAD * 2) / (ts.length - 1);
  const yScale = (v: number) => PAD + (1 - (v - minV) / (maxV - minV)) * (H - PAD * 2);
  const pts = ts.map((v, i) => `${PAD + i * xStep},${yScale(v)}`);
  return `M${pts.join(" L")}`;
});

const netAvg = computed(() => {
  if (!data.value?.network_ts) return 0;
  const ts: number[] = data.value.network_ts;
  return (ts.reduce((a, b) => a + b, 0) / ts.length).toFixed(3);
});

// ── Selected link detail ──────────────────────────────────────────────────────
const selectedLink = computed(() =>
  data.value?.links.find((l: any) => l.id === selected.value) ?? null
);
const selectedSparkPath = computed(() => {
  const lk = selectedLink.value;
  if (!lk) return "";
  const ts: number[] = lk.snapshots;
  const W = 300, H = 50, PAD = 3;
  const minV = Math.min(...ts) - 0.02;
  const maxV = Math.max(...ts) + 0.02;
  const xStep = (W - PAD * 2) / (ts.length - 1);
  const yScale = (v: number) => PAD + (1 - (v - minV) / (maxV - minV)) * (H - PAD * 2);
  const pts = ts.map((v, i) => `${PAD + i * xStep},${yScale(v)}`);
  return `M${pts.join(" L")}`;
});
</script>

<template>
  <div class="min-h-screen bg-[#020818] text-[#c8d8e8] font-mono" style="padding-left:52px">
    <NavSidebar />
    <!-- Header -->
    <header class="border-b border-[#1a2535] px-6 py-3 flex items-center justify-between">
      <div class="flex items-center gap-4">
        <NuxtLink to="/"
          class="text-[10px] text-[#4a7090] hover:text-[#00aaff] border border-[#1a2535] hover:border-[#00aaff] px-2 py-1 rounded transition-colors">
          ← MAIN
        </NuxtLink>
        <div>
          <span class="text-[#00aaff] text-xs font-bold tracking-widest">CHENNAI ITS</span>
          <span class="text-[#4a7090] text-[10px] ml-2">/ CORRIDOR ANALYTICS</span>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-[10px] text-[#4a7090]">DATA: 2026-03-18 16:10–16:40 IST · 15 SNAPSHOTS · 64 LINKS</span>
        <button @click="fetchData"
          class="text-[10px] border border-[#1a2535] hover:border-[#00aaff] text-[#4a7090] hover:text-[#00aaff] px-2 py-1 rounded transition-colors">
          ↺ REFRESH
        </button>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center h-64 text-[#4a7090] text-xs">
      <span class="animate-pulse">LOADING ANALYTICS...</span>
    </div>

    <div v-else-if="!data" class="flex items-center justify-center h-64 text-[#ef4444] text-xs">
      DATA UNAVAILABLE
    </div>

    <div v-else class="p-5 space-y-5">

      <!-- ── Network-wide time series ── -->
      <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-4">
        <div class="flex items-center justify-between mb-3">
          <span class="text-[10px] font-bold text-[#00aaff] tracking-widest">NETWORK-WIDE CONGESTION INDEX</span>
          <span class="text-[10px] text-[#4a7090]">AVG: <span :style="{ color: congColor(+netAvg) }">{{ netAvg }}</span></span>
        </div>
        <div class="relative">
          <svg viewBox="0 0 600 60" class="w-full h-14" preserveAspectRatio="none">
            <!-- Grid lines -->
            <line x1="4" y1="15" x2="596" y2="15" stroke="#1a2535" stroke-width="0.5" />
            <line x1="4" y1="30" x2="596" y2="30" stroke="#1a2535" stroke-width="0.5" />
            <line x1="4" y1="45" x2="596" y2="45" stroke="#1a2535" stroke-width="0.5" />
            <!-- Fill -->
            <path
              :d="netSparkPath + ` L596,56 L4,56 Z`"
              fill="rgba(0,170,255,0.08)"
            />
            <!-- Line -->
            <path :d="netSparkPath" fill="none" stroke="#00aaff" stroke-width="1.5" />
            <!-- Data points -->
            <circle
              v-for="(v, i) in data.network_ts"
              :key="i"
              :cx="4 + i * (592 / (data.network_ts.length - 1))"
              :cy="4 + (1 - (v - Math.min(...data.network_ts) + 0.02) / (Math.max(...data.network_ts) - Math.min(...data.network_ts) + 0.04)) * 52"
              r="2"
              :fill="congColor(v)"
            />
          </svg>
          <!-- Time labels -->
          <div class="flex justify-between mt-1">
            <span v-for="(t, i) in data.time_labels" :key="i"
              class="text-[8px] text-[#2a3545]"
              :style="{ display: i % 3 === 0 || i === data.time_labels.length - 1 ? 'block' : 'none' }">
              {{ t }}
            </span>
          </div>
        </div>
      </section>

      <!-- ── Heatmap ── -->
      <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-4">
        <div class="flex items-center justify-between mb-3">
          <span class="text-[10px] font-bold text-[#00aaff] tracking-widest">CORRIDOR CONGESTION HEATMAP</span>
          <div class="flex items-center gap-3 text-[9px]">
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm inline-block bg-[#22c55e]"></span>FREE</span>
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm inline-block bg-[#eab308]"></span>MOD</span>
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm inline-block bg-[#f97316]"></span>HEAVY</span>
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm inline-block bg-[#ef4444]"></span>SEVERE</span>
          </div>
        </div>

        <!-- Time header row -->
        <div class="flex gap-px mb-px pl-[110px]">
          <div
            v-for="t in data.time_labels" :key="t"
            class="flex-1 text-center text-[7px] text-[#2a3545] truncate"
          >{{ t }}</div>
        </div>

        <!-- Link rows -->
        <div class="space-y-px">
          <div
            v-for="lk in data.links" :key="lk.id"
            class="flex gap-px items-center group cursor-pointer"
            @click="selected = selected === lk.id ? null : lk.id"
          >
            <!-- Link label -->
            <div class="w-[108px] shrink-0 text-right pr-2 text-[8px] truncate"
              :class="selected === lk.id ? 'text-[#00aaff]' : 'text-[#2a4060] group-hover:text-[#4a7090]'">
              {{ lk.from.split(' ')[0] }}–{{ lk.to.split(' ')[0] }}
            </div>
            <!-- Cells -->
            <div
              v-for="(v, si) in lk.snapshots" :key="si"
              class="flex-1 h-4 rounded-[1px] transition-opacity"
              :style="{ backgroundColor: congBg(v), opacity: selected && selected !== lk.id ? '0.4' : '1' }"
              :title="`${lk.id} ${lk.from}→${lk.to} @ ${data.time_labels[si]}: ${v}`"
            />
          </div>
        </div>
      </section>

      <!-- ── Selected link detail ── -->
      <section v-if="selectedLink" class="bg-[#0a0f1a] border border-[#00aaff]/30 rounded p-4">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-[10px] font-bold text-[#00aaff] tracking-widest mb-1">
              {{ selectedLink.id.toUpperCase() }} — {{ selectedLink.from }} → {{ selectedLink.to }}
            </div>
            <div class="flex items-center gap-4 text-[9px] text-[#4a7090]">
              <span>LENGTH: <span class="text-[#c8d8e8]">{{ (selectedLink.length_m / 1000).toFixed(1) }} km</span></span>
              <span>AVG: <span :style="{ color: congColor(selectedLink.avg_cong) }">{{ selectedLink.avg_cong }}</span></span>
              <span>MAX: <span :style="{ color: congColor(selectedLink.max_cong) }">{{ selectedLink.max_cong }}</span></span>
              <span>MIN: <span :style="{ color: congColor(selectedLink.min_cong) }">{{ selectedLink.min_cong }}</span></span>
              <span>STD: <span class="text-[#c8d8e8]">{{ selectedLink.std_cong }}</span></span>
              <span v-if="selectedLink.tt_base != null">TT: <span :style="{ color: congColor(selectedLink.tt_base) }">{{ selectedLink.tt_base }}</span></span>
              <span v-if="selectedLink.n_trav">TRAVERSALS: <span class="text-[#c8d8e8]">{{ selectedLink.n_trav }}</span></span>
            </div>
          </div>
          <button @click="selected = null" class="text-[#4a7090] hover:text-[#ef4444] text-xs">✕</button>
        </div>
        <svg viewBox="0 0 300 50" class="w-full h-12 mt-3" preserveAspectRatio="none">
          <path
            :d="selectedSparkPath.replace('M', 'M') + ` L297,47 L3,47 Z`"
            fill="rgba(0,170,255,0.10)"
          />
          <path :d="selectedSparkPath" fill="none" stroke="#00aaff" stroke-width="1.5" />
          <circle
            v-for="(v, i) in selectedLink.snapshots" :key="i"
            :cx="3 + i * (294 / (selectedLink.snapshots.length - 1))"
            :cy="3 + (1 - (v - Math.min(...selectedLink.snapshots) + 0.02) / (Math.max(...selectedLink.snapshots) - Math.min(...selectedLink.snapshots) + 0.04)) * 44"
            r="2.5"
            :fill="congColor(v)"
          />
        </svg>
        <div class="flex justify-between mt-1">
          <span v-for="(t, i) in data.time_labels" :key="i"
            class="text-[7px] text-[#2a3545]"
            :style="{ display: i % 3 === 0 || i === data.time_labels.length - 1 ? 'block' : 'none' }">
            {{ t }}
          </span>
        </div>
      </section>

      <!-- ── Stats table ── -->
      <section class="bg-[#0a0f1a] border border-[#1a2535] rounded p-4">
        <div class="flex items-center justify-between mb-3">
          <span class="text-[10px] font-bold text-[#00aaff] tracking-widest">LINK STATISTICS</span>
          <span class="text-[9px] text-[#2a3545]">CLICK HEADER TO SORT · CLICK ROW TO INSPECT</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-[9px] border-collapse">
            <thead>
              <tr class="text-[#2a5070] border-b border-[#1a2535]">
                <th class="text-left py-1.5 pr-3 font-normal">ID</th>
                <th class="text-left py-1.5 pr-3 font-normal">FROM → TO</th>
                <th
                  class="text-right py-1.5 pr-3 cursor-pointer hover:text-[#00aaff] select-none font-normal"
                  :class="sortKey === 'avg_cong' ? 'text-[#00aaff]' : ''"
                  @click="setSort('avg_cong')"
                >AVG{{ sortKey === 'avg_cong' ? (sortAsc ? ' ↑' : ' ↓') : '' }}</th>
                <th
                  class="text-right py-1.5 pr-3 cursor-pointer hover:text-[#00aaff] select-none font-normal"
                  :class="sortKey === 'max_cong' ? 'text-[#00aaff]' : ''"
                  @click="setSort('max_cong')"
                >MAX{{ sortKey === 'max_cong' ? (sortAsc ? ' ↑' : ' ↓') : '' }}</th>
                <th class="text-right py-1.5 pr-3 font-normal">MIN</th>
                <th
                  class="text-right py-1.5 pr-3 cursor-pointer hover:text-[#00aaff] select-none font-normal"
                  :class="sortKey === 'std_cong' ? 'text-[#00aaff]' : ''"
                  @click="setSort('std_cong')"
                >STD{{ sortKey === 'std_cong' ? (sortAsc ? ' ↑' : ' ↓') : '' }}</th>
                <th class="text-right py-1.5 pr-3 font-normal">TT BASE</th>
                <th
                  class="text-right py-1.5 cursor-pointer hover:text-[#00aaff] select-none font-normal"
                  :class="sortKey === 'length_m' ? 'text-[#00aaff]' : ''"
                  @click="setSort('length_m')"
                >LEN(km){{ sortKey === 'length_m' ? (sortAsc ? ' ↑' : ' ↓') : '' }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="lk in sortedLinks" :key="lk.id"
                class="border-b border-[#0e1520] cursor-pointer transition-colors"
                :class="selected === lk.id
                  ? 'bg-[#002040]'
                  : 'hover:bg-[#0e1520]'"
                @click="selected = selected === lk.id ? null : lk.id"
              >
                <td class="py-1 pr-3 text-[#4a7090]">{{ lk.id }}</td>
                <td class="py-1 pr-3 text-[#6a8090] truncate max-w-[160px]">{{ lk.from }} → {{ lk.to }}</td>
                <td class="py-1 pr-3 text-right font-bold" :style="{ color: congColor(lk.avg_cong) }">
                  {{ lk.avg_cong }}
                </td>
                <td class="py-1 pr-3 text-right" :style="{ color: congColor(lk.max_cong) }">
                  {{ lk.max_cong }}
                </td>
                <td class="py-1 pr-3 text-right" :style="{ color: congColor(lk.min_cong) }">
                  {{ lk.min_cong }}
                </td>
                <td class="py-1 pr-3 text-right text-[#6a8090]">{{ lk.std_cong }}</td>
                <td class="py-1 pr-3 text-right" :style="lk.tt_base != null ? { color: congColor(lk.tt_base) } : {}">
                  {{ lk.tt_base != null ? lk.tt_base : '—' }}
                </td>
                <td class="py-1 text-right text-[#4a7090]">{{ (lk.length_m / 1000).toFixed(1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

    </div>
  </div>
</template>
