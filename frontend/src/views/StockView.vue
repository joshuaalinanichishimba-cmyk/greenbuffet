<!--
  Inventory, as the demo lays it out: stock levels with a bar against the
  reorder point, a shopping list worked out from those levels, and every
  movement in and out. Buying in (purchase orders and suppliers) is the
  fourth tab.

  The movements table is the truth. A level is the sum of the movements, and
  a correction is a new movement, never an edit, so the store room always has
  a history that adds up.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import SubNav from '../components/SubNav.vue'
import { ApiError, api, type StockLevel, type StockMove } from '../services/api'
import { kwacha, kwachaShort } from '../services/money'
import { entryUnit, fromMilli, stockAmount, toMilli } from '../services/quantities'
import { session } from '../stores/session'

const route = useRoute()
const tab = ref<'levels' | 'shopping' | 'moves'>(route.query.tab === 'shopping' ? 'shopping' : 'levels')

const levels = ref<StockLevel[]>([])
const moves = ref<StockMove[]>([])
const lowOnly = ref(false)
const loading = ref(true)
const error = ref('')
const note = ref('')

const mayAdjust = computed(() => session.can('inventory.adjust'))

// What is physically on the shelves. An item counted below zero holds
// nothing, not negative food, so it adds nothing to the value; the warning
// above the table is where a negative belongs.
const value = computed(() => levels.value.reduce((t, r) => t + Math.max(0, r.value_ngwee), 0))
const low = computed(() => levels.value.filter((r) => r.is_low))
const negative = computed(() => levels.value.filter((r) => r.quantity_milli < 0))
const shown = computed(() => (lowOnly.value ? low.value : levels.value))

/** How full the bar is: on hand against twice the reorder point. */
function fill(row: StockLevel) {
  const top = Math.max(row.reorder_milli * 2, row.quantity_milli, 1)
  return `${Math.max(0, Math.min(100, (row.quantity_milli / top) * 100))}%`
}
function marker(row: StockLevel) {
  const top = Math.max(row.reorder_milli * 2, row.quantity_milli, 1)
  return `${(row.reorder_milli / top) * 100}%`
}

// The shopping list: bring each low item back up to twice its reorder point,
// which is the same rule a manager would use with a pencil.
const shopping = computed(() =>
  low.value.map((r) => {
    const need = Math.max(r.reorder_milli * 2 - Math.max(r.quantity_milli, 0), 0)
    return { ...r, need_milli: need, cost: Math.round((need / 1000) * r.cost_ngwee) }
  }),
)
const shoppingTotal = computed(() => shopping.value.reduce((t, r) => t + r.cost, 0))

async function load() {
  loading.value = true
  error.value = ''
  try {
    levels.value = await api.stockLevels()
    if (tab.value === 'moves') moves.value = await api.stockMoves()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load stock.'
  } finally {
    loading.value = false
  }
}

async function pick(t: 'levels' | 'shopping' | 'moves') {
  tab.value = t
  if (t === 'moves' && !moves.value.length) {
    try {
      moves.value = await api.stockMoves()
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : 'Could not load the movements.'
    }
  }
}

// ---- adjusting one ingredient, in a sheet rather than browser prompts ----
type Kind = 'count' | 'waste' | 'add' | 'reorder'
const editing = ref<StockLevel | null>(null)
const kind = ref<Kind>('count')
const typed = ref('')
const why = ref('')
const busy = ref(false)

const kinds: { v: Kind; label: string; ask: string }[] = [
  { v: 'count', label: 'Count', ask: 'What is actually on the shelf?' },
  { v: 'waste', label: 'Waste', ask: 'How much was thrown away?' },
  { v: 'add', label: 'Add', ask: 'How much is being added, outside a delivery?' },
  { v: 'reorder', label: 'Reorder at', ask: 'Warn me when stock falls to' },
]
const asking = computed(() => kinds.find((k) => k.v === kind.value)!)

function adjust(row: StockLevel) {
  editing.value = row
  kind.value = 'count'
  typed.value = fromMilli(row.unit, Math.max(row.quantity_milli, 0))
  why.value = ''
}

function setKind(k: Kind) {
  const row = editing.value
  kind.value = k
  if (!row) return
  typed.value = k === 'count' ? fromMilli(row.unit, Math.max(row.quantity_milli, 0))
    : k === 'reorder' ? fromMilli(row.unit, row.reorder_milli) : ''
}

