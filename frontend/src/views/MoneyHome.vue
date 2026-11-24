<!--
  The accountant's home: what came in, what is owed, what needs a decision.

  It answers the questions of someone who closes the books rather than runs
  the counter: did today's money arrive by the routes it should, did every
  till count out right, are the books in balance, what do we owe suppliers,
  and is there a journal or a payroll waiting for approval.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import Icon from '../components/Icon.vue'
import { api } from '../services/api'
import { kwacha, kwachaShort } from '../services/money'
import { firstName, greeting, problemText } from '../services/home'
import { session } from '../stores/session'
import ApprovalsPanel from '../components/ApprovalsPanel.vue'

interface MoneyHome {
  takings: { method: string; label: string; amount_ngwee: number }[]
  takings_ngwee: number
  mobile_ngwee: number
  mtd_sales_ngwee: number
  mtd_change: number | null
  mtd_orders: number
  month_label: string
  tills: { who: string; closed: string; expected_ngwee: number; counted_ngwee: number; variance_ngwee: number }[]
  tills_short_ngwee: number
  open_tills: number
  books: { income_ngwee: number; gross_margin_percent: number; profit_ngwee: number; balanced: boolean | null; drafts: number; can_approve: boolean } | null
  payroll: { period: string; this_month: string | null; latest: { period: string; status: string; net_ngwee: number; employer_cost_ngwee: number } | null; can_approve: boolean } | null
  owed: { total_ngwee: number; overdue_ngwee: number; suppliers: { name: string; owed_ngwee: number; oldest_days: number }[] } | null
}

const data = ref<MoneyHome | null>(null)
const error = ref('')
let timer: number | undefined

async function load() {
  try {
    data.value = await api.get<MoneyHome>('/home/money')
    error.value = ''
  } catch (problem) {
    error.value = problemText(problem, 'Could not load the money summary.')
  }
}

const takingsMax = computed(() => Math.max(1, ...(data.value?.takings ?? []).map((t) => t.amount_ngwee)))

const PAYROLL: Record<string, string> = { draft: 'Waiting for approval', approved: 'Approved, not yet paid', paid: 'Paid' }

