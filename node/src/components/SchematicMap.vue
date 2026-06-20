<script setup lang="ts">
const props = defineProps<{
  intersections: any[];
  schematicLinks: any[];
  congestionColor: (v: number) => string;
  congestionLabel: (v: number) => string;
  compact?: boolean;   // hide right panel + zoom controls
}>();

const selected   = ref<any>(null);
const svgEl      = ref<SVGSVGElement | null>(null);
const vp         = ref({ zoom: 1, x: 0, y: 0 });
const isDragging = ref(false);
const dragStart  = ref({ lx: 0, ly: 0 });

const VB_W  = 900;
const VB_H  = 600;
const LINE_W = 2.0;  // same width for both lanes

// ── Geometry helpers ──────────────────────────────────────────────────────
interface Pt { x: number; y: number; }

function perpOff(ax: number, ay: number, bx: number, by: number, d: number): Pt {
  const dx = bx - ax, dy = by - ay;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  return { x: -dy / len * d, y: dx / len * d };
}

function segIntersects(p1: Pt, p2: Pt, p3: Pt, p4: Pt): boolean {
  const d1x = p2.x - p1.x, d1y = p2.y - p1.y;
  const d2x = p4.x - p3.x, d2y = p4.y - p3.y;
  const cr  = d1x * d2y - d1y * d2x;
  if (Math.abs(cr) < 1e-8) return false;
  const dx = p3.x - p1.x, dy = p3.y - p1.y;
  const t  = (dx * d2y - dy * d2x) / cr;
  const u  = (dx * d1y - dy * d1x) / cr;
  const ep = 0.04;                              // ignore crossings within 4% of endpoints
  return t > ep && t < 1 - ep && u > ep && u < 1 - ep;
}

interface Seg { p1: Pt; p2: Pt; ci: number; an: string; bn: string; }

function buildSegs(np: Record<string, Pt>, corrs: [string, string][], hs: number): Seg[] {
  const out: Seg[] = [];
  corrs.forEach(([a, b], ci) => {
    const la = np[a], lb = np[b];
    if (!la || !lb) return;
    const { x: px, y: py } = perpOff(la.x, la.y, lb.x, lb.y, hs);
    // forward lane
    out.push({ p1: { x: la.x + px, y: la.y + py }, p2: { x: lb.x + px, y: lb.y + py }, ci, an: a, bn: b });
    // backward lane
    out.push({ p1: { x: lb.x - px, y: lb.y - py }, p2: { x: la.x - px, y: la.y - py }, ci, an: b, bn: a });
  });
  return out;
}

function countX(segs: Seg[]): number {
  let n = 0;
  for (let i = 0; i < segs.length; i++)
    for (let j = i + 1; j < segs.length; j++) {
      const s = segs[i], t = segs[j];
      if (s.ci === t.ci) continue;
      if (s.an === t.an || s.an === t.bn || s.bn === t.an || s.bn === t.bn) continue;
      if (segIntersects(s.p1, s.p2, t.p1, t.p2)) n++;
    }
  return n;
}

