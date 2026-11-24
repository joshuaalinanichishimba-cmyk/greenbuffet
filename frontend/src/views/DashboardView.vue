<!--
  Overview: the demo's first screen, from the real orders.

  Read top to bottom it answers the questions a manager walks in with: how
  much have we taken, is it better than yesterday, what is the kitchen doing,
  how are people paying, what is selling, and what are we about to run out
  of. Everything links to the screen that deals with it.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import Icon from '../components/Icon.vue'
import Spark from '../components/Spark.vue'
import Donut from '../components/Donut.vue'
import { api } from '../services/api'
import { kwachaAxis, kwachaShort } from '../services/money'
import { stockAmount } from '../services/quantities'
import { session } from '../stores/session'
import HomeExtras from '../components/HomeExtras.vue'
import ApprovalsPanel from '../components/ApprovalsPanel.vue'

interface Overview {
  sales_ngwee: number
  sales_change: number | null
  paid_orders: number
  orders_change: number | null
  average_ngwee: number
  average_change: number | null
  in_kitchen: number
  ready: number
  spark: { sales: number[]; orders: number[]; average: number[] }
  hours: number[]
  by_hour_today: number[]
  by_hour_yesterday: number[]
  pipeline: Record<'awaiting_payment' | 'received' | 'preparing' | 'ready', number>
  mix: { mobile: number; card: number; cash: number; account: number }
  collected_ngwee: number
  latest: { id: string; number: string; customer: string; initials: string; items: string; at: string; total_ngwee: number; state: string; state_label: string }[]
  best_sellers: { name: string; sold: number }[]
  stock_alerts: { name: string; unit: string; on_hand_milli: number; reorder_milli: number }[]
  rating: { average: number | null; count: number; latest: string }
  prep_minutes: number
  wait_minutes: number
}

const data = ref<Overview | null>(null)
const error = ref('')
const canSetPrep = computed(() => session.canAny('service.control', 'settings.edit'))
let timer: number | undefined

const firstName = computed(() => (session.user.value?.name ?? '').split(/\s+/)[0] || 'there')
const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
})

async function load() {
  try {
    data.value = await api.get<Overview>('/dashboard/overview')
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load the overview.'
  }
}

async function nudgePrep(by: number) {
  if (!data.value) return
  const minutes = Math.min(120, Math.max(1, data.value.prep_minutes + by))
  try {
    await api.post('/dashboard/service/prep', { minutes })
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not change the time.'
  }
}

// ---- the sales-by-hour chart -------------------------------------------
const CW = 600
const CH = 200
const PAD = { l: 44, r: 10, t: 10, b: 24 }
const chart = computed(() => {
  const d = data.value
  if (!d) return null
  const all = [...d.by_hour_today, ...d.by_hour_yesterday]
  const top = niceMax(Math.max(...all, 1))
  const x = (i: number) => PAD.l + (i / Math.max(d.hours.length - 1, 1)) * (CW - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (1 - v / top) * (CH - PAD.t - PAD.b)
  const line = (vals: number[]) => vals.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const today = line(d.by_hour_today)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({ v: top * f, y: y(top * f) }))
  const last = d.by_hour_today.length - 1
  return {
    today,
    area: `${today} L${x(last)},${y(0)} L${x(0)},${y(0)} Z`,
    yesterday: line(d.by_hour_yesterday),
    ticks,
    labels: d.hours.map((h, i) => ({ x: x(i), text: String(h).padStart(2, '0'), show: i % 2 === 0 || i === last })),
    end: { x: x(last), y: y(d.by_hour_today[last] ?? 0) },
  }
})

function niceMax(v: number) {
  const step = Math.pow(10, Math.floor(Math.log10(v)))
  for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= v) return m * step
  return 10 * step
}

const pipelineRows = computed(() => {
  const p = data.value?.pipeline
  if (!p) return []
  const max = Math.max(1, ...Object.values(p))
  return [
    { label: 'Awaiting payment', n: p.awaiting_payment, cls: '' },
    { label: 'Received', n: p.received, cls: 'amber' },
    { label: 'Preparing', n: p.preparing, cls: '' },
    { label: 'Ready for pickup', n: p.ready, cls: 'sprout' },
  ].map((r) => ({ ...r, width: `${(r.n / max) * 100}%` }))
})

const mixRows = computed(() => {
  const m = data.value?.mix
  const total = data.value?.collected_ngwee ?? 0
  if (!m) return []
  return [
    { label: 'Mobile money', v: m.mobile, colour: 'var(--green)' },
    { label: 'Card', v: m.card, colour: 'var(--sprout)' },
    { label: 'Cash at counter', v: m.cash, colour: 'var(--brown)' },
    ...(m.account ? [{ label: 'On account', v: m.account, colour: 'var(--kraft)' }] : []),
  ].map((r) => ({ ...r, pct: total ? Math.round((r.v / total) * 100) : 0 }))
})

