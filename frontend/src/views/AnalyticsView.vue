<!--
  Sales analytics, laid out as the demo's: the four headline numbers, daily
  sales, how people paid, when they order (a weekday-by-hour grid for staff
  rosters and prep), what sells, and which toppings go into the most bowls.

  The downloadable reports - Excel, PDF and CSV - are on the second tab.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import SubNav from '../components/SubNav.vue'
import Icon from '../components/Icon.vue'
import Spark from '../components/Spark.vue'
import Donut from '../components/Donut.vue'
import { ApiError, api } from '../services/api'
import { kwacha, kwachaAxis, kwachaShort } from '../services/money'

interface Data {
  days: number; sales_ngwee: number; paid_orders: number; per_day: number
  average_ngwee: number; lost_orders: number
  previous: {
    sales_ngwee: number; paid_orders: number; average_ngwee: number; lost_orders: number
    sales_change: number | null; orders_change: number | null
    average_change: number | null; lost_change: number | null
  }
  daily: { date: string; label: string; sales_ngwee: number }[]
  mix: { mobile: number; card: number; cash: number; account: number }
  hours: number[]; heat: number[][]; busiest: { day: string; hour: string } | null
  best_sellers: { name: string; sold: number; sales_ngwee: number }[]
  toppings: { name: string; count: number }[]
}

const days = ref(14)
const data = ref<Data | null>(null)
const error = ref('')
const hover = ref<number | null>(null)

async function load() {
  try {
    data.value = await api.get<Data>(`/dashboard/analytics?days=${days.value}`)
    error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the figures.'
  }
}

/** "vs K41,200 the 14 days before", or why there is nothing to compare. */
function comparison(field: keyof Data['previous'], before: string) {
  if (!data.value) return ''
  const change = data.value.previous[field]
  if (change === null) return `Nothing in the ${data.value.days} days before to compare`
  return `vs ${before} the ${data.value.days} days before`
}

function setDays(n: number) {
  days.value = n
  load()
}

