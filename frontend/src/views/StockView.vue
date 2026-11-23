<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type StockLevel, type StockMove } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { entryUnit, fromMilli, toMilli } from '../services/quantities'
import { session } from '../stores/session'

const levels = ref<StockLevel[]>([])
const moves = ref<StockMove[]>([])
const lowOnly = ref(false)
const loading = ref(true)
const error = ref('')
const busyId = ref('')
const showMoves = ref(false)

const mayAdjust = computed(() => session.can('inventory.adjust'))

const value = computed(() => levels.value.reduce((t, r) => t + r.value_ngwee, 0))
const lowCount = computed(() => levels.value.filter((r) => r.is_low).length)
const negative = computed(() => levels.value.filter((r) => r.quantity_milli < 0))

const shown = computed(() => (lowOnly.value ? levels.value.filter((r) => r.is_low) : levels.value))

function amount(row: { quantity_milli: number; unit: string }) {
  const unit = entryUnit(row.unit)
  if (unit === 'how many') return `${row.quantity_milli / 1000}`
  return `${row.quantity_milli} ${unit}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    levels.value = await api.stockLevels()
    if (showMoves.value) moves.value = await api.stockMoves()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load stock.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function openMoves() {
  showMoves.value = !showMoves.value
  if (showMoves.value && !moves.value.length) {
    try {
      moves.value = await api.stockMoves()
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : 'Could not load the movements.'
    }
  }
}

function ask(row: StockLevel, question: string, current: string) {
  const unit = entryUnit(row.unit)
  const typed = window.prompt(`${question}\n${row.name}, in ${unit === 'how many' ? 'whole items' : unit}`, current)
  if (typed === null) return null
  const milli = toMilli(row.unit, typed.replace('-', ''))
  if (milli === null) {
    error.value = 'That is not an amount.'
    return null
  }
  return typed.trim().startsWith('-') ? -milli : milli
}

async function count(row: StockLevel) {
  const milli = ask(row, 'What is actually on the shelf?', fromMilli(row.unit, Math.max(row.quantity_milli, 0)))
  if (milli === null) return
  await run(row, () => api.countStock(row.ingredient_id, Math.abs(milli)))
}

async function waste(row: StockLevel) {
  const milli = ask(row, 'How much was thrown away?', '')
  if (milli === null) return
  await run(row, () => api.adjustStock(row.ingredient_id, -Math.abs(milli), 'waste', 'Wasted'))
}

async function addStock(row: StockLevel) {
  const milli = ask(row, 'How much is being added, outside a delivery?', '')
  if (milli === null) return
  await run(row, () => api.adjustStock(row.ingredient_id, Math.abs(milli), 'adjustment', 'Added by hand'))
}

async function reorder(row: StockLevel) {
  const milli = ask(row, 'Warn me when stock falls to:', fromMilli(row.unit, row.reorder_milli))
  if (milli === null) return
  await run(row, () => api.setReorderLevel(row.ingredient_id, Math.abs(milli)))
}

async function run(row: StockLevel, action: () => Promise<StockLevel>) {
  busyId.value = row.ingredient_id
  error.value = ''
  try {
    const saved = await action()
    levels.value = levels.value.map((r) => (r.ingredient_id === saved.ingredient_id ? saved : r))
    if (showMoves.value) moves.value = await api.stockMoves()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save that.'
    await load()
  } finally {
    busyId.value = ''
  }
}

function when(iso: string) {
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lusaka',
  })
}
</script>

<template>
  <AppShell>
    <h1>Stock</h1>
    <p class="lead">
      What is in the store room. Deliveries add to it, orders take from it through the recipes, and
      a count puts right whatever the shelves actually say.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="cards">
      <article class="card">
        <b>{{ kwacha(value) }}</b>
        <span>Stock on hand</span>
      </article>
      <article class="card" :class="{ warn: lowCount > 0 }">
        <b>{{ lowCount }}</b>
        <span>At or below reorder level</span>
      </article>
      <article class="card" :class="{ bad: negative.length > 0 }">
        <b>{{ negative.length }}</b>
        <span>Showing less than nothing</span>
      </article>
    </section>

    <p v-if="negative.length" class="notice">
      {{ negative.map((r) => r.name).join(', ') }}
      {{ negative.length === 1 ? 'has' : 'have' }} gone negative — sold more than was ever counted in.
      Count {{ negative.length === 1 ? 'it' : 'them' }} and the figure corrects itself.
    </p>

    <div class="toolbar">
      <label class="check">
        <input v-model="lowOnly" type="checkbox" />
        Only what needs ordering
      </label>
      <span class="spacer" />
      <button class="btn-quiet btn-small" @click="openMoves">
        {{ showMoves ? 'Hide movements' : 'Show movements' }}
      </button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ingredient</th>
            <th>On hand</th>
            <th>Reorder at</th>
            <th>Cost</th>
            <th>Value</th>
            <th v-if="mayAdjust"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in shown" :key="row.ingredient_id" :class="{ low: row.is_low, negative: row.quantity_milli < 0 }">
            <td>
              <b>{{ row.name }}</b>
              <small class="muted">{{ row.used_in }} recipe{{ row.used_in === 1 ? '' : 's' }}</small>
            </td>
            <td class="num">
              {{ amount(row) }}
              <small v-if="row.is_low" class="warn-text">order more</small>
            </td>
            <td class="num muted">{{ amount({ quantity_milli: row.reorder_milli, unit: row.unit }) }}</td>
            <td class="num">{{ kwacha(row.cost_ngwee) }}<small class="muted">per {{ row.unit === 'each' ? 'one' : row.unit }}</small></td>
            <td class="num">{{ kwacha(row.value_ngwee) }}</td>
            <td v-if="mayAdjust" class="actions">
              <button class="btn-quiet btn-small" :disabled="busyId === row.ingredient_id" @click="count(row)">Count</button>
              <button class="btn-quiet btn-small" :disabled="busyId === row.ingredient_id" @click="waste(row)">Waste</button>
              <button class="btn-quiet btn-small" :disabled="busyId === row.ingredient_id" @click="addStock(row)">Add</button>
              <button class="btn-quiet btn-small" :disabled="busyId === row.ingredient_id" @click="reorder(row)">Reorder at</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <template v-if="showMoves">
      <h2>Movements</h2>
      <p class="muted">Every change, newest first. Nothing here is ever edited.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>When</th><th>Ingredient</th><th>What</th><th>Amount</th><th>Left</th><th>Reference</th></tr>
          </thead>
          <tbody>
            <tr v-for="m in moves" :key="m.id">
              <td class="num">{{ when(m.at) }}</td>
              <td>{{ m.ingredient_name }}</td>
              <td><span class="tag" :class="{ off: m.quantity_milli < 0 }">{{ m.kind_label }}</span></td>
              <td class="num" :class="m.quantity_milli < 0 ? 'out' : 'in'">
                {{ m.quantity_milli > 0 ? '+' : '' }}{{ amount({ quantity_milli: m.quantity_milli, unit: m.unit }) }}
              </td>
              <td class="num muted">{{ amount({ quantity_milli: m.balance_milli, unit: m.unit }) }}</td>
              <td class="muted">{{ m.reference || m.note }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.8rem; margin-bottom: 0.9rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 0.8rem 1rem; display: grid; gap: 0.1rem; }
.card b { font-size: 1.3rem; }
.card span { font-size: 0.8rem; color: var(--muted); }
.card.warn b { color: #9a6700; }
.card.bad b { color: var(--danger); }
.toolbar { display: flex; align-items: center; gap: 0.8rem; margin: 0.9rem 0 0.7rem; }
.check { display: flex; gap: 0.4rem; align-items: center; font-size: 0.88rem; }
.check input { width: 17px; height: 17px; accent-color: var(--green-mid); }
.spacer { flex: 1; }
.num { white-space: nowrap; }
td small { display: block; font-size: 0.74rem; }
.warn-text { color: #9a6700; font-weight: 700; }
tr.low td:nth-child(2) { font-weight: 700; }
tr.negative td:nth-child(2) { color: var(--danger); font-weight: 700; }
.actions { display: flex; gap: 0.3rem; flex-wrap: wrap; min-width: 15rem; }
.in { color: var(--green-mid); }
.out { color: #8a3b00; }
</style>
