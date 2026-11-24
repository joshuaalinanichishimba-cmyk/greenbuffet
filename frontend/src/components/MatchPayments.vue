<!--
  Mobile money and card payments still waiting to be matched. Tick each one
  off against the operator's statement or the merchant phone's messages:
  "Arrived", or "Did not arrive" (it then stops counting as paid, and the
  books move it to money owed to us so it is chased, not lost).
-->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../services/api'
import { kwacha } from '../services/money'
import { session } from '../stores/session'

interface Pending { id: string; order_number: string; label: string; amount_ngwee: number; reference: string; taken_by: string; at: string }
const rows = ref<Pending[]>([])
const error = ref('')
const busy = ref('')

async function load() {
  if (!session.can('payments.confirm')) return
  try {
    rows.value = await api.get<Pending[]>('/sales/payments/unconfirmed')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load payments to match.'
  }
}

async function decide(row: Pending, ok: boolean) {
  busy.value = row.id
  error.value = ''
  try {
    await api.post(`/sales/payments/${row.id}/confirm`, { ok })
    rows.value = rows.value.filter((r) => r.id !== row.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save that.'
  } finally {
    busy.value = ''
  }
}

function when(iso: string) {
  return new Date(iso).toLocaleString('en-ZM', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

onMounted(load)
</script>

<template>
  <section v-if="rows.length || error" class="card match">
    <div class="card-head">
      <div>
        <h3>To match against the statement</h3>
        <p class="muted small">{{ rows.length }} mobile money or card payment{{ rows.length === 1 ? '' : 's' }} nobody has yet seen arrive</p>
      </div>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>When</th><th>Order</th><th>How</th><th>Reference</th><th class="num">Amount</th><th>Taken by</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ when(r.at) }}</td>
            <td>{{ r.order_number }}</td>
            <td>{{ r.label }}</td>
            <td><code>{{ r.reference }}</code></td>
            <td class="num">{{ kwacha(r.amount_ngwee) }}</td>
            <td>{{ r.taken_by }}</td>
            <td class="act">
              <button class="btn-primary btn-small" :disabled="busy === r.id" @click="decide(r, true)">Arrived</button>
              <button class="btn-quiet btn-small" :disabled="busy === r.id" @click="decide(r, false)">Did not arrive</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.match { margin-bottom: 1rem; }
.num { text-align: right; white-space: nowrap; }
.act { display: flex; gap: .4rem; justify-content: flex-end; flex-wrap: wrap; }
</style>