// ── Base node layout (angle-optimised: all shared-node angles ≥20°, 0 crossings) ─
// 42 nodes — optimised 2026-06-15 (10 new nodes added for full city coverage)
const BASE: Record<string, { x: number; y: number; short: string }> = {
  "Royapuram":       { x: 820, y:  60, short: "ROYAPUR" },
  "Perambur":        { x: 659, y:  43, short: "PERAMB" },
  "Avadi":           { x: 140, y:  90, short: "AVADI" },
  "Ambattur":        { x: 378, y:  61, short: "AMBAT" },
  "Egmore":          { x: 720, y: 125, short: "EGMORE" },
  "Anna Nagar":      { x: 491, y:  97, short: "ANNA NGR" },
  "Chennai Central": { x: 757, y: 151, short: "CENTRAL" },
  "Koyambedu":       { x: 477, y: 149, short: "KOYAM" },
  "Nungambakkam":    { x: 656, y: 189, short: "NUNGA" },
  "Vadapalani":      { x: 530, y: 185, short: "VADAP" },
  "Mylapore":        { x: 750, y: 195, short: "MYLAPORE" },
  "T. Nagar":        { x: 610, y: 215, short: "T.NAGAR" },
  "Poonamallee":     { x: 140, y: 220, short: "POONAM" },
  "Porur":           { x: 355, y: 240, short: "PORUR" },
  "Saidapet":        { x: 572, y: 248, short: "SAIDAPET" },
  "Kathipara":       { x: 490, y: 275, short: "KATH" },
  "Guindy":          { x: 562, y: 292, short: "GUINDY" },
  "Madhya Kailash":  { x: 670, y: 275, short: "M.KAILASH" },
  "Adyar":           { x: 710, y: 295, short: "ADYAR" },
  "Besant Nagar":    { x: 762, y: 312, short: "BESANT" },
  "Tidel Park":      { x: 668, y: 325, short: "TIDEL" },
  "Velachery":       { x: 497, y: 355, short: "VELA" },
  "Taramani":        { x: 640, y: 362, short: "TARAM" },
  "Thiruvanmiyur":   { x: 730, y: 359, short: "THIRUV" },
  "Perungudi":       { x: 657, y: 400, short: "PERUN" },
  "Pallavaram":      { x: 322, y: 369, short: "PALLAV" },
  "Chromepet":       { x: 308, y: 420, short: "CHROME" },
  "Pallikaranai":    { x: 535, y: 432, short: "PALLIKA" },
  "Tambaram":        { x: 233, y: 441, short: "TAMB" },
  "Thoraipakkam":    { x: 633, y: 447, short: "THORAI" },
  "Sholinganallur":  { x: 596, y: 507, short: "SHOLI" },
  "SRM Nagar":       { x: 600, y: 545, short: "SRM" },
  // ── New nodes (2026-06-15) ──
  "Ennore":          { x: 852, y:  22, short: "ENNORE" },
  "Madhavaram":      { x: 662, y:  16, short: "MADHAV" },
  "Redhills":        { x: 480, y:  16, short: "REDHILLS" },
  "Mogappair":       { x: 418, y: 100, short: "MOGAP" },
  "Maduravoyal":     { x: 292, y: 168, short: "MADUR" },
  "Teynampet":       { x: 628, y: 230, short: "TEYNAM" },
  "Medavakkam":      { x: 508, y: 468, short: "MEDAV" },
  "Vandalur":        { x: 176, y: 508, short: "VAND" },
  "Kelambakkam":     { x: 618, y: 578, short: "KELAM" },
  "Guduvanchery":    { x: 200, y: 570, short: "GUDUV" },
};

const corridors: [string, string][] = [
  // ── Original corridors ──
  ["Avadi","Ambattur"],["Ambattur","Anna Nagar"],["Anna Nagar","Koyambedu"],
  ["Koyambedu","Chennai Central"],["Poonamallee","Porur"],["Porur","Koyambedu"],
  ["Porur","Kathipara"],["Kathipara","Koyambedu"],["Kathipara","Guindy"],
  ["Guindy","Velachery"],["Guindy","Madhya Kailash"],["Madhya Kailash","Adyar"],
  ["Chennai Central","Madhya Kailash"],["Madhya Kailash","Tidel Park"],
  ["Tidel Park","Taramani"],["Taramani","Velachery"],["Taramani","Thoraipakkam"],
  ["Adyar","Perungudi"],["Sholinganallur","SRM Nagar"],
  ["Velachery","Chromepet"],["Chromepet","Pallavaram"],["Pallavaram","Tambaram"],
  ["Tambaram","Chromepet"],
  ["Royapuram","Chennai Central"],["Royapuram","Perambur"],
  ["Perambur","Egmore"],["Perambur","Ambattur"],["Chennai Central","Egmore"],
  ["Chennai Central","Nungambakkam"],["Nungambakkam","T. Nagar"],
  ["Koyambedu","Vadapalani"],["Vadapalani","T. Nagar"],
  ["T. Nagar","Saidapet"],["Saidapet","Guindy"],["Saidapet","Kathipara"],
  ["Chennai Central","Mylapore"],["Mylapore","Adyar"],
  ["Adyar","Besant Nagar"],["Besant Nagar","Thiruvanmiyur"],
  ["Thiruvanmiyur","Thoraipakkam"],["Perungudi","Thoraipakkam"],
  ["Thoraipakkam","Sholinganallur"],["Pallikaranai","Thoraipakkam"],
  ["Velachery","Pallikaranai"],
  // ── New corridors (2026-06-15) ──
  ["Ennore","Royapuram"],
  ["Madhavaram","Perambur"],["Madhavaram","Ennore"],
  ["Redhills","Ambattur"],["Redhills","Madhavaram"],
  ["Mogappair","Ambattur"],["Mogappair","Anna Nagar"],
  ["Maduravoyal","Poonamallee"],["Maduravoyal","Koyambedu"],["Maduravoyal","Porur"],
  ["Teynampet","T. Nagar"],["Teynampet","Saidapet"],["Teynampet","Nungambakkam"],
  ["Medavakkam","Velachery"],["Medavakkam","Pallikaranai"],
  ["Vandalur","Tambaram"],["Vandalur","Guduvanchery"],
  ["Kelambakkam","SRM Nagar"],["Kelambakkam","Guduvanchery"],
  ["Guduvanchery","Tambaram"],
];

