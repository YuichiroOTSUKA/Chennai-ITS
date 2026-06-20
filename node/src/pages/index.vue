<script setup lang="ts">
const view = ref<"map" | "schematic">("map");
const schMethod = ref<"gps" | "tt">("gps");
const stats = ref<any>(null);
const intersections = ref<any[]>([]);
const schematicLinks = ref<any[]>([]);
const lastUpdate = ref("");
const sysTime = ref("");
const runtimeConfig = useRuntimeConfig();
const API = runtimeConfig.public.apiBase || "http://localhost:8100";

// ── Replay state ─────────────────────────────────────────────────────────────
const schSnapsGps = ref<any[]>([]);     // GPS schematic-snapshots
const schSnapsTt  = ref<any[]>([]);     // TT  schematic-snapshots
const roadSnaps   = ref<any[]>([]);     // road-snapshots (segment congestion only)
const replayMode  = ref(false);
const snapIndex   = ref(0);
const isPlaying   = ref(false);
const replayMethod = ref<"gps" | "tt">("gps");
let playTimer: ReturnType<typeof setInterval> | null = null;

// Active snapshot array based on current replayMethod
const schSnaps = computed(() =>
  replayMethod.value === "tt" ? schSnapsTt.value : schSnapsGps.value
);

const currentSnap = computed(() =>
  replayMode.value && schSnaps.value.length ? schSnaps.value[snapIndex.value] : null
);

// intersections to pass down: live OR replay
const activeIntersections = computed(() =>
  currentSnap.value ? currentSnap.value.intersections : intersections.value
);

// schematic links to pass down: live OR replay
const activeSchematicLinks = computed(() =>
  currentSnap.value ? currentSnap.value.links : schematicLinks.value
);

async function loadSnapshots() {
  try {
    const [schGps, schTt, road]: [any, any, any] = await Promise.all([
      $fetch(API + "/traffic/schematic-snapshots?method=gps"),
      $fetch(API + "/traffic/schematic-snapshots?method=tt"),
      $fetch(API + "/traffic/road-snapshots"),
    ]);
    schSnapsGps.value = schGps.snapshots ?? [];
    schSnapsTt.value  = schTt.snapshots  ?? [];
    roadSnaps.value   = road.snapshots   ?? [];
  } catch {}
}

function startReplay() {
  replayMode.value = true;
  snapIndex.value  = 0;
  isPlaying.value  = false;
}
function exitReplay() {
  replayMode.value = false;
  isPlaying.value  = false;
  if (playTimer) { clearInterval(playTimer); playTimer = null; }
}
function prevSnap() { isPlaying.value = false; if (snapIndex.value > 0) snapIndex.value--; }
function nextSnap() { isPlaying.value = false; if (snapIndex.value < schSnaps.value.length - 1) snapIndex.value++; }
function firstSnap() { isPlaying.value = false; snapIndex.value = 0; }
function lastSnap()  { isPlaying.value = false; snapIndex.value = schSnaps.value.length - 1; }

function togglePlay() {
  if (isPlaying.value) {
    isPlaying.value = false;
    if (playTimer) { clearInterval(playTimer); playTimer = null; }
  } else {
    if (snapIndex.value >= schSnaps.value.length - 1) snapIndex.value = 0;
    isPlaying.value = true;
    playTimer = setInterval(() => {
      if (snapIndex.value < schSnaps.value.length - 1) {
        snapIndex.value++;
      } else {
        isPlaying.value = false;
        clearInterval(playTimer!); playTimer = null;
      }
    }, 1500);
  }
}

// Live data functions
async function fetchStats() {
  try {
    const r: any = await $fetch(API + "/traffic/stats");
    stats.value = r.result;
    lastUpdate.value = new Date().toLocaleTimeString("en-IN");
  } catch {}
}
async function fetchIntersections() {
  try {
    const r: any = await $fetch(API + "/traffic/intersections");
    intersections.value = r.result;
  } catch {}
}
async function fetchSchematic() {
  try {
    const r: any = await $fetch(API + `/traffic/schematic?method=${schMethod.value}`);
    schematicLinks.value = r.links ?? [];
  } catch {}
}
function toggleSchMethod() {
  schMethod.value = schMethod.value === "gps" ? "tt" : "gps";
  fetchSchematic();
}

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
  return "Free Flow";
};

