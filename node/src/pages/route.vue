<script setup lang="ts">
const runtimeConfig = useRuntimeConfig()
const API = runtimeConfig.public.apiBase || "http://localhost:8100"

// ── State ──────────────────────────────────────────────────────────────────────
const schematicLinks = ref<any[]>([])
const loading   = ref(true)
const computing = ref(false)

const fromNode = ref("Avadi")
const toNode   = ref("Chennai Central")

interface RouteResult {
  label: string
  color: string
  path:  string[]
  links: string[]
  totalDist: number
  avgCong:   number
  estTime:   number   // minutes
}
const routes = ref<RouteResult[]>([])
const selectedRoute = ref(0)
const error = ref("")

// ── Load schematic data ────────────────────────────────────────────────────────
async function loadSchematic() {
  loading.value = true
  try {
    const r: any = await $fetch(API + "/traffic/schematic?method=gps")
    schematicLinks.value = r.links ?? []
  } catch {
    error.value = "Failed to load schematic data"
  } finally {
    loading.value = false
  }
}
onMounted(loadSchematic)

// ── Graph construction ────────────────────────────────────────────────────────
interface Edge {
  to:   string
  lid:  string
  dist: number   // metres
  cong: number   // 0–1
  time: number   // minutes
}

function buildGraph(links: any[]): Record<string, Edge[]> {
  const adj: Record<string, Edge[]> = {}
  const FREE_FLOW_KMH = 30
  const FREE_FLOW_MPS = FREE_FLOW_KMH / 3.6

  for (const lk of links) {
    const fwd: number[] = lk.forward  ?? []
    const bwd: number[] = lk.backward ?? []
    const avgFwd = fwd.length ? fwd.reduce((a: number, b: number) => a + b, 0) / fwd.length : 0.35
    const avgBwd = bwd.length ? bwd.reduce((a: number, b: number) => a + b, 0) / bwd.length : 0.35
    const len: number = lk.length_m ?? 1000

    const timeMin = (avgCong: number) =>
      (len / (FREE_FLOW_MPS * Math.max(0.05, 1 - avgCong * 0.85))) / 60

    if (!adj[lk.from]) adj[lk.from] = []
    adj[lk.from].push({ to: lk.to,   lid: lk.id,        dist: len, cong: avgFwd, time: timeMin(avgFwd) })

    if (bwd.length > 0) {
      if (!adj[lk.to]) adj[lk.to] = []
      adj[lk.to].push({ to: lk.from, lid: lk.id + "_r", dist: len, cong: avgBwd, time: timeMin(avgBwd) })
    }
  }
  return adj
}

// ── Dijkstra ──────────────────────────────────────────────────────────────────
function dijkstra(
  adj: Record<string, Edge[]>,
  start: string,
  goal:  string,
  weightFn: (e: Edge) => number
): { path: string[]; lids: string[]; edges: Edge[] } | null {
  const dist: Record<string, number> = {}
  const prev: Record<string, string | null> = {}
  const prevEdge: Record<string, Edge | null> = {}

  for (const n of Object.keys(adj)) { dist[n] = Infinity; prev[n] = null; prevEdge[n] = null }
  dist[start] = 0

  const queue: [number, string][] = [[0, start]]

  while (queue.length > 0) {
    queue.sort((a, b) => a[0] - b[0])
    const [cost, node] = queue.shift()!
    if (cost > dist[node]) continue
    if (node === goal) break

    for (const edge of (adj[node] ?? [])) {
      const nc = cost + weightFn(edge)
      if (nc < dist[edge.to]) {
        dist[edge.to] = nc
        prev[edge.to] = node
        prevEdge[edge.to] = edge
        queue.push([nc, edge.to])
      }
    }
  }

  if (dist[goal] === Infinity) return null

  const path: string[] = []
  const lids: string[] = []
  const edges: Edge[]  = []
  let cur = goal
  while (cur !== start && prev[cur] !== null) {
    path.unshift(cur)
    const e = prevEdge[cur]!
    lids.unshift(e.lid)
    edges.unshift(e)
    cur = prev[cur]!
  }
  path.unshift(start)
  return { path, lids, edges }
}