// ── HALF_SEP: node positions are pre-optimised (all angles ≥20°, 0 crossings)
// Upper-bound 2.0 so near-node lane crossings stay within ≤11px of node center
const basePos: Record<string, Pt> = {};
for (const [k, v] of Object.entries(BASE)) basePos[k] = { x: v.x, y: v.y };

let HALF_SEP = 2.0;
for (let hs = 2.0; hs >= 1.0; hs -= 0.5) {
  if (countX(buildSegs(basePos, corridors, hs)) === 0) { HALF_SEP = hs; break; }
}

const nodeLayout: Record<string, { x: number; y: number; short: string }> = {};
for (const [k, v] of Object.entries(BASE))
  nodeLayout[k] = { x: v.x, y: v.y, short: v.short };

if (import.meta.dev) console.log(`[SchematicMap] HALF_SEP=${HALF_SEP} (angles≥20°, 0 cross)`);

// ── Schematic bucket lookup: "NodeA|NodeB" → {fwd: float[], bwd: float[]} ────
// fwd[i] = congestion at fraction i/N along A→B; bwd[i] = congestion along B→A
const schematicByPair = computed(() => {
  const m: Record<string, { fwd: number[]; bwd: number[] }> = {};
  for (const link of props.schematicLinks) {
    if (!link?.from || !link?.to) continue;
    m[`${link.from}|${link.to}`] = { fwd: link.forward,  bwd: link.backward };
    m[`${link.to}|${link.from}`] = { fwd: link.backward, bwd: link.forward  };
  }
  return m;
});

// ── Pan / Zoom ────────────────────────────────────────────────────────────
const groupTransform = computed(() =>
  `translate(${vp.value.x.toFixed(1)},${vp.value.y.toFixed(1)}) scale(${vp.value.zoom.toFixed(4)})`
);

function calcInitVp() {
  if (!svgEl.value) return;
  const w = svgEl.value.clientWidth;
  const h = svgEl.value.clientHeight;
  const z = Math.min(w / VB_W, h / VB_H) * 0.93;
  vp.value = { zoom: z, x: (w - VB_W * z) / 2, y: (h - VB_H * z) / 2 };
}

function onWheel(e: WheelEvent) {
  e.preventDefault();
  const f    = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const rect = svgEl.value!.getBoundingClientRect();
  const mx   = e.clientX - rect.left;
  const my   = e.clientY - rect.top;
  const v    = vp.value;
  const nz   = Math.max(0.25, Math.min(10, v.zoom * f));
  vp.value   = { zoom: nz, x: mx - (mx - v.x) * nz / v.zoom, y: my - (my - v.y) * nz / v.zoom };
}

function onMouseDown(e: MouseEvent) { isDragging.value = true; dragStart.value = { lx: e.clientX, ly: e.clientY }; }
function onMouseMove(e: MouseEvent) {
  if (!isDragging.value) return;
  vp.value = { ...vp.value, x: vp.value.x + (e.clientX - dragStart.value.lx), y: vp.value.y + (e.clientY - dragStart.value.ly) };
  dragStart.value = { lx: e.clientX, ly: e.clientY };
}
function stopDrag() { isDragging.value = false; }

