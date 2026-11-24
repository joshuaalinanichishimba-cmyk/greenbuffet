<!--
  One line icon from services/icons.ts, drawn the way the demo draws them:
  24px grid, current text colour, 1.9 stroke with round ends.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { ICONS } from '../services/icons'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const body = computed(() => ICONS[props.name] ?? '')
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="ic"
    v-html="body"
  />
</template>