// ── Find Routes ───────────────────────────────────────────────────────────────
function findRoutes() {
  if (fromNode.value === toNode.value) { error.value = "出発地と目的地が同じです"; return }
  error.value = ""
  computing.value = true
  routes.value = []

  const adj = buildGraph(schematicLinks.value)

  const defs = [
    { label: "最短距離",    color: "#38bdf8", w: (e: Edge) => e.dist },
    { label: "最小混雑",    color: "#22c55e", w: (e: Edge) => e.cong * 50000 + e.dist * 0.1 },
    { label: "最速ルート",  color: "#f97316", w: (e: Edge) => e.time },
  ]

  const results: RouteResult[] = []
  for (const def of defs) {
    const r = dijkstra(adj, fromNode.value, toNode.value, def.w)
    if (!r) continue
    const totalDist = r.edges.reduce((s, e) => s + e.dist, 0)
    const avgCong   = r.edges.length ? r.edges.reduce((s, e) => s + e.cong, 0) / r.edges.length : 0
    const estTime   = r.edges.reduce((s, e) => s + e.time, 0)
    results.push({ label: def.label, color: def.color, path: r.path, links: r.lids, totalDist, avgCong, estTime })
  }

  routes.value = results
  computing.value = false
}

// ── Per-link metadata lookup ──────────────────────────────────────────────────
const linkMeta = computed(() => {
  const m: Record<string, any> = {}
  for (const lk of schematicLinks.value) m[lk.id] = lk
  return m
})

function getLinkCong(lid: string): number {
  const base = lid.replace("_r", "")
  const lk = linkMeta.value[base]
  if (!lk) return 0.35
  const arr: number[] = lid.endsWith("_r") ? (lk.backward ?? lk.forward) : lk.forward
  return arr.length ? arr.reduce((a: number, b: number) => a + b, 0) / arr.length : 0.35
}
function getLinkDist(lid: string): number {
  return linkMeta.value[lid.replace("_r", "")]?.length_m ?? 0
}

// ── Color helpers ─────────────────────────────────────────────────────────────
function congColor(v: number): string {
  if (v >= 0.75) return "#ef4444"
  if (v >= 0.55) return "#f97316"
  if (v >= 0.33) return "#eab308"
  return "#22c55e"
}
function pct(v: number): string { return (v * 100).toFixed(0) + "%" }
function km(m: number):  string { return (m / 1000).toFixed(1) + " km" }
function min(t: number): string { return t.toFixed(0) + " min" }
</script>

