<!--
  End of day: the cash-up and sales summary, as on the demo.

  It reads like the sheet a manager signs at closing: what came in by each
  way of paying, what was taken off, what was sold, what was thrown away, and
  how each drawer counted against what it should have held.
-->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import CashReview from '../components/CashReview.vue'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import { api } from '../services/api'
import { kwacha } from '../services/money'
import { stockAmount } from '../services/quantities'

interface Day {
  date: string; title: string
  mobile_ngwee: number; airtel_ngwee: number; mtn_ngwee: number; zamtel_ngwee: number
  card_ngwee: number; cash_ngwee: number; account_ngwee: number
  refunds_ngwee: number; discounts_ngwee: number; net_ngwee: number
  paid_orders: number; cancelled: number; still_open: number
  items: { name: string; qty: number; sales_ngwee: number }[]
  waste: { name: string; unit: string; quantity_milli: number; cost_ngwee: number; note: string }[]
  shifts: { opened_by: string; closed_by: string; opened: string; closed: string; float_ngwee: number; expected_ngwee: number; counted_ngwee: number | null; variance_ngwee: number | null }[]
}

const data = ref<Day | null>(null)
const error = ref('')
const picked = ref(new Date(Date.now() + 2 * 3600 * 1000).toISOString().slice(0, 10))

async function load() {
  try {
    data.value = await api.get<Day>(`/dashboard/end-of-day?day=${picked.value}`)
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load the day.'
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <PageHead title="End of day" lead="The cash-up and sales summary for one trading day.">
      <label class="field day">
        Day
        <input v-model="picked" type="date" @change="load" />
      </label>
    </PageHead>

    <CashReview />

    <p v-if="error" class="error">{{ error }}</p>

    <article v-if="data" class="card sheet-doc">
      <header class="doc-head">
        <div>
          <h2>{{ data.title }}</h2>
          <p class="muted">The Green Buffet · Liberty Mall, Kitwe</p>
        </div>
        <span class="pill">{{ data.paid_orders }} paid orders</span>
      </header>

      <div class="grid-2">
        <section>
          <h3>Money in</h3>
          <dl class="lines">
            <div><dt>Airtel Money</dt><dd>{{ kwacha(data.airtel_ngwee) }}</dd></div>
            <div><dt>MTN MoMo</dt><dd>{{ kwacha(data.mtn_ngwee) }}</dd></div>
            <div><dt>Zamtel Kwacha</dt><dd>{{ kwacha(data.zamtel_ngwee) }}</dd></div>
            <div><dt>Card</dt><dd>{{ kwacha(data.card_ngwee) }}</dd></div>
            <div><dt>Cash at counter</dt><dd>{{ kwacha(data.cash_ngwee) }}</dd></div>
            <div v-if="data.account_ngwee"><dt>On account</dt><dd>{{ kwacha(data.account_ngwee) }}</dd></div>
            <div class="minus"><dt>Refunds</dt><dd>−{{ kwacha(data.refunds_ngwee) }}</dd></div>
            <div class="sum"><dt>Net sales</dt><dd>{{ kwacha(data.net_ngwee) }}</dd></div>
          </dl>
          <p class="muted small">Discounts and free bowls already taken off: {{ kwacha(data.discounts_ngwee) }}</p>
        </section>

        <section>
          <h3>Orders</h3>
          <dl class="lines">
            <div><dt>Paid</dt><dd>{{ data.paid_orders }}</dd></div>
            <div><dt>Cancelled</dt><dd>{{ data.cancelled }}</dd></div>
            <div><dt>Still not paid</dt><dd :class="{ warn: data.still_open }">{{ data.still_open }}</dd></div>
          </dl>

          <h3 style="margin-top: 1.2rem">The drawer</h3>
          <p v-if="!data.shifts.length" class="muted">No till was opened this day.</p>
          <div v-for="(s, i) in data.shifts" :key="i" class="shift">
            <p class="muted small">Opened {{ s.opened }} by {{ s.opened_by }}<template v-if="s.closed">, counted {{ s.closed }} by {{ s.closed_by }}</template></p>
            <dl class="lines">
              <div><dt>Float</dt><dd>{{ kwacha(s.float_ngwee) }}</dd></div>
              <div><dt>Should hold</dt><dd>{{ kwacha(s.expected_ngwee) }}</dd></div>
              <div><dt>Counted</dt><dd>{{ s.counted_ngwee === null ? 'Not counted yet' : kwacha(s.counted_ngwee) }}</dd></div>
              <div v-if="s.variance_ngwee !== null" class="sum">
                <dt>{{ s.variance_ngwee < 0 ? 'Short' : s.variance_ngwee > 0 ? 'Over' : 'Exact' }}</dt>
                <dd :class="{ bad: s.variance_ngwee < 0 }">{{ kwacha(Math.abs(s.variance_ngwee)) }}</dd>
              </div>
            </dl>
          </div>
        </section>
      </div>

      <section style="margin-top: 1.4rem">
        <h3>Items sold</h3>
        <p v-if="!data.items.length" class="muted">Nothing sold.</p>
        <div v-else class="table-wrap">
          <table>
            <thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Sales</th></tr></thead>
            <tbody>
              <tr v-for="i in data.items" :key="i.name">
                <td>{{ i.name }}</td>
                <td class="num">{{ i.qty }}</td>
                <td class="num">{{ kwacha(i.sales_ngwee) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section style="margin-top: 1.4rem">
        <h3>Wastage</h3>
        <p v-if="!data.waste.length" class="muted">Nothing thrown away.</p>
        <div v-else class="table-wrap">
          <table>
            <thead><tr><th>Ingredient</th><th class="num">Amount</th><th class="num">Cost</th><th class="hide-small">Why</th></tr></thead>
            <tbody>
              <tr v-for="(w, i) in data.waste" :key="i">
                <td>{{ w.name }}</td>
                <td class="num">{{ stockAmount(w.unit, w.quantity_milli) }}</td>
                <td class="num">{{ kwacha(w.cost_ngwee) }}</td>
                <td class="hide-small muted">{{ w.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <footer class="signoff">
        <div><span class="muted small">Counted by</span><div class="line" /></div>
        <div><span class="muted small">Checked by</span><div class="line" /></div>
      </footer>
    </article>
  </AppShell>
</template>

<style scoped>
.day { min-width: 180px; }
.sheet-doc { padding: 1.4rem 1.5rem; }
.doc-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--line); }
.doc-head h2 { margin: 0; font-size: 1.3rem; }
h3 { margin: 0 0 .6rem; }
.small { font-size: .85rem; }
.lines { margin: 0; display: grid; gap: .1rem; }
.lines div { display: flex; justify-content: space-between; gap: 1rem; padding: .35rem 0; border-bottom: 1px dashed var(--line); }
.lines dt { color: var(--ink); }
.lines dd { margin: 0; font-variant-numeric: tabular-nums; font-weight: 600; }
.lines .minus dd { color: var(--danger); }
.lines .sum { border-bottom: 0; border-top: 2px solid var(--ink); margin-top: .3rem; padding-top: .5rem; }
.lines .sum dt, .lines .sum dd { font-family: var(--display); font-weight: 900; font-size: 1.05rem; }
.lines .warn { color: var(--warn); }
.lines .bad { color: var(--danger); }
.shift + .shift { margin-top: 1rem; }
.signoff { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-top: 2rem; }
.signoff .line { border-bottom: 1.5px solid var(--ink); height: 2.2rem; }
</style>
