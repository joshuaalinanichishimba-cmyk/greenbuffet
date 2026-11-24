<!--
  The demo's segmented tabs, used where one sidebar entry covers screens that
  are separate pages here: Staff & roles, Menu, Inventory, Settings.
-->
<script setup lang="ts">
import { useRoute } from 'vue-router'

defineProps<{ links: { to: string; label: string; show?: boolean }[] }>()
const route = useRoute()
</script>

<template>
  <nav class="seg subnav" aria-label="Sections">
    <RouterLink
      v-for="l in links.filter((x) => x.show !== false)"
      :key="l.to"
      :to="l.to"
      :aria-current="route.path === l.to ? 'page' : undefined"
    >
      {{ l.label }}
    </RouterLink>
  </nav>
</template>

<style scoped>
.subnav { margin: 0 0 1.2rem; }
.subnav a {
  padding: .42rem .95rem; border-radius: 999px; font-weight: 700; font-size: .9rem;
  color: var(--ink); text-decoration: none; min-height: 36px; display: inline-flex; align-items: center;
}
.subnav a[aria-current='page'] { background: var(--paper); color: var(--green-deep); box-shadow: var(--shadow); }
</style>