const bestMax = computed(() => Math.max(1, ...(data.value?.best_sellers ?? []).map((b) => b.sold)))

onMounted(() => {
  load()
  timer = window.setInterval(load, 30000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <ApprovalsPanel />
    <div class="head">
      <div>
        <h1>{{ greeting }}, {{ firstName }}</h1>
        <p class="lead">Here's how The Green Buffet is doing today.</p>
      </div>
      <div class="actions">
        <RouterLink to="/end-of-day" class="btn-outline">
          <Icon name="calendarCheck" :size="18" /> End of day
        </RouterLink>
        <RouterLink to="/kitchen" class="btn-primary">
          <Icon name="flame" :size="18" /> Kitchen display
        </RouterLink>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="data">
      <!-- the kitchen's wait, which the counter quotes to customers -->
      <section class="card service">
        <span class="live-dot" />
        <div class="service-text">
          <b>Kitchen open</b>
          <span>Customers at the counter are told “ready in about {{ data.wait_minutes }} min”</span>
        </div>
        <div class="prep">
          <span class="muted">Base prep time</span>
          <div class="stepper">
            <button :disabled="!canSetPrep" aria-label="Less time" @click="nudgePrep(-1)"><Icon name="minus" :size="16" /></button>
            <b>{{ data.prep_minutes }} min</b>
            <button :disabled="!canSetPrep" aria-label="More time" @click="nudgePrep(1)"><Icon name="plus" :size="16" /></button>
          </div>
        </div>
      </section>

      <!-- the four numbers -->
      <div class="kpis">
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="cash" :size="18" /></span><span class="kpi-label">Sales today</span></div>
          <span class="kpi-value">{{ kwachaShort(data.sales_ngwee) }}</span>
          <span v-if="data.sales_change !== null" class="delta" :class="{ down: data.sales_change < 0 }">
            <Icon :name="data.sales_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.sales_change) }}%
          </span>
          <p class="kpi-note">{{ data.sales_change === null ? 'Nothing to compare with yesterday yet' : 'vs same time yesterday' }}</p>
          <Spark :values="data.spark.sales" />
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="receipt" :size="18" /></span><span class="kpi-label">Paid orders</span></div>
          <span class="kpi-value">{{ data.paid_orders }}</span>
          <span v-if="data.orders_change !== null" class="delta" :class="{ down: data.orders_change < 0 }">
            <Icon :name="data.orders_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.orders_change) }}%
          </span>
          <p class="kpi-note">{{ data.orders_change === null ? 'Nothing to compare with yesterday yet' : 'vs same time yesterday' }}</p>
          <Spark :values="data.spark.orders" />
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon brown"><Icon name="bowl" :size="18" /></span><span class="kpi-label">Average order</span></div>
          <span class="kpi-value">{{ kwachaShort(data.average_ngwee) }}</span>
          <span v-if="data.average_change !== null" class="delta" :class="{ down: data.average_change < 0 }">
            <Icon :name="data.average_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.average_change) }}%
          </span>
          <p class="kpi-note">{{ data.average_change === null ? 'Nothing to compare with yesterday yet' : 'vs same time yesterday' }}</p>
          <Spark :values="data.spark.average" colour="var(--brown)" />
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon amber"><Icon name="clock" :size="18" /></span><span class="kpi-label">In the kitchen</span></div>
          <span class="kpi-value">{{ data.in_kitchen }}</span>
          <p class="kpi-note">{{ data.ready }} ready for pickup</p>
        </div>
      </div>

      <div class="split">
        <div class="col">
          <!-- sales by hour -->
          <section class="card">
            <div class="card-head">
              <div>
                <h3>Sales by hour</h3>
                <p class="muted small">Today against yesterday, Lusaka time</p>
              </div>
              <b class="big-green">{{ kwachaShort(data.sales_ngwee) }}</b>
            </div>
            <div class="legend">
              <span><i class="sw today" />Today</span>
              <span><i class="sw yday" />Yesterday</span>
            </div>
            <svg v-if="chart" class="hours" :viewBox="`0 0 ${CW} ${CH}`" role="img" aria-label="Sales by hour, today against yesterday">
              <defs>
                <linearGradient id="todayFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0" stop-color="var(--green)" stop-opacity=".2" />
                  <stop offset="1" stop-color="var(--green)" stop-opacity="0" />
                </linearGradient>
              </defs>
              <g v-for="t in chart.ticks" :key="t.v">
                <line :x1="PAD.l" :x2="CW - PAD.r" :y1="t.y" :y2="t.y" stroke="var(--line)" stroke-dasharray="3 4" />
                <text :x="PAD.l - 8" :y="t.y + 4" text-anchor="end" class="axis">{{ kwachaAxis(t.v) }}</text>
              </g>
              <text
                v-for="(l, i) in chart.labels"
                v-show="l.show"
                :key="l.text"
                :x="l.x"
                :y="CH - 6"
                :text-anchor="i === chart.labels.length - 1 ? 'end' : 'middle'"
                class="axis"
              >{{ l.text }}</text>
              <path :d="chart.yesterday" fill="none" stroke="var(--muted)" stroke-width="2" stroke-dasharray="5 5" opacity=".7" />
              <path :d="chart.area" fill="url(#todayFill)" />
              <path :d="chart.today" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linejoin="round" />
              <circle :cx="chart.end.x" :cy="chart.end.y" r="4" fill="var(--green)" />
            </svg>
          </section>

          <!-- latest orders -->
          <section class="card">
            <div class="card-head">
              <h3>Latest orders</h3>
              <RouterLink to="/orders">All orders</RouterLink>
            </div>
            <div v-if="!data.latest.length" class="muted">No orders yet today.</div>
            <ul class="orders">
              <li v-for="o in data.latest" :key="o.id">
                <span class="initials">{{ o.initials }}</span>
                <div class="what">
                  <b>{{ o.number }}</b> <span class="muted">· {{ o.customer }}</span>
                  <p class="muted small">{{ o.items }}</p>
                </div>
                <span class="muted when">{{ o.at }}</span>
                <b class="amount">{{ kwachaShort(o.total_ngwee) }}</b>
                <span class="status" :class="o.state">{{ o.state_label }}</span>
              </li>
            </ul>
          </section>
        </div>

        <div class="col">
          <!-- live orders -->
          <section class="card">
            <div class="card-head">
              <h3>Live orders</h3>
              <RouterLink to="/orders">Manage</RouterLink>
            </div>
            <div class="pipe">
              <div v-for="r in pipelineRows" :key="r.label" class="pipe-row">
                <span>{{ r.label }}</span>
                <div class="bar" :class="r.cls"><span :style="{ width: r.width }" /></div>
                <b>{{ r.n }}</b>
              </div>
            </div>
          </section>

          <!-- how people paid -->
          <section class="card">
            <div class="card-head"><h3>How customers paid today</h3></div>
            <div class="paid">
              <Donut
                :parts="mixRows.map((r) => ({ value: r.v, colour: r.colour }))"
                :label="kwachaShort(data.collected_ngwee)"
                sub="collected"
              />
              <ul class="mix">
                <li v-for="r in mixRows" :key="r.label">
                  <i :style="{ background: r.colour }" />
                  <span>{{ r.label }}</span>
                  <b>{{ r.pct }}%</b>
                  <span class="muted">{{ kwachaShort(r.v) }}</span>
                </li>
              </ul>
            </div>
          </section>

          <!-- best sellers -->
          <section class="card">
            <div class="card-head"><h3>Best sellers today</h3></div>
            <p v-if="!data.best_sellers.length" class="muted">Nothing sold yet today.</p>
            <ol class="best">
              <li v-for="(b, i) in data.best_sellers" :key="b.name">
                <span class="rank" :class="{ first: i === 0 }">{{ i + 1 }}</span>
                <div class="best-body">
                  <span>{{ b.name }}</span>
                  <div class="bar"><span :style="{ width: `${(b.sold / bestMax) * 100}%` }" /></div>
                </div>
                <b>{{ b.sold }}</b>
              </li>
            </ol>
          </section>

          <!-- stock alerts -->
          <section class="card alerts">
            <div class="card-head">
              <h3>Stock alerts</h3>
              <RouterLink to="/stock?tab=shopping">Shopping list</RouterLink>
            </div>
            <p v-if="!data.stock_alerts.length" class="muted">Nothing below its reorder level.</p>
            <ul>
              <li v-for="a in data.stock_alerts" :key="a.name">
                <Icon name="alert" :size="16" />
                <span>{{ a.name }}</span>
                <b>{{ stockAmount(a.unit, a.on_hand_milli) }}</b>
              </li>
            </ul>
          </section>

          <!-- rating -->
          <section class="card">
            <div class="card-head">
              <h3>Customer rating</h3>
              <RouterLink to="/feedback">Feedback</RouterLink>
            </div>
            <template v-if="data.rating.count">
              <p class="rating">
                <b>{{ data.rating.average }}</b>
                <span class="stars">★★★★★</span>
                <span class="muted">{{ data.rating.count }} ratings</span>
              </p>
              <p v-if="data.rating.latest" class="quote">“{{ data.rating.latest }}”</p>
            </template>
            <p v-else class="muted">No feedback recorded yet. Write down what customers tell you on the Feedback screen.</p>
          </section>
        </div>
      </div>
      <HomeExtras />
    </template>
    <p v-else-if="!error" class="muted">Loading today's figures…</p>
  </AppShell>
</template>

<style scoped>
.head { display: flex; gap: 1rem; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; margin-bottom: 1.2rem; }
.head .lead { margin: .3rem 0 0; }
.actions { display: flex; gap: .6rem; flex-wrap: wrap; }
.small { font-size: .875rem; }

.service { display: flex; align-items: center; gap: .9rem; flex-wrap: wrap; margin-bottom: 1rem; padding: .9rem 1.2rem; }
.live-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 4px color-mix(in srgb, var(--green) 22%, transparent); flex: none; }
.service-text { display: grid; min-width: 0; flex: 1 1 260px; }
.service-text b { font-weight: 700; }
.service-text span { color: var(--muted); font-size: .92rem; }
.prep { display: grid; gap: .2rem; justify-items: center; }
.stepper { display: flex; align-items: center; gap: .6rem; }
.stepper b { font-family: var(--display); font-weight: 800; min-width: 4.2ch; text-align: center; }
.stepper button { width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid var(--line); background: var(--paper); display: grid; place-items: center; padding: 0; color: var(--ink); }
.stepper button:hover:not([disabled]) { border-color: var(--green); }

.kpis { grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr)); }
.kpi .delta { margin-right: .4rem; }
.kpi-note { display: inline; color: var(--muted); font-size: .88rem; }

