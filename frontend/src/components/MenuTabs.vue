<!-- The four parts of the Menu, which the demo shows as one screen. -->
<script setup lang="ts">
import SubNav from './SubNav.vue'
import { session } from '../stores/session'
</script>

<template>
  <SubNav
    :links="[
      { to: '/menu', label: 'Prices & availability' },
      { to: '/menu/items', label: 'Items & recipes' },
      { to: '/menu/choices', label: 'Build options', show: session.can('menu.edit') },
      { to: '/menu/ingredients', label: 'Ingredients', show: session.can('menu.edit') },
    ]"
  />
</template>
