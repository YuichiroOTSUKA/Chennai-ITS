<script setup lang="ts">
const route = useRoute()

const nav = [
  { to: "/",               icon: "⊞", label: "MAP",        key: "index"          },
  { to: "/compare",        icon: "⇄", label: "COMPARE",    key: "compare"        },
  { to: "/analytics",      icon: "▦", label: "ANALYTICS",  key: "analytics"      },
  { to: "/method-analysis",icon: "⊕", label: "METHOD",     key: "method-analysis"},
  { to: "/simulation",     icon: "▷", label: "SIMULATION", key: "simulation"     },
  { to: "/forecast",       icon: "◈", label: "FORECAST",   key: "forecast"       },
  { to: "/route",          icon: "⇆", label: "ROUTE",      key: "route"          },
]

const isActive = (item: typeof nav[0]) =>
  route.path === item.to || (item.to !== "/" && route.path.startsWith(item.to))
</script>

<template>
  <nav class="nav-sidebar">
    <!-- Logo -->
    <div class="nav-logo">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="url(#ng)" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="3" fill="url(#ng)"/>
        <line x1="12" y1="2"  x2="12" y2="7"  stroke="url(#ng)" stroke-width="1.2"/>
        <line x1="12" y1="17" x2="12" y2="22" stroke="url(#ng)" stroke-width="1.2"/>
        <line x1="2"  y1="12" x2="7"  y2="12" stroke="url(#ng)" stroke-width="1.2"/>
        <line x1="17" y1="12" x2="22" y2="12" stroke="url(#ng)" stroke-width="1.2"/>
        <defs>
          <linearGradient id="ng" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
            <stop stop-color="#38bdf8"/>
            <stop offset="1" stop-color="#6366f1"/>
          </linearGradient>
        </defs>
      </svg>
    </div>

    <div class="nav-divider"/>

    <!-- Nav items -->
    <NuxtLink
      v-for="item in nav"
      :key="item.to"
      :to="item.to"
      :class="['nav-item', isActive(item) && 'active']"
    >
      <span class="nav-icon">{{ item.icon }}</span>
      <span class="nav-label">{{ item.label }}</span>
    </NuxtLink>

    <div class="nav-spacer"/>
    <div class="nav-version">ITS</div>
  </nav>
</template>

<style scoped>
.nav-sidebar {
  position: fixed;
  left: 0; top: 0; bottom: 0;
  width: 52px;
  background: rgba(2, 8, 24, 0.97);
  border-right: 1px solid rgba(56, 189, 248, 0.12);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0 8px;
  z-index: 200;
  backdrop-filter: blur(12px);
  box-shadow: 2px 0 24px rgba(56, 189, 248, 0.04);
  overflow: hidden;
  transition: width 0.22s cubic-bezier(.4,0,.2,1);
  gap: 0;
}
.nav-sidebar:hover {
  width: 156px;
  align-items: flex-start;
  padding-left: 10px;
}

.nav-logo {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.nav-divider {
  width: 28px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(56,189,248,0.3), transparent);
  margin: 6px 0 8px;
  flex-shrink: 0;
  transition: width 0.22s;
}
.nav-sidebar:hover .nav-divider {
  width: 132px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 8px;
  border-radius: 8px;
  text-decoration: none;
  color: #475569;
  width: 36px;
  overflow: hidden;
  transition: all 0.18s;
  white-space: nowrap;
  flex-shrink: 0;
  position: relative;
}
.nav-sidebar:hover .nav-item {
  width: 136px;
}
.nav-item:hover {
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.08);
}
.nav-item.active {
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.12);
  box-shadow: inset 3px 0 0 #38bdf8;
}
.nav-item.active::before {
  content: "";
  position: absolute;
  left: 0; top: 20%; bottom: 20%;
  width: 3px;
  background: linear-gradient(180deg, #38bdf8, #6366f1);
  border-radius: 0 2px 2px 0;
}

.nav-icon {
  font-size: 14px;
  flex-shrink: 0;
  width: 20px;
  text-align: center;
  line-height: 1;
}
.nav-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  opacity: 0;
  transition: opacity 0.15s;
  font-family: "Segoe UI", system-ui, sans-serif;
}
.nav-sidebar:hover .nav-label {
  opacity: 1;
}

.nav-spacer { flex: 1; }

.nav-version {
  font-size: 7px;
  color: #1e3050;
  letter-spacing: 0.15em;
  font-weight: 600;
  margin-bottom: 2px;
}
</style>