const incidents = computed(() => {
  const src = activeIntersections.value;
  if (!src.length) return [];
  const incs: Array<{ type: string; sev: string; location: string }> = [];
  for (const n of src) {
    if (n.congestion >= 0.75)
      incs.push({ type: "交差点飽和", sev: "CRITICAL", location: n.name });
    else if (n.congestion >= 0.55)
      incs.push({ type: "幹線渋滞", sev: "HIGH", location: n.name });
  }
  return incs.sort((a, b) =>
    a.sev === "CRITICAL" && b.sev !== "CRITICAL" ? -1 : 1
  );
});

// Replay progress bar width %
const replayProgress = computed(() =>
  schSnaps.value.length > 1
    ? (snapIndex.value / (schSnaps.value.length - 1)) * 100
    : 0
);

onMounted(() => {
  const tick = () => (sysTime.value = new Date().toLocaleTimeString("en-GB"));
  tick();
  setInterval(tick, 1000);
  fetchStats();
  fetchIntersections();
  fetchSchematic();
  loadSnapshots();
  setInterval(() => {
    if (!replayMode.value) {
      fetchStats();
      fetchIntersections();
      fetchSchematic();
    }
  }, 30000);
});

onUnmounted(() => {
  if (playTimer) clearInterval(playTimer);
});
</script>

