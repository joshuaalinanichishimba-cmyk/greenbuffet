<!--
  Payments: every payment and refund, as on the demo's Payments screen.

  The demo shows gateway fees and settlement; this restaurant has no gateway,
  so the honest equivalent is the operator's reference on every mobile money
  and card payment. One without a reference cannot be matched against the
  Airtel or MTN statement later, so those are what "needs attention" means.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import MatchPayments from '../components/MatchPayments.vue'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import Icon from '../components/Icon.vue'
import { api } from '../services/api'
import { kwacha, kwachaShort } from '../services/money'

interface Row {
  id: string; when: string; order: string; method: string; method_code: string
  amount_ngwee: number; reference: string; by: string; refund: boolean; status: string
}
interface Data {
  collected_ngwee: number; refunded_ngwee: number; net_ngwee: number
  count: number; needs_attention: number
  by_method: Record<string, number>; rows: Row[]
}

const data = ref<Data | null>(null)
const error = ref('')
const filter = ref('')
const days = ref(14)

const filters = [
  { v: '', label: 'All' },
  { v: 'mobile', label: 'Mobile money' },
  { v: 'card', label: 'Card' },
  { v: 'cash', label: 'Cash' },
  { v: 'attention', label: 'Needs attention' },
  { v: 'refunds', label: 'Refunds' },
]

const methods = computed(() => {
  const m = data.value?.by_method ?? {}
  return [
    { label: 'Airtel Money', v: m.airtel ?? 0 },
    { label: 'MTN MoMo', v: m.mtn ?? 0 },
    { label: 'Zamtel Kwacha', v: m.zamtel ?? 0 },
    { label: 'Card', v: m.card ?? 0 },
    { label: 'Cash', v: m.cash ?? 0 },
  ]
})

async function load() {
  try {
    data.value = await api.get<Data>(`/dashboard/payments?method=${filter.value}&days=${days.value}`)
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load payments.'
  }
}

function setFilter(v: string) {
  filter.value = v
  load()
}

function setDays(n: number) {
  days.value = n
  load()
}

onMounted(load)
</script>

<template>
  <AppShell>
    <PageHead title="Payments" :lead="`Every payment and refund over the last ${days} days. Mobile money and card payments need the operator's reference so they can be matched to the statement.`">
      <div class="tabs" style="margin: 0">
        <button v-for="n in [1, 7, 14, 30]" :key="n" :class="{ on: days === n }" @click="setDays(n)">
          {{ n === 1 ? 'Today' : `${n} days` }}
        </button>
      </div>
    </PageHead>

    <p v-if="error" class="error">{{ error }}</p>
    <MatchPayments />

    <template v-if="data">
      <div class="kpis">
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="cash" :size="18" /></span><span class="kpi-label">Collected</span></div>
          <span class="kpi-value">{{ kwachaShort(data.collected_ngwee) }}</span>
          <p class="kpi-note">{{ data.count }} payments</p>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon brown"><Icon name="receipt" :size="18" /></span><span class="kpi-label">Refunded</span></div>
          <span class="kpi-value">{{ kwachaShort(data.refunded_ngwee) }}</span>
          <p class="kpi-note">Given back to customers</p>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="card" :size="18" /></span><span class="kpi-label">Kept</span></div>
          <span class="kpi-value">{{ kwachaShort(data.net_ngwee) }}</span>
          <p class="kpi-note">Collected less refunds</p>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon amber"><Icon name="alert" :size="18" /></span><span class="kpi-label">Needs attention</span></div>
          <span class="kpi-value" :style="{ color: data.needs_attention ? 'var(--warn)' : undefined }">{{ data.needs_attention }}</span>
          <p class="kpi-note">Mobile or card with no reference</p>
        </div>
      </div>

      <section class="card methods">
        <div v-for="m in methods" :key="m.label" class="method">
          <span class="muted">{{ m.label }}</span>
          <b>{{ kwachaShort(m.v) }}</b>
        </div>
      </section>

      <div class="tabs">
        <button v-for="f in filters" :key="f.v" :class="{ on: filter === f.v }" @click="setFilter(f.v)">{{ f.label }}</button>
      </div>

      <div v-if="!data.rows.length" class="empty">No payments match.</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Order</th>
              <th>Method</th>
              <th class="hide-small">Reference</th>
              <th class="hide-small">Taken by</th>
              <th class="num">Amount</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in data.rows" :key="r.id">
              <td class="muted tnum">{{ r.when }}</td>
              <td><b>{{ r.order }}</b></td>
              <td>{{ r.method }}</td>
              <td class="hide-small tnum">{{ r.reference || '—' }}</td>
              <td class="hide-small">{{ r.by }}</td>
              <td class="num"><b :style="{ color: r.refund ? 'var(--danger)' : undefined }">{{ r.refund ? '−' : '' }}{{ kwacha(r.amount_ngwee) }}</b></td>
              <td>
                <span class="pill" :class="{ danger: r.refund, warn: r.status === 'Needs reference' }">{{ r.status }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.methods { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 130px), 1fr)); gap: .8rem; margin-bottom: 1.2rem; }
.method { display: grid; gap: .15rem; }
.method b { font-family: var(--display); font-weight: 800; font-size: 1.15rem; }
</style>
