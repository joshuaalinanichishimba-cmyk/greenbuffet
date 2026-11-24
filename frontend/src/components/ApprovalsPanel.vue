<!--
  Everything waiting on a decision this account can make, and the screen to
  make it on: payments to match, cash moves to confirm, till counts to review,
  journals, leave, payroll. Counts come straight from the records; nothing
  shows when nothing is waiting.
-->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import { api } from '../services/api'
import { kwacha } from '../services/money'
import { session } from '../stores/session'

interface Item { key: string; count: number; amount_ngwee: number; text: string; to: string; level: string }
const items = ref<Item[]>([])

onMounted(async () => {
  if (!session.canAny('payments.confirm', 'cash.approve', 'journal.approve', 'leave.approve', 'payroll.approve')) return
  items.value = (await api.get<{ items: Item[] }>('/home/attention').catch(() => ({ items: [] }))).items
})
</script>

<template>
  <section v-if="items.length" class="card attention">
    <div class="card-head"><h3>Waiting for you</h3></div>
    <ul class="home-list">
      <li v-for="i in items" :key="i.key" class="with-icon">
        <Icon :name="i.level === 'high' ? 'alert' : 'clock'" :class="{ high: i.level === 'high' }" />
        <div>
          <b>{{ i.count }}</b> {{ i.text }}
          <p v-if="i.amount_ngwee" class="sub">{{ kwacha(i.amount_ngwee) }}</p>
        </div>
        <RouterLink :to="i.to">Open</RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.attention { margin-bottom: 1rem; border-color: color-mix(in srgb, var(--warn) 40%, var(--line)); }
.high { color: var(--danger); }
</style>
