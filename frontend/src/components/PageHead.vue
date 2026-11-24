<!--
  The top of a screen, as the demo lays it out: a brown Montserrat title, a
  line under it, and the screen's main actions on the right.
-->
<script setup lang="ts">
defineProps<{ title: string; lead?: string }>()
</script>

<template>
  <div class="head">
    <div class="words">
      <h1>{{ title }}</h1>
      <p v-if="lead" class="lead">{{ lead }}</p>
    </div>
    <div v-if="$slots.default" class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.head { display: flex; gap: 1rem; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; margin-bottom: 1.2rem; }
.words { min-width: 0; }
.words .lead { margin: .3rem 0 0; }
.actions { display: flex; gap: .6rem; flex-wrap: wrap; }
</style>