.big-green { font-family: var(--display); font-weight: 900; font-size: 1.35rem; color: var(--green-deep); }
.legend { display: flex; gap: 1rem; font-size: .85rem; font-weight: 600; margin: -.2rem 0 .4rem; }
.legend span { display: inline-flex; align-items: center; gap: .35rem; }
.sw { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.sw.today { background: var(--green); }
.sw.yday { background: var(--muted); opacity: .55; }
.hours { width: 100%; height: auto; display: block; }
.axis { font-size: 11px; fill: var(--muted); font-family: var(--body); }

.orders { list-style: none; margin: 0; padding: 0; }
.orders li { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto auto; gap: .8rem; align-items: center; padding: .7rem 0; border-bottom: 1px solid var(--line); }
.orders li:last-child { border-bottom: 0; }
.what { min-width: 0; }
.what p { margin: .1rem 0 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.when { font-variant-numeric: tabular-nums; }
.amount { font-family: var(--display); font-weight: 800; font-variant-numeric: tabular-nums; }
@media (max-width: 620px) {
  .orders li { grid-template-columns: auto minmax(0, 1fr) auto; }
  .when { display: none; }
  .orders .status { grid-column: 2 / -1; justify-self: start; }
}

.pipe { display: grid; gap: .7rem; }
.pipe-row { display: grid; grid-template-columns: minmax(0, 9.5rem) minmax(0, 1fr) 2ch; gap: .8rem; align-items: center; font-size: .95rem; }
.pipe-row b { text-align: right; font-variant-numeric: tabular-nums; }

.paid { display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; }
.mix { list-style: none; margin: 0; padding: 0; display: grid; gap: .55rem; flex: 1; min-width: 0; }
.mix li { display: grid; grid-template-columns: 10px minmax(0, 1fr) auto auto; gap: .55rem; align-items: center; font-size: .93rem; }
.mix i { width: 10px; height: 10px; border-radius: 3px; }

.best { list-style: none; margin: 0; padding: 0; display: grid; gap: .7rem; }
.best li { display: grid; grid-template-columns: 26px minmax(0, 1fr) auto; gap: .7rem; align-items: center; }
.rank { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; font-weight: 800; font-size: .82rem; background: var(--leaf-soft); color: var(--green-deep); }
.rank.first { background: var(--green); color: var(--green-ink); }
.best-body { display: grid; gap: .3rem; min-width: 0; }
.best-body span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.alerts { border-color: color-mix(in srgb, var(--danger) 30%, var(--line)); }
.alerts ul { list-style: none; margin: 0; padding: 0; display: grid; gap: .55rem; }
.alerts li { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: .6rem; align-items: center; color: var(--ink); }
.alerts li :deep(svg) { color: var(--danger); }
.alerts li b { color: var(--danger); font-variant-numeric: tabular-nums; }

.rating { display: flex; align-items: baseline; gap: .6rem; margin: 0 0 .5rem; }
.rating b { font-family: var(--display); font-weight: 900; font-size: 1.9rem; }
.stars { color: #E8A317; letter-spacing: .1em; }
.quote { font-style: italic; color: var(--muted); }
</style>