// ---- daily sales chart --------------------------------------------------------
const W = 640
const H = 220
const P = { l: 46, r: 12, t: 12, b: 26 }
const chart = computed(() => {
  const d = data.value?.daily ?? []
  if (!d.length) return null
  const top = niceMax(Math.max(...d.map((x) => x.sales_ngwee), 1))
  const x = (i: number) => P.l + (i / Math.max(d.length - 1, 1)) * (W - P.l - P.r)
  const y = (v: number) => P.t + (1 - v / top) * (H - P.t - P.b)
  const line = d.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.sales_ngwee).toFixed(1)}`).join(' ')
  const step = Math.max(1, Math.ceil(d.length / 7))
  return {
    line,
    area: `${line} L${x(d.length - 1)},${y(0)} L${x(0)},${y(0)} Z`,
    ticks: [0, 0.25, 0.5, 0.75, 1].map((f) => ({ v: top * f, y: y(top * f) })),
    labels: d.map((p, i) => ({ x: x(i), text: p.label, show: i % step === 0 || i === d.length - 1 })),
    points: d.map((p, i) => ({ x: x(i), y: y(p.sales_ngwee), ...p })),
    width: (W - P.l - P.r) / Math.max(d.length - 1, 1),
  }
})

function niceMax(v: number) {
  const step = Math.pow(10, Math.floor(Math.log10(v)))
  for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= v) return m * step
  return 10 * step
}

const mixRows = computed(() => {
  const m = data.value?.mix
  if (!m) return []
  const total = m.mobile + m.card + m.cash + m.account
  return [
    { label: 'Mobile money', v: m.mobile, colour: 'var(--green)' },
    { label: 'Card', v: m.card, colour: 'var(--sprout)' },
    { label: 'Cash at counter', v: m.cash, colour: 'var(--brown)' },
    ...(m.account ? [{ label: 'On account', v: m.account, colour: 'var(--kraft)' }] : []),
  ].map((r) => ({ ...r, pct: total ? Math.round((r.v / total) * 100) : 0 }))
})
const mixTotal = computed(() => mixRows.value.reduce((s, r) => s + r.v, 0))

const heatMax = computed(() => Math.max(1, ...(data.value?.heat ?? []).flat()))
const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
function heatColour(n: number) {
  if (!n) return 'var(--leaf-soft)'
  const strength = 0.18 + 0.82 * (n / heatMax.value)
  return `color-mix(in srgb, var(--green) ${Math.round(strength * 100)}%, var(--leaf-soft))`
}

const bestMax = computed(() => Math.max(1, ...(data.value?.best_sellers ?? []).map((b) => b.sold)))
const topMax = computed(() => Math.max(1, ...(data.value?.toppings ?? []).map((t) => t.count)))

const sparkSales = computed(() => (data.value?.daily ?? []).map((d) => d.sales_ngwee))

onMounted(load)
</script>

<template>
  <AppShell>
    <PageHead title="Sales analytics" lead="Worked out from every paid order. Lusaka time.">
      <div class="tabs" style="margin: 0">
        <button v-for="n in [7, 14, 30, 90]" :key="n" :class="{ on: days === n }" @click="setDays(n)">{{ n }} days</button>
      </div>
    </PageHead>
    <SubNav :links="[{ to: '/reports', label: 'Analytics' }, { to: '/reports/downloads', label: 'Downloads' }]" />

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="data">
      <div class="kpis">
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="cash" :size="18" /></span><span class="kpi-label">Sales</span></div>
          <span class="kpi-value">{{ kwachaShort(data.sales_ngwee) }}</span>
          <span v-if="data.previous.sales_change !== null" class="delta" :class="{ down: data.previous.sales_change < 0 }"><Icon :name="data.previous.sales_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.previous.sales_change) }}%</span>
          <p class="kpi-note">{{ comparison('sales_change', kwachaShort(data.previous.sales_ngwee)) }}</p>
          <Spark :values="sparkSales" />
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="receipt" :size="18" /></span><span class="kpi-label">Paid orders</span></div>
          <span class="kpi-value">{{ data.paid_orders }}</span>
          <span v-if="data.previous.orders_change !== null" class="delta" :class="{ down: data.previous.orders_change < 0 }"><Icon :name="data.previous.orders_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.previous.orders_change) }}%</span>
          <p class="kpi-note">{{ data.per_day }} a day · {{ comparison('orders_change', String(data.previous.paid_orders)) }}</p>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon brown"><Icon name="bowl" :size="18" /></span><span class="kpi-label">Average order</span></div>
          <span class="kpi-value">{{ kwachaShort(data.average_ngwee) }}</span>
          <span v-if="data.previous.average_change !== null" class="delta" :class="{ down: data.previous.average_change < 0 }"><Icon :name="data.previous.average_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.previous.average_change) }}%</span>
          <p class="kpi-note">{{ comparison('average_change', kwachaShort(data.previous.average_ngwee)) }}</p>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon amber"><Icon name="alert" :size="18" /></span><span class="kpi-label">Lost orders</span></div>
          <span class="kpi-value">{{ data.lost_orders }}</span>
          <span v-if="data.previous.lost_change !== null" class="delta" :class="{ down: data.previous.lost_change > 0 }"><Icon :name="data.previous.lost_change < 0 ? 'down' : 'up'" />{{ Math.abs(data.previous.lost_change) }}%</span>
          <p class="kpi-note">Cancelled before payment · {{ data.previous.lost_orders }} the period before</p>
        </div>
      </div>

      <div class="split">
        <section class="card">
          <h3>Daily sales</h3>
          <p class="muted small">Hover a day for the figure</p>
          <svg v-if="chart" class="chart" :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="Sales by day" @mouseleave="hover = null">
            <defs>
              <linearGradient id="dailyFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stop-color="var(--green)" stop-opacity=".2" />
                <stop offset="1" stop-color="var(--green)" stop-opacity="0" />
              </linearGradient>
            </defs>
            <g v-for="t in chart.ticks" :key="t.v">
              <line :x1="P.l" :x2="W - P.r" :y1="t.y" :y2="t.y" stroke="var(--line)" stroke-dasharray="3 4" />
              <text :x="P.l - 8" :y="t.y + 4" text-anchor="end" class="axis">{{ kwachaAxis(t.v) }}</text>
            </g>
            <text
              v-for="(l, i) in chart.labels"
              v-show="l.show"
              :key="l.text"
              :x="l.x"
              :y="H - 6"
              :text-anchor="i === 0 ? 'start' : i === chart.labels.length - 1 ? 'end' : 'middle'"
              class="axis"
            >{{ l.text }}</text>
            <path :d="chart.area" fill="url(#dailyFill)" />
            <path :d="chart.line" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linejoin="round" />
            <rect
              v-for="(p, i) in chart.points"
              :key="p.date"
              :x="p.x - chart.width / 2"
              :y="P.t"
              :width="chart.width"
              :height="H - P.t - P.b"
              fill="transparent"
              @mouseenter="hover = i"
            />
            <g v-if="hover !== null && chart.points[hover]">
              <line :x1="chart.points[hover].x" :x2="chart.points[hover].x" :y1="P.t" :y2="H - P.b" stroke="var(--muted)" stroke-dasharray="2 3" />
              <circle :cx="chart.points[hover].x" :cy="chart.points[hover].y" r="4.5" fill="var(--green)" />
            </g>
          </svg>
          <p v-if="hover !== null && data.daily[hover]" class="tip">
            {{ data.daily[hover].label }}: <b>{{ kwacha(data.daily[hover].sales_ngwee) }}</b>
          </p>
        </section>

        <section class="card">
          <h3>Payment mix</h3>
          <div class="paid">
            <Donut
              :parts="mixRows.map((r) => ({ value: r.v, colour: r.colour }))"
              :label="kwachaAxis(mixTotal)"
              :sub="`${data.days} days`"
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
      </div>

      <section class="card heat-card">
        <h3>When customers order</h3>
        <p class="muted small">
          <template v-if="data.busiest">Busiest: {{ data.busiest.day }}s around {{ data.busiest.hour }}. </template>Use this for staff rosters and prep timing.
        </p>
        <div class="heat-wrap">
          <table class="heat">
            <thead>
              <tr><th></th><th v-for="h in data.hours" :key="h">{{ String(h).padStart(2, '0') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, d) in data.heat" :key="d">
                <th>{{ weekdays[d] }}</th>
                <td v-for="(n, i) in row" :key="i" :style="{ background: heatColour(n) }" :title="`${weekdays[d]} ${data.hours[i]}:00 · ${n} orders`" />
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid-2">
        <section class="card">
          <h3>Best sellers</h3>
          <p v-if="!data.best_sellers.length" class="muted">Nothing sold in this period.</p>
          <ol class="best">
            <li v-for="(b, i) in data.best_sellers" :key="b.name">
              <span class="rank" :class="{ first: i === 0 }">{{ i + 1 }}</span>
              <div class="best-body">
                <div class="spread"><span class="name">{{ b.name }}</span><span class="muted">{{ b.sold }} sold <b>{{ kwachaShort(b.sales_ngwee) }}</b></span></div>
                <div class="bar"><span :style="{ width: `${(b.sold / bestMax) * 100}%` }" /></div>
              </div>
            </li>
          </ol>
        </section>
        <section class="card">
          <h3>Most picked toppings</h3>
          <p class="muted small">Prep planning: how often each choice goes into an order.</p>
          <p v-if="!data.toppings.length" class="muted">No build-your-own choices in this period.</p>
          <div v-for="t in data.toppings" :key="t.name" class="top-row">
            <span>{{ t.name }}</span>
            <div class="bar"><span :style="{ width: `${(t.count / topMax) * 100}%` }" /></div>
            <b>{{ t.count }}</b>
          </div>
        </section>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
h3 { margin: 0; }
.small { font-size: .875rem; margin: .2rem 0 .6rem; }
.kpi .delta { margin-right: .4rem; }
.kpi-note { display: inline; }
.split { margin-bottom: 1rem; }
.chart { width: 100%; height: auto; display: block; }
.axis { font-size: 11px; fill: var(--muted); font-family: var(--body); }
.tip { margin: .3rem 0 0; font-size: .9rem; }
.paid { display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; margin-top: .8rem; }
.mix { list-style: none; margin: 0; padding: 0; display: grid; gap: .55rem; flex: 1; min-width: 0; }
.mix li { display: grid; grid-template-columns: 10px minmax(0, 1fr) auto auto; gap: .55rem; align-items: center; font-size: .93rem; }
.mix i { width: 10px; height: 10px; border-radius: 3px; }
.heat-card { margin-bottom: 1rem; }
.heat-wrap { overflow-x: auto; }
.heat { border-collapse: separate; border-spacing: 4px; width: 100%; min-width: 560px; background: transparent; }
.heat th { background: none; font-size: .78rem; color: var(--muted); font-weight: 700; text-align: center; padding: 0 .2rem; position: static; }
.heat tbody th { text-align: left; width: 3rem; }
.heat td { height: 28px; border-radius: 6px; padding: 0; border: 0; }
.heat tbody tr:hover td { background: inherit; }
.best { list-style: none; margin: .8rem 0 0; padding: 0; display: grid; gap: .75rem; }
.best li { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: .7rem; align-items: center; }
.rank { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; font-weight: 800; font-size: .82rem; background: var(--leaf-soft); color: var(--green-deep); }
.rank.first { background: var(--green); color: var(--green-ink); }
.best-body { display: grid; gap: .3rem; min-width: 0; }
.best-body .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.top-row { display: grid; grid-template-columns: minmax(0, 8rem) minmax(0, 1fr) 4ch; gap: .8rem; align-items: center; margin-top: .55rem; font-size: .93rem; }
.top-row b { text-align: right; }
</style>
