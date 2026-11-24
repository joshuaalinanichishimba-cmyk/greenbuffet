<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type BalanceSheet, type CashFlow, type ProfitAndLoss, type TrialBalance } from '../services/api'
import { kwacha } from '../services/money'

const tab = ref<'pl' | 'bs' | 'cash' | 'tb'>('pl')
const month = ref(new Date().toISOString().slice(0, 7))
const pl = ref<ProfitAndLoss | null>(null)
const bs = ref<BalanceSheet | null>(null)
const cash = ref<CashFlow | null>(null)
const tb = ref<TrialBalance | null>(null)
const loading = ref(true)
const error = ref('')

const months = computed(() => {
  const out: string[] = []
  const now = new Date()
  for (let back = 0; back < 12; back += 1) {
    const when = new Date(now.getFullYear(), now.getMonth() - back, 1)
    out.push(when.toISOString().slice(0, 7))
  }
  return out
})

function monthName(value: string) {
  const [year, mon] = value.split('-')
  return new Date(Number(year), Number(mon) - 1, 1).toLocaleDateString('en-GB', {
    month: 'long', year: 'numeric',
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [a, b, c, d] = await Promise.all([
      api.profitAndLoss(month.value),
      api.balanceSheet(month.value),
      api.cashFlow(month.value),
      api.trialBalance(month.value),
    ])
    pl.value = a
    bs.value = b
    cash.value = c
    tb.value = d
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the books.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(month, load)
</script>

<template>
  <AppShell>
    <div class="head">
      <div>
        <h1>The books</h1>
        <p class="muted">
          Every figure here is the sum of journal entries, and every entry can be traced to the
          receipt or delivery it came from.
        </p>
      </div>
      <label class="field">
        Month
        <select v-model="month">
          <option v-for="m in months" :key="m" :value="m">{{ monthName(m) }}</option>
        </select>
      </label>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="tabs">
      <button :class="{ on: tab === 'pl' }" @click="tab = 'pl'">Profit and loss</button>
      <button :class="{ on: tab === 'bs' }" @click="tab = 'bs'">Balance sheet</button>
      <button :class="{ on: tab === 'cash' }" @click="tab = 'cash'">Cash</button>
      <button :class="{ on: tab === 'tb' }" @click="tab = 'tb'">Trial balance</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <!-- profit and loss -->
    <section v-else-if="tab === 'pl' && pl" class="panel statement">
      <h2>Profit and loss</h2>
      <p class="muted">{{ monthName(month) }}</p>

      <h3>Money in</h3>
      <dl>
        <div v-for="row in pl.income" :key="row.code">
          <dt>{{ row.name }}</dt><dd>{{ kwacha(row.amount_ngwee) }}</dd>
        </div>
        <div class="sum"><dt>Total sales</dt><dd>{{ kwacha(pl.total_income_ngwee) }}</dd></div>
      </dl>

      <h3>What the food cost</h3>
      <dl>
        <div v-for="row in pl.cost_of_sales" :key="row.code">
          <dt>{{ row.name }}</dt><dd>{{ kwacha(row.amount_ngwee) }}</dd>
        </div>
        <div class="sum">
          <dt>Gross profit</dt>
          <dd>{{ kwacha(pl.gross_profit_ngwee) }} <small class="muted">{{ pl.gross_margin_percent }}%</small></dd>
        </div>
      </dl>

      <h3>Running costs</h3>
      <dl>
        <div v-for="row in pl.expenses" :key="row.code">
          <dt>{{ row.name }}</dt><dd>{{ kwacha(row.amount_ngwee) }}</dd>
        </div>
        <div class="sum"><dt>Total costs</dt><dd>{{ kwacha(pl.total_expenses_ngwee) }}</dd></div>
      </dl>

      <dl class="final" :class="pl.profit_ngwee >= 0 ? 'good' : 'bad'">
        <div><dt>{{ pl.profit_ngwee >= 0 ? 'Profit' : 'Loss' }} for the month</dt>
          <dd>{{ kwacha(Math.abs(pl.profit_ngwee)) }}</dd></div>
      </dl>
    </section>

    <!-- balance sheet -->
    <section v-else-if="tab === 'bs' && bs" class="panel statement">
      <h2>Balance sheet</h2>
      <p class="muted">As at {{ bs.as_at }}</p>

      <h3>What we own</h3>
      <dl>
        <div v-for="row in bs.assets" :key="row.code">
          <dt>{{ row.name }}</dt><dd>{{ kwacha(row.amount_ngwee) }}</dd>
        </div>
        <div class="sum"><dt>Total</dt><dd>{{ kwacha(bs.total_assets_ngwee) }}</dd></div>
      </dl>

      <h3>What we owe</h3>
      <dl>
        <div v-for="row in bs.liabilities" :key="row.code">
          <dt>{{ row.name }}</dt><dd>{{ kwacha(row.amount_ngwee) }}</dd>
        </div>
        <div class="sum"><dt>Total</dt><dd>{{ kwacha(bs.total_liabilities_ngwee) }}</dd></div>
      </dl>

      <h3>The owner's stake</h3>
      <dl>
        <div v-for="row in bs.equity" :key="row.code">
          <dt>{{ row.name }}</dt><dd>{{ kwacha(row.amount_ngwee) }}</dd>
        </div>
        <div><dt>Profit this period</dt><dd>{{ kwacha(bs.profit_this_period_ngwee) }}</dd></div>
        <div class="sum"><dt>Total</dt><dd>{{ kwacha(bs.total_equity_ngwee) }}</dd></div>
      </dl>

      <p class="check" :class="bs.balanced ? 'ok' : 'off'">
        <template v-if="bs.balanced">
          Balanced: what we own equals what we owe plus the owner's stake.
        </template>
        <template v-else>
          Out by {{ kwacha(Math.abs(bs.difference_ngwee)) }}. Something is wrong — check the journal.
        </template>
      </p>
    </section>

    <!-- cash -->
    <section v-else-if="tab === 'cash' && cash" class="panel statement">
      <h2>Where the money moved</h2>
      <p class="muted">{{ monthName(month) }}</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Account</th><th>Opened with</th><th>In</th><th>Out</th><th>Left</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in cash.accounts" :key="row.code">
              <td><b>{{ row.name }}</b></td>
              <td class="num">{{ kwacha(row.opening_ngwee) }}</td>
              <td class="num in">{{ kwacha(row.in_ngwee) }}</td>
              <td class="num out">{{ kwacha(row.out_ngwee) }}</td>
              <td class="num"><b>{{ kwacha(row.closing_ngwee) }}</b></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td><b>All together</b></td>
              <td class="num">{{ kwacha(cash.opening_ngwee) }}</td>
              <td class="num in">{{ kwacha(cash.in_ngwee) }}</td>
              <td class="num out">{{ kwacha(cash.out_ngwee) }}</td>
              <td class="num"><b>{{ kwacha(cash.closing_ngwee) }}</b></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <!-- trial balance -->
    <section v-else-if="tab === 'tb' && tb" class="panel statement">
      <h2>Trial balance</h2>
      <p class="muted">As at {{ tb.as_at }}</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Code</th><th>Account</th><th>Debit</th><th>Credit</th></tr></thead>
          <tbody>
            <tr v-for="row in tb.rows" :key="row.code">
              <td class="num muted">{{ row.code }}</td>
              <td>{{ row.name }}</td>
              <td class="num">{{ row.debit_ngwee ? kwacha(row.debit_ngwee) : '' }}</td>
              <td class="num">{{ row.credit_ngwee ? kwacha(row.credit_ngwee) : '' }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td></td><td><b>Totals</b></td>
              <td class="num"><b>{{ kwacha(tb.total_debit_ngwee) }}</b></td>
              <td class="num"><b>{{ kwacha(tb.total_credit_ngwee) }}</b></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p class="check" :class="tb.balanced ? 'ok' : 'off'">
        {{ tb.balanced ? 'The two columns match, so the books balance.'
          : `Out by ${kwacha(Math.abs(tb.total_debit_ngwee - tb.total_credit_ngwee))}.` }}
      </p>
    </section>
  </AppShell>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
.head p { margin: 0 0 1rem; max-width: 55ch; }
.statement { max-width: 640px; }
.statement h2 { margin: 0; font-size: 1.15rem; }
.statement > p.muted { margin: 0.1rem 0 1rem; }
.statement h3 { font-size: 0.95rem; margin: 1.2rem 0 0.4rem; color: var(--muted); }
dl { margin: 0; display: grid; gap: 0.25rem; }
dl > div { display: flex; justify-content: space-between; gap: 1rem; }
dt, dd { margin: 0; font-size: 0.93rem; }
dd { white-space: nowrap; }
.sum { border-top: 1px solid var(--line); padding-top: 0.3rem; margin-top: 0.3rem; font-weight: 700; }
.final { margin-top: 1.4rem; border-top: 2px solid var(--ink); padding-top: 0.5rem; font-size: 1.1rem; font-weight: 800; }
.final.good dd { color: var(--green-mid); }
.final.bad dd { color: var(--danger); }
.check { margin-top: 1.2rem; padding: 0.5rem 0.7rem; border-radius: 10px; font-size: 0.88rem; }
.check.ok { background: var(--ok-soft); color: var(--green-deep); }
.check.off { background: var(--danger-soft); color: var(--danger); }
.num { white-space: nowrap; text-align: right; }
th:nth-child(n + 3), td.num { text-align: right; }
.in { color: var(--green-mid); }
.out { color: var(--kraft-ink); }
tfoot td { border-top: 2px solid var(--line); }
</style>
