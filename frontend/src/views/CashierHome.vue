<!--
  The cashier's home: my till, what I have taken, and who is waiting.

  The demo gives the cashier account "orders and collection only". A cashier
  here also runs the till, so the first thing on the screen is whether that
  till is open and what should be in the drawer, then the orders ready at the
  pass, because a name to call out is the most urgent thing at a counter.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import Icon from '../components/Icon.vue'
import { api } from '../services/api'
import { kwacha, kwachaShort } from '../services/money'
import { firstName, greeting, problemText } from '../services/home'
import { session } from '../stores/session'

interface CashierHome {
  shift: {
    id: string; opened_at: string; float_ngwee: number; orders: number
    sales_ngwee: number; cash_ngwee: number | null
    by_method: { method: string; label: string; amount_ngwee: number; count: number }[]
  } | null
  last_closed: { closed_at: string; variance_ngwee: number } | null
  my_orders: number
  my_sales_ngwee: number
  unpaid: { id: string; number: string; customer: string; total_ngwee: number }[]
  waiting: { id: string; number: string; customer: string; initials: string; items: string; at: string }[]
  preparing: number
  recent: { id: string; number: string; customer: string; items: string; at: string; total_ngwee: number; status: string }[]
  attendance: { linked: boolean; in: boolean; since: string | null; out_at: string | null } | null
}

const data = ref<CashierHome | null>(null)
const error = ref('')
const busy = ref(false)
let timer: number | undefined

async function load() {
  try {
    data.value = await api.get<CashierHome>('/home/cashier')
    error.value = ''
  } catch (problem) {
    error.value = problemText(problem, 'Could not load your till.')
  }
}

async function clock(direction: 'in' | 'out') {
  busy.value = true
  try {
    await api.post(`/people/clock-${direction}`, {})
    await load()
  } catch (problem) {
    error.value = problemText(problem, 'Could not clock you ' + direction + '.')
  } finally {
    busy.value = false
  }
}