async function save() {
  const row = editing.value
  if (!row) return
  const milli = toMilli(row.unit, typed.value)
  if (milli === null && !(kind.value === 'count' && typed.value.trim() === '0')) {
    error.value = 'That is not an amount.'
    return
  }
  const amount = milli ?? 0
  busy.value = true
  error.value = ''
  try {
    let saved: StockLevel
    if (kind.value === 'count') saved = await api.countStock(row.ingredient_id, amount)
    else if (kind.value === 'waste') saved = await api.adjustStock(row.ingredient_id, -amount, 'waste', why.value.trim() || 'Wasted')
    else if (kind.value === 'add') saved = await api.adjustStock(row.ingredient_id, amount, 'adjustment', why.value.trim() || 'Added by hand')
    else saved = await api.setReorderLevel(row.ingredient_id, amount)
    levels.value = levels.value.map((r) => (r.ingredient_id === saved.ingredient_id ? saved : r))
    note.value = `${row.name}: saved.`
    editing.value = null
    if (tab.value === 'moves') moves.value = await api.stockMoves()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save that.'
  } finally {
    busy.value = false
  }
}

function when(iso: string) {
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lusaka',
  })
}

function unitWord(unit: string) {
  const u = entryUnit(unit)
  return u === 'how many' ? 'items' : u
}

onMounted(load)
</script>