<template>
  <div class="tms-root">
    <NavSidebar />
    <div class="scan-bar" />

    <!-- Control Room Header -->
    <header class="tms-header">
      <div class="ctrl-left">
        <div class="title-row">
          <div
            class="status-dot"
            :style="{
              background: replayMode ? '#ffaa22' : lastUpdate ? '#00ff88' : '#334466',
              boxShadow: replayMode ? '0 0 8px #ffaa22' : lastUpdate ? '0 0 8px #00ff88' : 'none',
            }"
          />
          <span class="ctrl-title">CHENNAI ITS</span>
          <span class="sys-time">{{ replayMode ? (currentSnap?.time_ist ?? '') + ' IST' : sysTime }}</span>
        </div>
        <div
          class="ctrl-status"
          :style="{ color: replayMode ? '#ffaa22' : lastUpdate ? '#00cc66' : '#2a4060' }"
        >
          {{ replayMode
              ? `◈ REPLAY  BUS PROBE  2026-03-18`
              : lastUpdate ? `● LIVE  ${lastUpdate}` : '● CONNECTING…' }}
        </div>
        <div class="ctrl-stats-row">
          <span class="cstat red">{{ stats?.severe_segments ?? "—" }} <em>SEV</em></span>
          <span class="cstat orange">{{ stats?.moderate_segments ?? "—" }} <em>MOD</em></span>
          <span class="cstat green">{{ stats?.free_segments ?? "—" }} <em>FREE</em></span>
          <span v-if="stats" class="cstat-idx">CI: {{ stats.congestion_index }}</span>
        </div>
        <div v-if="incidents.length" class="inc-badge">
          <div class="inc-dot" />
          <span>
            {{ incidents.filter((i) => i.sev === "CRITICAL").length }} CRITICAL
            &nbsp;
            {{ incidents.filter((i) => i.sev === "HIGH").length }} HIGH
          </span>
        </div>
      </div>

      <!-- Replay timeline player -->
      <div class="timeline-wrap">
        <div v-if="!replayMode" class="live-indicator">
          <span class="live-text">● LIVE MODE</span>
          <button
            v-if="schSnapsGps.length"
            class="replay-btn"
            @click="startReplay"
          >⏮ REPLAY</button>
          <span v-else class="loading-text">Loading probe data…</span>
        </div>

        <div v-else class="replay-player">
          <button class="r-btn exit-btn" @click="exitReplay" title="Exit replay">✕ LIVE</button>

          <div class="r-controls">
            <button class="r-btn" @click="firstSnap" title="First">⏮</button>
            <button class="r-btn" @click="prevSnap"  title="Prev">◀</button>
            <button class="r-btn play-btn" @click="togglePlay" :title="isPlaying ? 'Pause' : 'Play'">
              {{ isPlaying ? '⏸' : '▶' }}
            </button>
            <button class="r-btn" @click="nextSnap"  title="Next">▶</button>
            <button class="r-btn" @click="lastSnap"  title="Last">⏭</button>
          </div>

          <div class="r-timeline">
            <span class="r-time-label">{{ schSnaps[0]?.time_ist }}</span>
            <div class="r-bar-wrap">
              <div class="r-bar-bg">
                <div class="r-bar-fill" :style="{ width: replayProgress + '%' }" />
              </div>
              <input
                type="range"
                class="r-scrubber"
                :min="0"
                :max="schSnaps.length - 1"
                :value="snapIndex"
                @input="(e) => { isPlaying && togglePlay(); snapIndex = Number((e.target as HTMLInputElement).value); }"
              />
            </div>
            <span class="r-time-label">{{ schSnaps[schSnaps.length-1]?.time_ist }}</span>
          </div>

          <div class="r-current-time">
            <span class="r-ts">{{ currentSnap?.time_ist }} IST</span>
            <span class="r-snap-idx">{{ snapIndex + 1 }}/{{ schSnaps.length }}</span>
          </div>

          <div class="replay-method-toggle">
            <button
              :class="['rm-btn', replayMethod === 'gps' && 'rm-active-gps']"
              @click="replayMethod = 'gps'"
              title="GPS instantaneous speed"
            >GPS</button>
            <button
              :class="['rm-btn', replayMethod === 'tt' && 'rm-active-tt']"
              @click="replayMethod = 'tt'"
              title="Travel-time speed"
            >TT</button>
          </div>
        </div>
      </div>

      <div class="view-toggle">
        <button
          :class="['vtab', view === 'map' && 'active-map']"
          @click="view = 'map'"
        >● MAP VIEW</button>
        <button
          :class="['vtab', view === 'schematic' && 'active-sch']"
          @click="view = 'schematic'"
        >▶ SCHEMATIC</button>
      </div>

      <!-- Speed method toggle (schematic live only) -->
      <div v-if="view === 'schematic' && !replayMode" class="method-toggle">
        <span class="method-label">SPEED METHOD</span>
        <button
          :class="['mtab', schMethod === 'gps' && 'mtab-active-gps']"
          @click="schMethod !== 'gps' && toggleSchMethod()"
          title="GPS瞬間速度: 各セグメントの瞬間速度から算出"
        >GPS</button>
        <button
          :class="['mtab', schMethod === 'tt' && 'mtab-active-tt']"
          @click="schMethod !== 'tt' && toggleSchMethod()"
          title="旅行時間速度: リンク通過時間から空間平均速度を算出"
        >TRAVEL TIME</button>
      </div>
    </header>


    <main class="tms-main">
      <TrafficMap
        v-if="view === 'map'"
        :api="API"
        :intersections="activeIntersections"
        :road-snaps="replayMode ? roadSnaps : null"
        :snap-index="replayMode ? snapIndex : -1"
      />
      <SchematicMap
        v-else
        :intersections="activeIntersections"
        :schematic-links="activeSchematicLinks"
        :congestion-color="congestionColor"
        :congestion-label="congestionLabel"
      />
    </main>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; margin: 0; padding: 0; }