const opened = computed(() => {
  const s = data.value?.shift
  if (!s) return ''
  return new Date(s.opened_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
})

const STATUS: Record<string, string> = { paid: 'Paid', open: 'Unpaid', cancelled: 'Cancelled' }

onMounted(() => {
  load()
  timer = window.setInterval(load, 20000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <div class="home-head">
      <div>
        <h1>{{ greeting() }}, {{ firstName(session.user.value?.name) }}</h1>
        <p class="lead">Your till and the counter, right now.</p>
      </div>
      <div class="actions">
        <RouterLink to="/orders" class="btn-outline"><Icon name="receipt" :size="18" /> Orders</RouterLink>
        <RouterLink to="/till" class="btn-primary"><Icon name="till" :size="18" /> Go to the till</RouterLink>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="data">
      <!-- clocking, when this account belongs to someone on the staff list -->
      <section v-if="data.attendance" class="card home-banner" :class="data.attendance.in ? 'good' : 'warn'">
        <span class="home-dot" :class="{ warn: !data.attendance.in }" />
        <div class="text">
          <b v-if="data.attendance.in">Clocked in since {{ data.attendance.since }}</b>
          <b v-else-if="data.attendance.out_at">Clocked out at {{ data.attendance.out_at }}</b>
          <b v-else>Not clocked in yet today</b>
          <span>Your hours go straight to payroll.</span>
        </div>
        <button v-if="data.attendance.in" class="btn-outline" :disabled="busy" @click="clock('out')">Clock out</button>
        <button v-else class="btn-primary" :disabled="busy" @click="clock('in')">Clock in</button>
      </section>

      <!-- the till -->
      <section v-if="data.shift" class="card home-banner good">
        <span class="home-dot" />
        <div class="text">
          <b>Your till is open, since {{ opened }}</b>
          <span>Float {{ kwacha(data.shift.float_ngwee) }}. At closing you count the drawer first; the system compares afterwards.</span>
        </div>
        <RouterLink to="/till" class="btn-outline">Close the till</RouterLink>
      </section>
      <section v-else class="card home-banner warn">
        <span class="home-dot warn" />
        <div class="text">
          <b>Your till is not open</b>
          <span v-if="data.last_closed">
            Last closed {{ data.last_closed.closed_at }},
            {{ data.last_closed.variance_ngwee === 0 ? 'exactly right'
              : data.last_closed.variance_ngwee > 0 ? `${kwacha(data.last_closed.variance_ngwee)} over`
              : `${kwacha(-data.last_closed.variance_ngwee)} short` }}.
          </span>
          <span v-else>Count the float into the drawer, then open the till to start selling.</span>
        </div>
        <RouterLink to="/till" class="btn-primary">Open the till</RouterLink>
      </section>

      <div class="kpis">
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="cash" :size="18" /></span><span class="kpi-label">You have taken today</span></div>
          <span class="kpi-value">{{ kwachaShort(data.my_sales_ngwee) }}</span>
          <span class="kpi-sub">{{ data.my_orders }} paid order{{ data.my_orders === 1 ? '' : 's' }}</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="bowl" :size="18" /></span><span class="kpi-label">Ready to hand over</span></div>
          <span class="kpi-value">{{ data.waiting.length }}</span>
          <span class="kpi-sub">{{ data.preparing }} still being made</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon amber"><Icon name="clock" :size="18" /></span><span class="kpi-label">Unpaid on your till</span></div>
          <span class="kpi-value">{{ data.unpaid.length }}</span>
          <span class="kpi-sub">{{ data.unpaid.length ? 'Take payment or cancel' : 'Nothing waiting' }}</span>
        </div>
        <div v-if="data.shift" class="kpi">
          <div class="kpi-top"><span class="kpi-icon brown"><Icon name="wallet" :size="18" /></span><span class="kpi-label">This till session</span></div>
          <span class="kpi-value">{{ kwachaShort(data.shift.sales_ngwee) }}</span>
          <span class="kpi-sub">{{ data.shift.orders }} order{{ data.shift.orders === 1 ? '' : 's' }} since opening</span>
        </div>
      </div>

      <div class="split">
        <div class="col">
          <section class="card">
            <div class="card-head">
              <h3>Ready at the pass</h3>
              <RouterLink to="/orders">All orders</RouterLink>
            </div>
            <p v-if="!data.waiting.length" class="home-empty">Nothing waiting. Finished orders appear here for you to call out.</p>
            <ul class="home-list">
              <li v-for="o in data.waiting" :key="o.id" class="with-icon">
                <span class="initials">{{ o.initials }}</span>
                <div>
                  <b>{{ o.number }}</b> <span class="muted">· {{ o.customer }}</span>
                  <p class="sub">{{ o.items }}</p>
                </div>
                <span class="status ready">Ready</span>
              </li>
            </ul>
          </section>

          <section class="card">
            <div class="card-head"><h3>Your latest orders</h3></div>
            <p v-if="!data.recent.length" class="home-empty">You have not rung anything up today.</p>
            <ul class="home-list">
              <li v-for="o in data.recent" :key="o.id">
                <div>
                  <b>{{ o.number }}</b> <span class="muted">· {{ o.customer }} · {{ o.at }}</span>
                  <p class="sub">{{ o.items }}</p>
                </div>
                <div class="right">
                  <b class="num">{{ kwachaShort(o.total_ngwee) }}</b>
                  <span class="status" :class="o.status === 'open' ? 'received' : o.status === 'cancelled' ? 'cancelled' : 'collected'">{{ STATUS[o.status] ?? o.status }}</span>
                </div>
              </li>
            </ul>
          </section>
        </div>

        <div class="col">
          <section v-if="data.unpaid.length" class="card">
            <div class="card-head"><h3>Waiting for payment</h3><RouterLink to="/till">Till</RouterLink></div>
            <ul class="home-list">
              <li v-for="o in data.unpaid" :key="o.id">
                <div><b>{{ o.number }}</b> <span class="muted">· {{ o.customer }}</span></div>
                <b class="num">{{ kwachaShort(o.total_ngwee) }}</b>
              </li>
            </ul>
          </section>

          <section v-if="data.shift" class="card">
            <div class="card-head"><h3>Taken on this till</h3></div>
            <p v-if="!data.shift.by_method.length" class="home-empty">No payments yet.</p>
            <ul class="home-list">
              <li v-for="m in data.shift.by_method" :key="m.method">
                <div>{{ m.label }} <span class="muted">· {{ m.count }}</span></div>
                <b class="num">{{ kwacha(m.amount_ngwee) }}</b>
              </li>
            </ul>
          </section>

          <section class="card">
            <div class="card-head"><h3>Quick links</h3></div>
            <ul class="home-list">
              <li class="with-icon"><Icon name="customers" /><RouterLink to="/customers">Customers and stamp cards</RouterLink><span /></li>
              <li class="with-icon"><Icon name="flame" /><RouterLink to="/kitchen">Kitchen display</RouterLink><span /></li>
              <li class="with-icon"><Icon name="clock" /><RouterLink to="/people">Clock in or out</RouterLink><span /></li>
            </ul>
          </section>
        </div>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.right { display: grid; justify-items: end; gap: .25rem; }
</style>
