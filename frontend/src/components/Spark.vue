<!--
  The thin trend line along the bottom of a KPI card, as on the demo's
  Overview: the last seven days, with a soft fill underneath.
-->
<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ values: number[]; colour?: string }>(), { colour: 'var(--green)' })
const W = 240
const H = 34

const path = computed(() => {
  const v = props.values.length ? props.values : [0, 0]
  const max = Math.max(...v, 1)
  const step = W / Math.max(v.length - 1, 1)
  const pts = v.map((n, i) => [i * step, H - 3 - (n / max) * (H - 8)])
  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  return { line, area: `${line} L${W},${H} L0,${H} Z` }
})
const id = `spark-${Math.random().toString(36).slice(2, 8)}`
</script>

<template>
  <svg class="kpi-spark" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <linearGradient :id="id" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" :stop-color="colour" stop-opacity=".22" />
        <stop offset="1" :stop-color="colour" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path :d="path.area" :fill="`url(#${id})`" />
    <path :d="path.line" fill="none" :stroke="colour" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" />
  </svg>
</template>