@keyframes scan-sweep {
  0%   { top: -4px; }
  100% { top: 100vh; }
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
@keyframes blink-crit {
  0%, 49%   { opacity: 1; }
  50%, 100% { opacity: 0.35; }
}

.scan-bar {
  position: fixed; left: 0; right: 0; height: 3px; z-index: 999; pointer-events: none;
  background: linear-gradient(transparent, rgba(0, 150, 255, 0.06), transparent);
  animation: scan-sweep 5s linear infinite;
}

.tms-root {
  width: 100vw; height: 100vh;
  background: #020818;
  display: flex; flex-direction: column;
  overflow: hidden;
  font-family: "Segoe UI", system-ui, sans-serif;
  padding-left: 52px;
}

.tms-header {
  display: flex; align-items: center;
  padding: 8px 14px;
  background: rgba(2, 8, 24, 0.97);
  border-bottom: 1px solid rgba(56, 189, 248, 0.1);
  flex-shrink: 0;
  z-index: 10;
  box-shadow: 0 0 28px rgba(0, 60, 180, 0.14), inset 0 0 20px rgba(0, 20, 60, 0.3);
  gap: 16px;
}

.ctrl-left { display: flex; flex-direction: column; gap: 3px; flex-shrink: 0; }

.title-row {
  display: flex; align-items: center; gap: 8px;
  border-bottom: 1px solid #0a1830;
  padding-bottom: 5px; margin-bottom: 2px;
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  animation: pulse-dot 2s infinite;
}
.ctrl-title {
  color: #a8c8e8; font-size: 13px; font-weight: 700;
  letter-spacing: 2px; font-family: monospace;
}
.sys-time {
  margin-left: auto; color: #1e3a5a;
  font-size: 10px; font-family: monospace; letter-spacing: 0.5px;
}
.ctrl-status { font-size: 10px; font-family: monospace; letter-spacing: 0.5px; }
.ctrl-stats-row {
  display: flex; gap: 10px; font-size: 9px; font-family: monospace; color: #1e3a5a;
}
.cstat em { font-style: normal; color: #0d2035; }
.cstat.red    { color: #ff4422; }
.cstat.orange { color: #ff8833; }
.cstat.green  { color: #00cc55; }
.cstat-idx    { color: #1e4060; }
.inc-badge {
  display: flex; align-items: center; gap: 5px;
  border-top: 1px solid #0a1830; padding-top: 4px; margin-top: 2px;
}
.inc-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #ff2200; box-shadow: 0 0 6px #ff2200;
  animation: blink-crit 1.5s infinite;
}
.inc-badge span { color: #ff6644; font-size: 9px; font-family: monospace; letter-spacing: 0.5px; }

/* ── Timeline / Replay player ── */
.timeline-wrap { flex: 1; min-width: 0; display: flex; align-items: center; }

.live-indicator {
  display: flex; align-items: center; gap: 10px;
}
.live-text {
  color: #0d3020; font-size: 9px; font-family: monospace; letter-spacing: 0.8px;
}
.replay-btn {
  font-size: 9px; padding: 4px 10px; border-radius: 3px; cursor: pointer;
  font-family: monospace; letter-spacing: 0.5px; font-weight: 700;
  background: rgba(40, 20, 0, 0.85); border: 1px solid #553300;
  color: #ffaa22; transition: all 0.15s;
}
.replay-btn:hover { background: rgba(80, 40, 0, 0.9); border-color: #aa6600; }
.loading-text { color: #1a3050; font-size: 8px; font-family: monospace; }

.replay-player {
  display: flex; align-items: center; gap: 10px; width: 100%;
}
.r-btn {
  font-size: 10px; padding: 3px 7px; border-radius: 3px; cursor: pointer;
  font-family: monospace; font-weight: 700;
  background: rgba(4, 12, 30, 0.9); border: 1px solid #0a2040;
  color: #4488cc; transition: all 0.12s; white-space: nowrap; flex-shrink: 0;
}
.r-btn:hover { background: rgba(0, 40, 120, 0.4); color: #88bbff; border-color: #2255aa; }
.play-btn { min-width: 34px; color: #ffaa22; border-color: #553300; }
.play-btn:hover { color: #ffcc55; border-color: #aa6600; background: rgba(80,40,0,0.4); }
.exit-btn { color: #1e5070; border-color: #0a2030; font-size: 8px; }
.exit-btn:hover { color: #2288aa; }

.r-controls { display: flex; gap: 3px; flex-shrink: 0; }

.r-timeline {
  flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px;
}
.r-time-label {
  font-size: 8px; font-family: monospace; color: #1e3a5a;
  white-space: nowrap; flex-shrink: 0;
}
.r-bar-wrap { flex: 1; position: relative; height: 16px; display: flex; align-items: center; }
.r-bar-bg {
  position: absolute; left: 0; right: 0; height: 3px; border-radius: 2px;
  background: #061020;
}
.r-bar-fill {
  height: 100%; border-radius: 2px;
  background: linear-gradient(90deg, #1a4080, #4488cc);
  transition: width 0.3s;
}
.r-scrubber {
  position: absolute; left: 0; right: 0; width: 100%; height: 16px;
  opacity: 0; cursor: pointer; margin: 0;
}

.r-current-time {
  display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0;
}
.r-ts {
  font-size: 12px; font-family: monospace; font-weight: 700; color: #ffaa22;
  letter-spacing: 0.5px;
}
.r-snap-idx { font-size: 8px; font-family: monospace; color: #1e3a5a; }

/* ── View toggle ── */
.view-toggle { display: flex; gap: 4px; flex-shrink: 0; }
.vtab {
  font-size: 10px; padding: 6px 16px; border-radius: 3px; cursor: pointer;
  font-family: monospace; letter-spacing: 0.5px; font-weight: 700;
  background: rgba(6, 12, 28, 0.8); border: 1px solid #0a1830;
  color: #1e3a5a; transition: all 0.15s;
}
.vtab.active-map { background: rgba(0, 30, 100, 0.9); border-color: #2255cc; color: #6699ee; }
.vtab.active-sch { background: rgba(70, 30, 0, 0.9);  border-color: #cc7700; color: #ffaa22; }
.vtab:hover:not(.active-map):not(.active-sch) { color: #2a5070; }

.tms-main { flex: 1; overflow: hidden; position: relative; }

/* ── Replay method toggle (GPS/TT in replay player) ── */
.replay-method-toggle {
  display: flex; gap: 2px; flex-shrink: 0; border-left: 1px solid #0a1830; padding-left: 8px;
}
.rm-btn {
  font-size: 9px; padding: 3px 8px; border-radius: 3px; cursor: pointer;
  font-family: monospace; font-weight: 700;
  background: rgba(4, 12, 30, 0.9); border: 1px solid #0a2040;
  color: #1e3a5a; transition: all 0.12s; white-space: nowrap;
}
.rm-active-gps { background: rgba(0, 60, 20, 0.6); border-color: #009944; color: #00cc66; }
.rm-active-tt  { background: rgba(60, 0, 90, 0.6);  border-color: #9933cc; color: #cc66ff; }
.rm-btn:hover:not(.rm-active-gps):not(.rm-active-tt) { color: #2a5070; }

/* ── Speed method toggle ── */
.method-toggle {
  display: flex; align-items: center; gap: 4px; flex-shrink: 0;
  border-left: 1px solid #0a1830; padding-left: 12px;
}
.method-label {
  font-size: 7px; font-family: monospace; letter-spacing: 0.15em;
  color: #1a3050; margin-right: 2px; white-space: nowrap;
}
.mtab {
  font-size: 9px; padding: 5px 10px; border-radius: 3px; cursor: pointer;
  font-family: monospace; font-weight: 700; letter-spacing: 0.04em;
  background: rgba(6, 12, 28, 0.8); border: 1px solid #0a1830;
  color: #1e3a5a; transition: all 0.15s; white-space: nowrap;
}
.mtab:hover:not(.mtab-active-gps):not(.mtab-active-tt) { color: #2a5070; border-color: #0f2040; }
.mtab-active-gps {
  background: rgba(0, 80, 20, 0.35); border-color: #00aa44;
  color: #00ff88; box-shadow: 0 0 6px rgba(0,200,80,0.2);
}
.mtab-active-tt {
  background: rgba(60, 0, 100, 0.35); border-color: #8833cc;
  color: #cc88ff; box-shadow: 0 0 6px rgba(150,50,255,0.2);
}
</style>