function zoomBy(f: number) {
  if (!svgEl.value) return;
  const cx = svgEl.value.clientWidth / 2, cy = svgEl.value.clientHeight / 2;
  const v  = vp.value;
  const nz = Math.max(0.25, Math.min(10, v.zoom * f));
  vp.value = { zoom: nz, x: cx - (cx - v.x) * nz / v.zoom, y: cy - (cy - v.y) * nz / v.zoom };
}

onMounted(async () => {
  await nextTick();
  calcInitVp();
  svgEl.value?.addEventListener('wheel', onWheel, { passive: false });
});
onUnmounted(() => { svgEl.value?.removeEventListener('wheel', onWheel); });

// ── Corridor rendering data ───────────────────────────────────────────────
interface LaneSeg { p1: Pt; p2: Pt; color: string; op: number; }
interface CorridorRender {
  key: string; a: string; b: string;
  fwdSegs: LaneSeg[]; bwdSegs: LaneSeg[];
  la: Pt; lb: Pt;
}

const nodeMap = computed(() => {
  const m: Record<string, any> = {};
  for (const n of props.intersections) m[n.name] = n;
  return m;
});
function nodeData(name: string) { return nodeMap.value[name] ?? { congestion: 0.3 }; }

function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }

const corridorData = computed((): CorridorRender[] => {
  const out: CorridorRender[] = [];

  for (const [a, b] of corridors) {
    const la = nodeLayout[a], lb = nodeLayout[b];
    if (!la || !lb) continue;

    const { x: px, y: py } = perpOff(la.x, la.y, lb.x, lb.y, HALF_SEP);

    // ── get per-bucket arrays from backend data ───────────────────────────
    const bucket = schematicByPair.value[`${a}|${b}`];
    const fwdArr = bucket?.fwd;
    const bwdArr = bucket?.bwd;
    const N      = fwdArr?.length ?? 1;

    // ── fallback: use node congestion when no bucket data yet ─────────────
    const cA = (nodeData(a).congestion as number) ?? 0.3;
    const cB = (nodeData(b).congestion as number) ?? 0.3;

    const fwdSegs: LaneSeg[] = [];
    const bwdSegs: LaneSeg[] = [];

    for (let i = 0; i < N; i++) {
      const t0 = i / N, t1 = (i + 1) / N;

      // forward lane: A→B (left-offset)
      const fv   = fwdArr ? fwdArr[i] : lerp(cA, cB, (t0 + t1) / 2);
      const fCol = props.congestionColor(fv);
      const fOp  = fv >= 0.55 ? 0.92 : 0.68;
      fwdSegs.push({
        p1: { x: lerp(la.x, lb.x, t0) + px, y: lerp(la.y, lb.y, t0) + py },
        p2: { x: lerp(la.x, lb.x, t1) + px, y: lerp(la.y, lb.y, t1) + py },
        color: fCol, op: fOp,
      });

      // backward lane: B→A (right-offset); bwd[0] is near A so reverse index
      const ri   = N - 1 - i;
      const bv   = bwdArr ? bwdArr[ri] : lerp(cB, cA, (t0 + t1) / 2);
      const bCol = props.congestionColor(bv);
      const bOp  = bv >= 0.55 ? 0.92 : 0.68;
      bwdSegs.push({
        p1: { x: lerp(lb.x, la.x, t0) - px, y: lerp(lb.y, la.y, t0) - py },
        p2: { x: lerp(lb.x, la.x, t1) - px, y: lerp(lb.y, la.y, t1) - py },
        color: bCol, op: bOp,
      });
    }

    out.push({ key: `${a}|${b}`, a, b, la, lb, fwdSegs, bwdSegs });
  }
  return out;
});
</script>