<template>
  <div class="rt-root">
    <div class="grid-overlay" />
    <NavSidebar />

    <main class="rt-main">
      <!-- Header -->
      <header class="rt-header">
        <div class="rt-title-row">
          <span class="rt-icon">⇆</span>
          <div>
            <h1 class="rt-title">ROUTE COMPARISON</h1>
            <p class="rt-sub">Chennai ITS · Dijkstra multi-criteria routing</p>
          </div>
        </div>
      </header>

      <!-- Selector -->
      <section class="selector-card">
        <div class="selector-row">
          <div class="sel-group">
            <label class="sel-label">FROM</label>
            <select v-model="fromNode" class="sel-input">
              <option v-for="n in 42" :key="n">{{ ['Adyar','Ambattur','Anna Nagar','Avadi','Besant Nagar','Chennai Central','Chromepet','Egmore','Ennore','Guduvanchery','Guindy','Kathipara','Kelambakkam','Koyambedu','Madhavaram','Madhya Kailash','Maduravoyal','Medavakkam','Mogappair','Mylapore','Nungambakkam','Pallavaram','Pallikaranai','Perambur','Perungudi','Poonamallee','Porur','Redhills','Royapuram','SRM Nagar','Saidapet','Sholinganallur','T. Nagar','Tambaram','Taramani','Teynampet','Thiruvanmiyur','Thoraipakkam','Tidel Park','Vadapalani','Vandalur','Velachery'][n-1] }}</option>
            </select>
          </div>
          <div class="sel-arrow">→</div>
          <div class="sel-group">
            <label class="sel-label">TO</label>
            <select v-model="toNode" class="sel-input">
              <option v-for="n in 42" :key="n">{{ ['Adyar','Ambattur','Anna Nagar','Avadi','Besant Nagar','Chennai Central','Chromepet','Egmore','Ennore','Guduvanchery','Guindy','Kathipara','Kelambakkam','Koyambedu','Madhavaram','Madhya Kailash','Maduravoyal','Medavakkam','Mogappair','Mylapore','Nungambakkam','Pallavaram','Pallikaranai','Perambur','Perungudi','Poonamallee','Porur','Redhills','Royapuram','SRM Nagar','Saidapet','Sholinganallur','T. Nagar','Tambaram','Taramani','Teynampet','Thiruvanmiyur','Thoraipakkam','Tidel Park','Vadapalani','Vandalur','Velachery'][n-1] }}</option>
            </select>
          </div>
          <button class="find-btn" :disabled="loading || computing" @click="findRoutes">
            <span v-if="computing">Computing…</span>
            <span v-else>⇆ Find Routes</span>
          </button>
        </div>
        <p v-if="error" class="sel-error">{{ error }}</p>
      </section>

      <!-- Loading -->
      <div v-if="loading" class="rt-loading">Loading road network data…</div>

      <!-- No results yet -->
      <div v-else-if="routes.length === 0 && !computing" class="rt-empty">
        <p>出発地と目的地を選択して「Find Routes」を押してください</p>
        <p class="rt-empty-sub">42 intersections · 64 links · GPS congestion weights</p>
      </div>

      <!-- Results -->
      <div v-else-if="routes.length > 0" class="results-area">

        <!-- Summary cards -->
        <div class="summary-grid">
          <div
            v-for="(rt, i) in routes"
            :key="i"
            :class="['summary-card', selectedRoute === i && 'selected']"
            :style="selectedRoute === i ? { borderColor: rt.color, boxShadow: `0 0 18px ${rt.color}22` } : {}"
            @click="selectedRoute = i"
          >
            <div class="card-badge" :style="{ background: rt.color + '22', color: rt.color, border: `1px solid ${rt.color}44` }">
              {{ rt.label }}
            </div>
            <div class="card-stats">
              <div class="cstat">
                <span class="cval">{{ km(rt.totalDist) }}</span>
                <span class="clbl">距離</span>
              </div>
              <div class="cstat">
                <span class="cval" :style="{ color: congColor(rt.avgCong) }">{{ pct(rt.avgCong) }}</span>
                <span class="clbl">平均混雑</span>
              </div>
              <div class="cstat">
                <span class="cval">{{ min(rt.estTime) }}</span>
                <span class="clbl">推定時間</span>
              </div>
              <div class="cstat">
                <span class="cval">{{ rt.path.length - 1 }}</span>
                <span class="clbl">リンク数</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Route path visualization -->
        <section v-if="routes[selectedRoute]" class="path-section">
          <div class="path-header">
            <span class="path-label" :style="{ color: routes[selectedRoute].color }">
              {{ routes[selectedRoute].label }} — 経路詳細
            </span>
          </div>
          <div class="path-chain">
            <template v-for="(node, ni) in routes[selectedRoute].path" :key="ni">
              <div class="chain-node" :class="{ 'chain-start': ni === 0, 'chain-end': ni === routes[selectedRoute].path.length - 1 }">
                {{ node }}
              </div>
              <div
                v-if="ni < routes[selectedRoute].links.length"
                class="chain-link"
                :style="{ background: congColor(getLinkCong(routes[selectedRoute].links[ni])) + '33',
                           borderColor: congColor(getLinkCong(routes[selectedRoute].links[ni])) + '88' }"
                :title="`${routes[selectedRoute].links[ni].replace('_r','')} · ${pct(getLinkCong(routes[selectedRoute].links[ni]))} · ${km(getLinkDist(routes[selectedRoute].links[ni]))}`"
              >
                <span class="cl-id">{{ routes[selectedRoute].links[ni].replace('_r','') }}</span>
                <span class="cl-cong" :style="{ color: congColor(getLinkCong(routes[selectedRoute].links[ni])) }">
                  {{ pct(getLinkCong(routes[selectedRoute].links[ni])) }}
                </span>
              </div>
            </template>
          </div>
        </section>

        <!-- Comparison table -->
        <section class="compare-table-section">
          <div class="ct-header">3ルート比較</div>
          <table class="ct-table">
            <thead>
              <tr>
                <th>指標</th>
                <th v-for="rt in routes" :key="rt.label" :style="{ color: rt.color }">{{ rt.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="ct-metric">総距離</td>
                <td v-for="rt in routes" :key="rt.label">{{ km(rt.totalDist) }}</td>
              </tr>
              <tr>
                <td class="ct-metric">平均混雑率</td>
                <td v-for="rt in routes" :key="rt.label">
                  <span :style="{ color: congColor(rt.avgCong) }">{{ pct(rt.avgCong) }}</span>
                </td>
              </tr>
              <tr>
                <td class="ct-metric">推定所要時間</td>
                <td v-for="rt in routes" :key="rt.label">{{ min(rt.estTime) }}</td>
              </tr>
              <tr>
                <td class="ct-metric">経由リンク数</td>
                <td v-for="rt in routes" :key="rt.label">{{ rt.path.length - 1 }}</td>
              </tr>
              <tr>
                <td class="ct-metric">経路</td>
                <td v-for="rt in routes" :key="rt.label" class="ct-path-cell">
                  {{ rt.path.join(' → ') }}
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- Link detail table for selected route -->
        <section v-if="routes[selectedRoute]" class="link-detail-section">
          <div class="ct-header">リンク別詳細 — {{ routes[selectedRoute].label }}</div>
          <table class="ct-table">
            <thead>
              <tr>
                <th>#</th><th>リンクID</th><th>区間</th><th>距離</th><th>混雑率</th><th>推定時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(lid, li) in routes[selectedRoute].links" :key="li">
                <td class="ct-num">{{ li + 1 }}</td>
                <td>{{ lid.replace('_r','') }}</td>
                <td class="ct-seg">{{ routes[selectedRoute].path[li] }} → {{ routes[selectedRoute].path[li+1] }}</td>
                <td>{{ km(getLinkDist(lid)) }}</td>
                <td><span :style="{ color: congColor(getLinkCong(lid)) }">{{ pct(getLinkCong(lid)) }}</span></td>
                <td>
                  {{ (() => {
                    const lk = linkMeta[lid.replace('_r','')]
                    if (!lk) return '—'
                    const arr: number[] = lid.endsWith('_r') ? (lk.backward ?? lk.forward) : lk.forward
                    const c = arr.length ? arr.reduce((a: number, b: number) => a + b, 0) / arr.length : 0.35
                    return ((lk.length_m ?? 0) / ((30/3.6) * Math.max(0.05, 1 - c*0.85)) / 60).toFixed(1) + ' min'
                  })() }}
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; margin: 0; padding: 0; }

.rt-root {
  min-height: 100vh;
  background: #020818;
  color: #cbd5e1;
  font-family: "Segoe UI", system-ui, sans-serif;
  padding-left: 52px;
}
.grid-overlay {
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    linear-gradient(rgba(56,189,248,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,189,248,0.025) 1px, transparent 1px);
  background-size: 60px 60px;
}
.rt-main {
  position: relative; z-index: 1;
  padding: 20px 24px 40px;
  max-width: 1200px;
}

/* ── Header ── */
.rt-header { margin-bottom: 20px; }
.rt-title-row { display: flex; align-items: center; gap: 14px; }
.rt-icon {
  font-size: 28px;
  background: linear-gradient(135deg, #38bdf8, #6366f1);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.rt-title {
  font-size: 20px; font-weight: 700; letter-spacing: 0.12em;
  background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #6366f1 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.rt-sub { font-size: 10px; color: #334466; letter-spacing: 0.1em; margin-top: 2px; }

/* ── Selector ── */
.selector-card {
  background: rgba(15,23,42,0.8);
  border: 1px solid rgba(56,189,248,0.12);
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 20px;
}
.selector-row { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.sel-group { display: flex; flex-direction: column; gap: 5px; }
.sel-label { font-size: 9px; font-weight: 700; letter-spacing: 0.15em; color: #38bdf8; }
.sel-input {
  background: #060e20; border: 1px solid #1a2a40; border-radius: 7px;
  color: #cbd5e1; font-size: 13px; padding: 7px 10px; min-width: 180px; cursor: pointer;
  outline: none;
}
.sel-input:focus { border-color: rgba(56,189,248,0.4); }
.sel-arrow { font-size: 20px; color: #38bdf8; padding-bottom: 6px; }
.find-btn {
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  border: none; border-radius: 8px; color: #fff;
  font-size: 12px; font-weight: 700; letter-spacing: 0.08em;
  padding: 9px 20px; cursor: pointer; margin-left: 8px;
  transition: opacity 0.15s;
}
.find-btn:hover:not(:disabled) { opacity: 0.85; }
.find-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.sel-error { color: #ef4444; font-size: 12px; margin-top: 8px; }

/* ── States ── */
.rt-loading, .rt-empty {
  text-align: center; padding: 60px 20px;
  color: #334466; font-size: 14px; letter-spacing: 0.08em;
}
.rt-empty-sub { font-size: 11px; margin-top: 8px; color: #1a2a40; }

/* ── Results ── */
.results-area { display: flex; flex-direction: column; gap: 16px; }

.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.summary-card {
  background: rgba(15,23,42,0.8);
  border: 1px solid rgba(56,189,248,0.1);
  border-radius: 12px; padding: 16px;
  cursor: pointer; transition: all 0.18s;
}
.summary-card:hover { background: rgba(20,30,55,0.9); }
.summary-card.selected { background: rgba(15,23,42,0.95); }
.card-badge {
  display: inline-block; border-radius: 6px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.12em;
  padding: 3px 10px; margin-bottom: 12px;
}
.card-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.cstat { display: flex; flex-direction: column; gap: 2px; }
.cval { font-size: 18px; font-weight: 700; color: #e2e8f0; }
.clbl { font-size: 9px; color: #334466; letter-spacing: 0.1em; }

/* ── Path chain ── */
.path-section {
  background: rgba(15,23,42,0.8);
  border: 1px solid rgba(56,189,248,0.1);
  border-radius: 12px; padding: 16px;
}
.path-header { margin-bottom: 12px; }
.path-label { font-size: 10px; font-weight: 700; letter-spacing: 0.12em; }
.path-chain {
  display: flex; align-items: center; flex-wrap: wrap; gap: 0;
  overflow-x: auto; padding-bottom: 4px;
}
.chain-node {
  background: rgba(30,40,60,0.9); border: 1px solid #1a2a40;
  border-radius: 6px; padding: 5px 10px;
  font-size: 10px; font-weight: 600; color: #94a3b8;
  white-space: nowrap; flex-shrink: 0;
}
.chain-node.chain-start { color: #38bdf8; border-color: rgba(56,189,248,0.4); }
.chain-node.chain-end   { color: #6366f1; border-color: rgba(99,102,241,0.4); }
.chain-link {
  display: flex; flex-direction: column; align-items: center;
  border: 1px solid; border-radius: 4px;
  padding: 3px 8px; margin: 0 2px;
  font-size: 8px; flex-shrink: 0; cursor: default;
  min-width: 44px;
}
.cl-id  { color: #334466; letter-spacing: 0.05em; }
.cl-cong { font-weight: 700; }

/* ── Tables ── */
.compare-table-section, .link-detail-section {
  background: rgba(15,23,42,0.8);
  border: 1px solid rgba(56,189,248,0.1);
  border-radius: 12px; overflow: hidden;
}
.ct-header {
  padding: 10px 16px;
  font-size: 9px; font-weight: 700; letter-spacing: 0.15em;
  color: #334466; border-bottom: 1px solid #0a1428;
}
.ct-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ct-table th {
  padding: 8px 14px; text-align: left;
  font-size: 9px; font-weight: 700; letter-spacing: 0.1em;
  color: #334466; border-bottom: 1px solid #0a1428;
}
.ct-table td {
  padding: 8px 14px; border-bottom: 1px solid #0a1428;
  color: #94a3b8;
}
.ct-table tr:last-child td { border-bottom: none; }
.ct-metric { color: #64748b; font-size: 10px; letter-spacing: 0.08em; }
.ct-num { color: #334466; font-size: 10px; }
.ct-seg { color: #64748b; font-size: 10px; }
.ct-path-cell { font-size: 10px; color: #475569; }
</style>
