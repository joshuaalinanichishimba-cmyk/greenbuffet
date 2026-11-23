<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, getToken, type Dashboard, type ReportData, type ReportInfo } from '../services/api'
import { kwacha } from '../services/money'

const dash = ref<Dashboard | null>(null)
const reports = ref<ReportInfo[]>([])
const open = ref<ReportData | null>(null)
const days = ref(30)
const loading = ref(true)
const error = ref('')
const downloading = ref('')

const spans = [
  { days: 1, label: 'Today' },
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
]

// The tallest bar sets the scale, so a quiet week still reads clearly.
const peak = computed(() => Math.max(1, ...(dash.value?.by_day ?? []).map((d) => d.sales_ngwee)))
const hourPeak = computed(() => Math.max(1, ...(dash.value?.by_hour ?? []).map((h) => h.sales_ngwee)))
const methodTotal = computed(() =>
  Math.max(1, (dash.value?.by_method ?? []).reduce((t, m) => t + m.amount_ngwee, 0)),
)

function shortDay(iso: string) {
  const when = new Date(iso)
  return when.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [d, r] = await Promise.all([api.dashboard(days.value), api.reportList()])
    dash.value = d
    reports.value = r
    if (open.value) await show(open.value.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the dashboard.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(days, load)

async function show(id: string) {
  error.value = ''
  try {
    open.value = await api.report(id, days.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not open that report.'
  }
}

/** Downloads go through fetch so the token travels with them. */
async function download(id: string, fmt: 'csv' | 'xlsx' | 'pdf') {
  downloading.value = `${id}-${fmt}`
  error.value = ''
  try {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
    const response = await fetch(`${base}/reports/${id}/download?fmt=${fmt}&days=${days.value}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (!response.ok) throw new ApiError(response.status, 'The file could not be made.')
    const blob = await response.blob()
    const name = (response.headers.get('Content-Disposition') ?? '').split('filename="')[1]?.replace('"', '')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = name || `${id}.${fmt}`
    link.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not download that.'
  } finally {
    downloading.value = ''
  }
}
</script>

<template>
  <AppShell>
    <div class="head">
      <div>
        <h1>Reports</h1>
        <p class="muted">How the restaurant is doing, and the files to take away.</p>
      </div>
      <div class="spans">
        <button v-for="s in spans" :key="s.days" class="span" :class="{ on: days === s.days }" @click="days = s.days">
          {{ s.label }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="dash">
      <section class="cards">
        <article class="card big">
          <b>{{ kwacha(dash.sales_ngwee) }}</b>
          <span>Taken{{ days === 1 ? ' today' : ` over ${days} days` }}</span>
        </article>
        <article class="card">
          <b>{{ dash.orders }}</b>
          <span>Orders · {{ kwacha(dash.average_order_ngwee) }} each</span>
        </article>
        <article class="card">
          <b>{{ dash.gross_margin_percent }}%</b>
          <span>Margin after food costs of {{ kwacha(dash.food_cost_ngwee) }}</span>
        </article>
        <article class="card">
          <b>{{ kwacha(dash.vat_ngwee) }}</b>
          <span>VAT collected inside prices</span>
        </article>
        <article class="card">
          <b>{{ kwacha(dash.stock_value_ngwee) }}</b>
          <span>Stock on hand<template v-if="dash.low_stock.length">, {{ dash.low_stock.length }} to reorder</template></span>
        </article>
        <article class="card">
          <b>{{ dash.kitchen_minutes ?? '—' }}<small v-if="dash.kitchen_minutes"> min</small></b>
          <span>Average time to ready · {{ dash.staff_on_now }} clocked in</span>
        </article>
      </section>

      <div class="panels">
        <section class="panel chart">
          <b>Sales by day</b>
          <ul class="bars">
            <li v-for="d in dash.by_day" :key="d.date">
              <span class="bar-wrap">
                <span class="bar" :style="{ height: `${Math.round((d.sales_ngwee / peak) * 100)}%` }"
                      :title="`${shortDay(d.date)}: ${kwacha(d.sales_ngwee)}`" />
              </span>
              <small>{{ shortDay(d.date) }}</small>
            </li>
          </ul>
        </section>

        <section class="panel">
          <b>How people paid</b>
          <ul class="methods">
            <li v-for="m in dash.by_method" :key="m.method">
              <span class="label">{{ m.label }}</span>
              <span class="track"><span class="fill" :style="{ width: `${(m.amount_ngwee / methodTotal) * 100}%` }" /></span>
              <span class="value">{{ kwacha(m.amount_ngwee) }}</span>
            </li>
            <li v-if="!dash.by_method.length" class="muted">Nothing taken yet.</li>
          </ul>

          <b class="later">Busiest hours</b>
          <ul class="methods">
            <li v-for="h in dash.by_hour" :key="h.hour">
              <span class="label">{{ String(h.hour).padStart(2, '0') }}:00</span>
              <span class="track"><span class="fill" :style="{ width: `${(h.sales_ngwee / hourPeak) * 100}%` }" /></span>
              <span class="value">{{ kwacha(h.sales_ngwee) }}</span>
            </li>
            <li v-if="!dash.by_hour.length" class="muted">No sales in this period.</li>
          </ul>
        </section>

        <section class="panel">
          <b>What sells</b>
          <table class="plain">
            <tbody>
              <tr v-for="item in dash.top_items" :key="item.name">
                <td>{{ item.name }}</td>
                <td class="num muted">{{ item.quantity }}</td>
                <td class="num">{{ kwacha(item.sales_ngwee) }}</td>
              </tr>
              <tr v-if="!dash.top_items.length"><td class="muted">Nothing sold yet.</td></tr>
            </tbody>
          </table>
        </section>
      </div>

      <h2>Take it away</h2>
      <p class="muted">Each report covers the period chosen above, except stock, payroll and the trial balance, which are as they stand now.</p>
      <ul class="reports">
        <li v-for="r in reports" :key="r.id" class="panel report">
          <button class="name" @click="show(r.id)">{{ r.name }}</button>
          <span class="formats">
            <button class="btn-quiet btn-small" :disabled="downloading === `${r.id}-pdf`" @click="download(r.id, 'pdf')">PDF</button>
            <button class="btn-quiet btn-small" :disabled="downloading === `${r.id}-xlsx`" @click="download(r.id, 'xlsx')">Excel</button>
            <button class="btn-quiet btn-small" :disabled="downloading === `${r.id}-csv`" @click="download(r.id, 'csv')">CSV</button>
          </span>
        </li>
      </ul>

      <div v-if="open" class="backdrop" @click.self="open = null">
        <section class="panel viewer">
          <header>
            <b>{{ open.name }}</b>
            <span class="row">
              <button class="btn-quiet btn-small" @click="download(open!.id, 'pdf')">PDF</button>
              <button class="btn-quiet btn-small" @click="download(open!.id, 'xlsx')">Excel</button>
              <button class="btn-quiet btn-small" @click="open = null">Close</button>
            </span>
          </header>
          <div class="table-wrap">
            <table>
              <thead><tr><th v-for="h in open.headings" :key="h">{{ h }}</th></tr></thead>
              <tbody>
                <tr v-for="(row, i) in open.rows" :key="i" :class="{ total: row[0] === 'Total' || row[1] === 'Total' || row[1] === 'Totals' }">
                  <td v-for="(cell, j) in row" :key="j" :class="{ num: j > 0 }">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!open.rows.length" class="muted">Nothing to show for this period.</p>
        </section>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
.head p { margin: 0 0 1rem; }
.spans { display: flex; gap: 0.35rem; flex-wrap: wrap; }
.span { background: #fff; border: 1px solid #cfd6cb; }
.span.on { background: var(--green); color: #fff; border-color: var(--green); }

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.8rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 0.85rem 1rem; display: grid; gap: 0.15rem; }
.card b { font-size: 1.35rem; }
.card.big b { font-size: 1.7rem; color: var(--green-mid); }
.card span { font-size: 0.78rem; color: var(--muted); }
.card small { font-size: 0.9rem; font-weight: 400; }

.panels { display: grid; gap: 0.9rem; grid-template-columns: minmax(0, 1fr); margin: 1rem 0; align-items: start; }
.panels > .panel { min-width: 0; overflow-x: auto; }
.panel > b { display: block; margin-bottom: 0.7rem; }
.later { margin-top: 1.3rem; }

.bars { list-style: none; margin: 0; padding: 0; display: flex; gap: 3px; align-items: flex-end; height: 150px; }
.bars li { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; height: 100%; min-width: 0; }
.bar-wrap { flex: 1; width: 100%; display: flex; align-items: flex-end; }
.bar { width: 100%; background: var(--green-mid); border-radius: 3px 3px 0 0; min-height: 2px; }
.bars li { min-width: 0; }
.bars small { font-size: 0.6rem; color: var(--muted); margin-top: 0.25rem; writing-mode: vertical-rl; }

.methods { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
.methods li { display: grid; grid-template-columns: 5rem 1fr auto; gap: 0.4rem; align-items: center; font-size: 0.82rem; min-width: 0; }
.label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track { background: #e7ebe4; border-radius: 999px; height: 9px; overflow: hidden; }
.fill { display: block; height: 100%; background: var(--green-mid); border-radius: 999px; }
.value { white-space: nowrap; font-variant-numeric: tabular-nums; }

.plain { border: 0; background: none; }
.plain td { border: 0; border-bottom: 1px solid var(--line); padding: 0.3rem 0.4rem 0.3rem 0; font-size: 0.88rem; }

h2 { margin-top: 1.6rem; }
.reports { list-style: none; margin: 0.8rem 0 0; padding: 0; display: grid; gap: 0.5rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.report { display: flex; justify-content: space-between; align-items: center; gap: 0.6rem; padding: 0.6rem 0.8rem; flex-wrap: wrap; min-width: 0; }
.name { background: none; border: 0; padding: 0; font-weight: 700; text-align: left; color: var(--green-mid); }
.formats { display: flex; gap: 0.25rem; }

.backdrop { position: fixed; inset: 0; background: rgba(12, 30, 16, 0.45); display: grid; place-items: center; padding: 1rem; z-index: 20; }
.viewer { max-width: 900px; width: 100%; max-height: 86vh; overflow-y: auto; }
.viewer header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.7rem; }
.row { display: flex; gap: 0.35rem; }
.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
tr.total td { font-weight: 700; border-top: 2px solid var(--line); }

@media (min-width: 900px) {
  .panels { grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr); }
}
</style>