<template>
  <AppShell>
    <PageHead title="Inventory" lead="What is in the store room. Deliveries add to it, every sale takes from it through the recipes, and a count puts right whatever the shelves actually say." />

    <div class="tabrow">
      <div class="tabs" style="margin: 0">
        <button :class="{ on: tab === 'levels' }" @click="pick('levels')">Stock levels</button>
        <button :class="{ on: tab === 'shopping' }" @click="pick('shopping')">
          Shopping list <span v-if="low.length" class="badge">{{ low.length }}</span>
        </button>
        <button :class="{ on: tab === 'moves' }" @click="pick('moves')">Movements</button>
      </div>
      <SubNav v-if="session.can('purchases.manage')" :links="[{ to: '/purchases', label: 'Buying in' }]" />
      <span class="muted value">Stock value <b>{{ kwachaShort(value) }}</b></span>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>
    <p v-if="negative.length" class="warn-note">
      {{ negative.map((r) => r.name).join(', ') }}
      {{ negative.length === 1 ? 'has' : 'have' }} gone below nothing: more was sold than was ever counted in.
      Count {{ negative.length === 1 ? 'it' : 'them' }} and the figure corrects itself.
    </p>

    <p v-if="loading" class="muted">Loading…</p>

    <!-- stock levels -->
    <template v-else-if="tab === 'levels'">
      <div class="filter">
        <label class="switch">
          <input v-model="lowOnly" type="checkbox" />
          Show low stock only
        </label>
        <span v-if="low.length" class="pill danger">{{ low.length }} below reorder level</span>
      </div>
      <div v-if="!shown.length" class="empty">Nothing to show.</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th class="num">On hand</th>
              <th class="hide-small level-col">Level</th>
              <th class="num hide-small">Reorder at</th>
              <th class="num hide-small">Unit cost</th>
              <th v-if="mayAdjust"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in shown" :key="row.ingredient_id">
              <td>
                <b :class="{ lowname: row.is_low }">{{ row.name }}</b>
                <p class="muted small">{{ row.used_in }} recipe{{ row.used_in === 1 ? '' : 's' }}</p>
              </td>
              <td class="num"><b :class="{ lowname: row.quantity_milli < 0 }">{{ stockAmount(row.unit, row.quantity_milli) }}</b></td>
              <td class="hide-small level-col">
                <div class="level">
                  <span :class="{ red: row.is_low }" :style="{ width: fill(row) }" />
                  <i v-if="row.reorder_milli" :style="{ left: marker(row) }" />
                </div>
              </td>
              <td class="num hide-small">{{ row.reorder_milli ? stockAmount(row.unit, row.reorder_milli) : '—' }}</td>
              <td class="num hide-small">{{ kwacha(row.cost_ngwee) }}</td>
              <td v-if="mayAdjust" class="act">
                <button class="btn-outline btn-small" @click="adjust(row)">Adjust</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- the shopping list -->
    <template v-else-if="tab === 'shopping'">
      <div v-if="!shopping.length" class="empty">Nothing is below its reorder level. Nothing to buy.</div>
      <template v-else>
        <p class="muted">Enough of each to bring it back to twice its reorder level, at today's cost.</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Item</th><th class="num">On hand</th><th class="num">Buy</th><th class="num">About</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in shopping" :key="r.ingredient_id">
                <td><b>{{ r.name }}</b></td>
                <td class="num lowname">{{ stockAmount(r.unit, r.quantity_milli) }}</td>
                <td class="num"><b>{{ stockAmount(r.unit, r.need_milli) }}</b></td>
                <td class="num">{{ kwacha(r.cost) }}</td>
              </tr>
              <tr class="total">
                <td colspan="3">Estimated total</td>
                <td class="num">{{ kwacha(shoppingTotal) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <RouterLink v-if="session.can('purchases.manage')" to="/purchases" class="btn-primary" style="margin-top: 1rem">
          Make a purchase order
        </RouterLink>
      </template>
    </template>

    <!-- movements -->
    <template v-else>
      <p class="muted">Every change, newest first. Nothing here is ever edited.</p>
      <div v-if="!moves.length" class="empty">No movements yet.</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr><th>When</th><th>Item</th><th>What</th><th class="num">Amount</th><th class="num hide-small">Left</th><th class="hide-small">Reference</th></tr>
          </thead>
          <tbody>
            <tr v-for="m in moves" :key="m.id">
              <td class="muted tnum">{{ when(m.at) }}</td>
              <td>{{ m.ingredient_name }}</td>
              <td><span class="pill" :class="{ neutral: m.quantity_milli < 0 }">{{ m.kind_label }}</span></td>
              <td class="num" :class="m.quantity_milli < 0 ? 'out' : 'in'">
                {{ m.quantity_milli > 0 ? '+' : '' }}{{ stockAmount(m.unit, m.quantity_milli) }}
              </td>
              <td class="num hide-small muted">{{ stockAmount(m.unit, m.balance_milli) }}</td>
              <td class="hide-small muted">{{ m.reference || m.note }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- adjust -->
    <div v-if="editing" class="sheet-back" @click.self="editing = null">
      <section class="sheet">
        <div class="sheet-head">
          <div>
            <h2>{{ editing.name }}</h2>
            <p class="muted">{{ stockAmount(editing.unit, editing.quantity_milli) }} on hand</p>
          </div>
          <button class="btn-quiet btn-small" @click="editing = null">Close</button>
        </div>
        <div class="tabs">
          <button v-for="k in kinds" :key="k.v" :class="{ on: kind === k.v }" @click="setKind(k.v)">{{ k.label }}</button>
        </div>
        <label class="field">
          {{ asking.ask }} ({{ unitWord(editing.unit) }})
          <input v-model="typed" type="number" min="0" step="any" />
        </label>
        <label v-if="kind === 'waste' || kind === 'add'" class="field" style="margin-top: .8rem">
          Why
          <input v-model="why" type="text" maxlength="200" :placeholder="kind === 'waste' ? 'Went off in the fridge' : 'Borrowed from next door'" />
        </label>
        <div class="row end" style="margin-top: 1rem">
          <button class="btn-quiet" @click="editing = null">Cancel</button>
          <button class="btn-primary" :disabled="busy" @click="save">Save</button>
        </div>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.tabrow { display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; margin-bottom: 1rem; }
.tabrow :deep(.subnav) { margin: 0; }
.value { margin-left: auto; }
.badge { display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 .35rem; border-radius: 999px; background: var(--danger); color: #fff; font-size: .72rem; margin-left: .25rem; }
.filter { display: flex; align-items: center; gap: .8rem; margin-bottom: .8rem; flex-wrap: wrap; }
.small { font-size: .82rem; margin: .1rem 0 0; }
.lowname { color: var(--danger); }
.level-col { width: 30%; }
.level { position: relative; height: 8px; border-radius: 999px; background: var(--leaf-soft); }
.level span { display: block; height: 100%; border-radius: inherit; background: var(--green); }
.level span.red { background: var(--danger); }
.level i { position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--ink); opacity: .55; }
.act { text-align: right; }
.in { color: var(--green-deep); }
.out { color: var(--kraft-ink); }
tr.total td { font-family: var(--display); font-weight: 900; border-top: 2px solid var(--ink); }
</style>