function monthName(period: string) {
  const [y, m] = period.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('en-ZM', { month: 'long', year: 'numeric' })
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 60000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <div class="home-head">
      <div>
        <h1>{{ greeting() }}, {{ firstName(session.user.value?.name) }}</h1>
        <p class="lead">The money: today, this month, and what needs your sign-off.</p>
      </div>
      <div class="actions">
        <RouterLink to="/end-of-day" class="btn-outline"><Icon name="calendarCheck" :size="18" /> End of day</RouterLink>
        <RouterLink v-if="data?.books" to="/books" class="btn-primary"><Icon name="book" :size="18" /> The books</RouterLink>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <ApprovalsPanel />

    <template v-if="data">
      <!-- things waiting on a decision come first -->
      <section v-if="data.books && data.books.balanced === false" class="card home-banner warn">
        <Icon name="alert" :size="22" />
        <div class="text">
          <b>The books do not balance</b>
          <span>Debits and credits differ this month. The trial balance shows which accounts.</span>
        </div>
        <RouterLink to="/books" class="btn-outline">Trial balance</RouterLink>
      </section>
      <section v-if="data.books?.drafts" class="card home-banner warn">
        <Icon name="journal" :size="22" />
        <div class="text">
          <b>{{ data.books.drafts }} journal entr{{ data.books.drafts === 1 ? 'y is' : 'ies are' }} waiting for approval</b>
          <span>{{ data.books.can_approve ? 'They do not reach the books until someone approves them.' : 'Someone who can approve journals needs to look at them.' }}</span>
        </div>
        <RouterLink to="/books/journal" class="btn-outline">Journal</RouterLink>
      </section>
      <section v-if="data.payroll?.this_month === 'draft' || data.payroll?.this_month === 'approved'" class="card home-banner warn">
        <Icon name="users" :size="22" />
        <div class="text">
          <b>{{ monthName(data.payroll.period) }} payroll: {{ PAYROLL[data.payroll.this_month] }}</b>
          <span>Staff are paid once it is approved and marked paid.</span>
        </div>
        <RouterLink to="/payroll" class="btn-outline">Payroll</RouterLink>
      </section>

      <div class="kpis">
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="cash" :size="18" /></span><span class="kpi-label">Taken today</span></div>
          <span class="kpi-value">{{ kwachaShort(data.takings_ngwee) }}</span>
          <span class="kpi-sub">{{ kwacha(data.mobile_ngwee) }} by mobile money</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="chart" :size="18" /></span><span class="kpi-label">{{ data.month_label }} so far</span></div>
          <span class="kpi-value">{{ kwachaShort(data.mtd_sales_ngwee) }}</span>
          <span v-if="data.mtd_change !== null" class="delta" :class="{ down: data.mtd_change < 0 }">
            <Icon :name="data.mtd_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.mtd_change) }}%
          </span>
          <span class="kpi-sub">{{ data.mtd_change === null ? `${data.mtd_orders} paid orders` : 'vs the same days last month' }}</span>
        </div>
        <div v-if="data.books" class="kpi">
          <div class="kpi-top"><span class="kpi-icon brown"><Icon name="book" :size="18" /></span><span class="kpi-label">Profit this month</span></div>
          <span class="kpi-value" :class="{ bad: data.books.profit_ngwee < 0 }">{{ kwachaShort(data.books.profit_ngwee) }}</span>
          <span class="kpi-sub">{{ data.books.gross_margin_percent }}% gross margin</span>
        </div>
        <div v-if="data.owed" class="kpi">
          <div class="kpi-top"><span class="kpi-icon amber"><Icon name="truck" :size="18" /></span><span class="kpi-label">Owed to suppliers</span></div>
          <span class="kpi-value">{{ kwachaShort(data.owed.total_ngwee) }}</span>
          <span class="kpi-sub" :class="{ bad: data.owed.overdue_ngwee }">{{ data.owed.overdue_ngwee ? `${kwacha(data.owed.overdue_ngwee)} over 30 days` : 'Nothing overdue' }}</span>
        </div>
      </div>

      <div class="split">
        <div class="col">
          <section class="card">
            <div class="card-head">
              <div>
                <h3>Till counts this week</h3>
                <p class="muted small">Every till closed in the last seven days, and what it was out by</p>
              </div>
              <RouterLink to="/end-of-day">End of day</RouterLink>
            </div>
            <p v-if="data.open_tills" class="info-note">{{ data.open_tills }} till{{ data.open_tills === 1 ? ' is' : 's are' }} still open.</p>
            <p v-if="!data.tills.length" class="home-empty">No tills closed this week.</p>
            <ul class="home-list">
              <li v-for="(t, i) in data.tills" :key="i">
                <div>
                  <b>{{ t.who }}</b> <span class="muted">· {{ t.closed }}</span>
                  <p class="sub">Expected {{ kwacha(t.expected_ngwee) }}, counted {{ kwacha(t.counted_ngwee) }}</p>
                </div>
                <b class="num" :class="t.variance_ngwee < 0 ? 'bad' : t.variance_ngwee > 0 ? '' : 'good'">
                  {{ t.variance_ngwee === 0 ? 'Exact' : t.variance_ngwee > 0 ? `+${kwacha(t.variance_ngwee)}` : `−${kwacha(-t.variance_ngwee)}` }}
                </b>
              </li>
            </ul>
            <p v-if="data.tills_short_ngwee < 0" class="short">Short in total: {{ kwacha(-data.tills_short_ngwee) }}</p>
          </section>

          <section v-if="data.owed" class="card">
            <div class="card-head"><h3>Who we owe</h3><RouterLink to="/purchases">Pay suppliers</RouterLink></div>
            <p v-if="!data.owed.suppliers.length" class="home-empty">Every delivery is paid for.</p>
            <ul class="home-list">
              <li v-for="s in data.owed.suppliers" :key="s.name">
                <div>
                  <b>{{ s.name }}</b>
                  <p class="sub">Oldest {{ s.oldest_days === 0 ? 'from today' : `${s.oldest_days} day${s.oldest_days === 1 ? '' : 's'} old` }}</p>
                </div>
                <b class="num" :class="{ bad: s.oldest_days >= 30 }">{{ kwacha(s.owed_ngwee) }}</b>
              </li>
            </ul>
          </section>
        </div>

        <div class="col">
          <section class="card">
            <div class="card-head"><h3>Today by payment method</h3><RouterLink to="/payments">Payments</RouterLink></div>
            <p v-if="!data.takings.length" class="home-empty">Nothing taken yet today.</p>
            <ul class="home-list">
              <li v-for="t in data.takings" :key="t.method" class="method">
                <div>
                  <span>{{ t.label }}</span>
                  <div class="bar"><span :style="{ width: `${(t.amount_ngwee / takingsMax) * 100}%` }" /></div>
                </div>
                <b class="num">{{ kwacha(t.amount_ngwee) }}</b>
              </li>
            </ul>
          </section>

          <section v-if="data.books" class="card">
            <div class="card-head"><h3>{{ data.month_label }} in the books</h3><RouterLink to="/books">Statements</RouterLink></div>
            <ul class="home-list">
              <li><span>Income</span><b class="num">{{ kwacha(data.books.income_ngwee) }}</b></li>
              <li><span>Gross margin</span><b class="num">{{ data.books.gross_margin_percent }}%</b></li>
              <li><span>Profit</span><b class="num" :class="data.books.profit_ngwee < 0 ? 'bad' : 'good'">{{ kwacha(data.books.profit_ngwee) }}</b></li>
              <li>
                <span>Trial balance</span>
                <span class="tag" :class="data.books.balanced === false ? 'bad' : ''">{{ data.books.balanced === false ? 'Out of balance' : 'Balances' }}</span>
              </li>
            </ul>
          </section>

          <section v-if="data.payroll" class="card">
            <div class="card-head"><h3>Payroll</h3><RouterLink to="/payroll">Open</RouterLink></div>
            <p v-if="!data.payroll.latest" class="home-empty">No payroll has been run yet.</p>
            <ul v-else class="home-list">
              <li><span>{{ monthName(data.payroll.latest.period) }}</span><span class="tag" :class="data.payroll.latest.status === 'paid' ? '' : 'warn'">{{ PAYROLL[data.payroll.latest.status] ?? data.payroll.latest.status }}</span></li>
              <li><span>Paid to staff</span><b class="num">{{ kwacha(data.payroll.latest.net_ngwee) }}</b></li>
              <li><span>Cost to the business</span><b class="num">{{ kwacha(data.payroll.latest.employer_cost_ngwee) }}</b></li>
            </ul>
            <p v-if="!data.payroll.this_month" class="muted small">{{ monthName(data.payroll.period) }} has not been run yet.</p>
          </section>
        </div>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.method .bar { margin-top: .4rem; }
.short { margin: .6rem 0 0; color: var(--danger); font-weight: 700; }
.kpi-value.bad, .kpi-sub.bad { color: var(--danger); }
</style>
