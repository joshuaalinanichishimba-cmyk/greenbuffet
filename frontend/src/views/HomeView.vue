<!--
  The first screen after sign-in. It picks the home that fits the account
  (see services/home.ts); the kitchen never lands here, because the router
  sends it straight to the kitchen board, as the demo does.
-->
<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { homeFor } from '../services/home'
import { session } from '../stores/session'

const HOMES = {
  overview: defineAsyncComponent(() => import('./DashboardView.vue')),
  system: defineAsyncComponent(() => import('./SystemHome.vue')),
  money: defineAsyncComponent(() => import('./MoneyHome.vue')),
  cashier: defineAsyncComponent(() => import('./CashierHome.vue')),
  stock: defineAsyncComponent(() => import('./StockHome.vue')),
  kitchen: defineAsyncComponent(() => import('./KitchenView.vue')),
}

const view = computed(() => HOMES[homeFor(session.user.value?.role_id, session.permissions.value)])
</script>

<template>
  <component :is="view" />
</template>
