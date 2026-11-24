<!--
  The ring on the demo's "How customers paid today": one arc per way of
  paying, the total in the middle.
-->
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ parts: { value: number; colour: string }[]; label: string; sub: string }>()
const R = 52
const C = 2 * Math.PI * R

const arcs = computed(() => {
  const total = props.parts.reduce((s, p) => s + p.value, 0)
  let offset = 0
  return props.parts
    .filter((p) => p.value > 0)
    .map((p) => {
      const length = total ? (p.value / total) * C : 0
      const arc = { colour: p.colour, dash: `${Math.max(length - 2, 0)} ${C}`, offset: -offset }
      offset += length
      return arc
    })
})
</script>

<template>
  <div class="donut">
    <svg viewBox="0 0 132 132" aria-hidden="true">
      <circle cx="66" cy="66" :r="R" fill="none" stroke="var(--line)" stroke-width="14" />
      <circle
        v-for="(a, i) in arcs"
        :key="i"
        cx="66" cy="66" :r="R" fill="none"
        :stroke="a.colour" stroke-width="14"
        :stroke-dasharray="a.dash" :stroke-dashoffset="a.offset"
        transform="rotate(-90 66 66)"
      />
    </svg>
    <div class="middle">
      <b>{{ label }}</b>
      <span>{{ sub }}</span>
    </div>
  </div>
</template>

<style scoped>
.donut { position: relative; width: 132px; height: 132px; flex: none; }
.donut svg { width: 100%; height: 100%; }
.middle { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; line-height: 1.15; }
.middle b { font-family: var(--display); font-weight: 900; font-size: 1.05rem; color: var(--ink); }
.middle span { font-size: .8rem; color: var(--muted); }
</style>