<template>
  <div class="sch-root">
    <div class="svg-wrap">
      <svg
        ref="svgEl"
        class="sch-svg"
        :class="{ grabbing: isDragging }"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="stopDrag"
        @mouseleave="stopDrag"
      >
        <defs>
          <filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feComposite in="SourceGraphic" in2="b" operator="over"/></filter>
          <filter id="ng"><feGaussianBlur stdDeviation="2" result="b"/><feComposite in="SourceGraphic" in2="b" operator="over"/></filter>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(56,189,248,0.04)" stroke-width="0.5"/>
          </pattern>
        </defs>

        <g :transform="groupTransform">
          <rect x="-5000" y="-5000" width="11000" height="11000" fill="url(#grid)"/>

          <!-- District labels -->
          <text x="55"  y="160" class="dlbl">NORTH WEST</text>
          <text x="400" y="44"  class="dlbl">NORTH</text>
          <text x="730" y="40"  class="dlbl">NORTH EAST</text>
          <text x="85"  y="430" class="dlbl">SOUTH WEST</text>
          <text x="400" y="480" class="dlbl">SOUTH</text>
          <text x="635" y="480" class="dlbl">SOUTH EAST</text>

          <!-- Coastline -->
          <path d="M 855 50 Q 870 200 860 360 Q 848 460 840 570"
                stroke="rgba(56,189,248,0.12)" stroke-width="1.5" fill="none" stroke-dasharray="4 6"/>
          <text x="858" y="310" font-size="9" font-family="'Segoe UI',sans-serif"
                fill="rgba(56,189,248,0.18)" letter-spacing="0.12em" text-anchor="middle"
                transform="rotate(-90,858,310)">BAY OF BENGAL</text>

          <!-- Glow pass (sample every 4th bucket for performance) -->
          <g v-for="d in corridorData" :key="`g-${d.key}`">
            <line v-for="(seg, i) in d.fwdSegs.filter((_,i)=>i%4===0)"
                  :key="`gf${i}`"
                  :x1="seg.p1.x" :y1="seg.p1.y" :x2="seg.p2.x" :y2="seg.p2.y"
                  :stroke="seg.color" stroke-width="6" :opacity="seg.op*0.07" filter="url(#glow)"/>
            <line v-for="(seg, i) in d.bwdSegs.filter((_,i)=>i%4===0)"
                  :key="`gb${i}`"
                  :x1="seg.p1.x" :y1="seg.p1.y" :x2="seg.p2.x" :y2="seg.p2.y"
                  :stroke="seg.color" stroke-width="6" :opacity="seg.op*0.07" filter="url(#glow)"/>
          </g>

          <!-- Forward lanes A→B -->
          <g v-for="d in corridorData" :key="`f-${d.key}`">
            <line v-for="(seg, i) in d.fwdSegs" :key="i"
                  :x1="seg.p1.x" :y1="seg.p1.y" :x2="seg.p2.x" :y2="seg.p2.y"
                  :stroke="seg.color" :stroke-width="LINE_W" stroke-linecap="butt" :opacity="seg.op"/>
          </g>

          <!-- Backward lanes B→A -->
          <g v-for="d in corridorData" :key="`bk-${d.key}`">
            <line v-for="(seg, i) in d.bwdSegs" :key="i"
                  :x1="seg.p1.x" :y1="seg.p1.y" :x2="seg.p2.x" :y2="seg.p2.y"
                  :stroke="seg.color" :stroke-width="LINE_W" stroke-linecap="butt" :opacity="seg.op"/>
          </g>

          <!-- Intersection nodes -->
          <g v-for="(layout, name) in nodeLayout" :key="String(name)"
             class="node-g" :transform="`translate(${layout.x},${layout.y})`"
             @click="selected = selected?.name === name ? null : { ...nodeData(String(name)), name }">
            <circle :r="nodeData(String(name)).congestion >= 0.75 ? 13 : 9"
                    :fill="props.congestionColor(nodeData(String(name)).congestion)"
                    opacity="0.1" class="pulse"/>
            <circle r="5" :fill="props.congestionColor(nodeData(String(name)).congestion)"
                    opacity="0.9" filter="url(#ng)"/>
            <circle r="5" :fill="props.congestionColor(nodeData(String(name)).congestion)" opacity="0.9"/>
            <circle r="2.5" fill="rgba(2,8,24,0.85)"/>
            <text x="0" :y="nodeData(String(name)).congestion >= 0.75 ? -16 : -10"
                  text-anchor="middle" font-size="7.5" font-family="'Segoe UI',monospace"
                  font-weight="600" letter-spacing="0.04em"
                  :fill="selected?.name === name ? '#38bdf8' : '#94a3b8'">{{ layout.short }}</text>
          </g>

          <!-- Selected node tooltip -->
          <g v-if="selected && nodeLayout[selected.name]"
             :transform="`translate(${Math.min(nodeLayout[selected.name].x + 12, 690)},${Math.max(nodeLayout[selected.name].y - 55, 10)})`">
            <rect x="0" y="0" width="155" height="55" rx="5"
                  fill="rgba(2,8,24,0.96)" stroke="rgba(56,189,248,0.3)" stroke-width="1"/>
            <text x="9" y="16" font-size="8.5" font-family="'Segoe UI',sans-serif" font-weight="700" fill="#e2e8f0">{{ selected.name }}</text>
            <text x="9" y="29" font-size="7.5" font-family="monospace" fill="#64748b">
              Congestion: {{ (selected.congestion * 100).toFixed(0) }}%
            </text>
            <rect x="9" y="36" :width="selected.congestion * 137" height="5" rx="2.5"
                  :fill="props.congestionColor(selected.congestion)" opacity="0.85"/>
            <rect x="9" y="36" width="137" height="5" rx="2.5"
                  fill="none" stroke="rgba(56,189,248,0.15)" stroke-width="1"/>
          </g>
        </g>
      </svg>

      <!-- Zoom controls -->
      <div v-if="!compact" class="zoom-ctrl">
        <button class="zbtn" @click="zoomBy(1.3)" title="Zoom in">+</button>
        <button class="zbtn" @click="calcInitVp()" title="Reset view">⌂</button>
        <button class="zbtn" @click="zoomBy(0.77)" title="Zoom out">−</button>
      </div>
    </div>

    <!-- Right panel -->
    <div v-if="!compact" class="sch-panel">
      <div class="panel-title">INTERSECTIONS</div>
      <div
        v-for="node in intersections" :key="node.name"
        class="sch-row" :class="{ active: selected?.name === node.name }"
        @click="selected = selected?.name === node.name ? null : node"
      >
        <span class="dot" :style="{ background: congestionColor(node.congestion) }"/>
        <span class="nname">{{ node.name }}</span>
        <span class="nval" :style="{ color: congestionColor(node.congestion) }">
          {{ congestionLabel(node.congestion) }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sch-root  { width:100%; height:100%; display:flex; background:#020818; overflow:hidden; }
.svg-wrap  { flex:1; height:100%; position:relative; }
.sch-svg   { width:100%; height:100%; cursor:grab; user-select:none; }
.sch-svg.grabbing { cursor:grabbing; }
.node-g    { cursor:pointer; }

.pulse { animation: pulse 2.5s ease-out infinite; }
@keyframes pulse {
  0%   { r:7;  opacity:.12; }
  50%  { r:13; opacity:.04; }
  100% { r:7;  opacity:.12; }
}

.dlbl {
  font-size:8px; fill:rgba(56,189,248,0.07);
  font-family:'Segoe UI',sans-serif; font-weight:700; letter-spacing:.18em;
}

.zoom-ctrl {
  position:absolute; bottom:14px; left:12px;
  display:flex; flex-direction:column; gap:3px; z-index:10;
}
.zbtn {
  width:26px; height:26px;
  background:rgba(2,5,14,0.92); border:1px solid #0f2040; border-radius:4px;
  color:#2a5070; font-size:14px; font-family:monospace;
  cursor:pointer; display:flex; align-items:center; justify-content:center;
  transition:all .12s;
}
.zbtn:hover { background:rgba(0,60,180,0.15); color:#6699ee; border-color:#1a4080; }

.sch-panel {
  width:185px; flex-shrink:0;
  background:rgba(4,12,30,0.95); border-left:1px solid rgba(56,189,248,0.1);
  padding:8px 0; overflow-y:auto; display:flex; flex-direction:column;
}
.panel-title {
  font-size:.6rem; color:rgba(56,189,248,0.3); letter-spacing:.2em;
  font-weight:700; text-align:center; padding:4px 0 8px;
}
.sch-row {
  display:flex; align-items:center; gap:7px; padding:5px 10px;
  cursor:pointer; border-left:2px solid transparent; transition:all .12s;
}
.sch-row:hover  { background:rgba(56,189,248,0.05); }
.sch-row.active { background:rgba(56,189,248,0.08); border-left-color:#38bdf8; }
.dot   { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.nname { font-size:.63rem; color:#94a3b8; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.nval  { font-size:.6rem; font-weight:600; flex-shrink:0; }
</style>
