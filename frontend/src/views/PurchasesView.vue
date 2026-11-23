<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import {
  ApiError, api,
  type MenuIngredient, type Purchase, type Supplier,
} from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { entryUnit, toMilli } from '../services/quantities'
import { session } from '../stores/session'

const suppliers = ref<Supplier[]>([])
const purchases = ref<Purchase[]>([])
const ingredients = ref<MenuIngredient[]>([])
const loading = ref(true)
const error = ref('')
const busyId = ref('')
const tab = ref<'purchases' | 'suppliers'>('purchases')

const mayBuy = computed(() => session.can('purchases.manage'))

const newSupplier = reactive({ open: false, name: '', contact: '', phone: '', saving: false })

const draft = reactive({
  open: false,
  supplier_id: '',
  invoice_number: '',
  lines: [] as { ingredient_id: string; typed: string; cost: string }[],
  saving: false,
})

const ingredientById = computed(() => new Map(ingredients.value.map((i) => [i.id, i])))

const draftTotal = computed(() =>
  draft.lines.reduce((total, line) => {
    const ingredient = ingredientById.value.get(line.ingredient_id)
    const milli = ingredient ? toMilli(ingredient.unit, line.typed) : null
    const cost = toNgwee(line.cost || '0')
    if (!ingredient || milli === null || cost === null) return total
    return total + Math.round((cost * milli) / 1000)
  }, 0),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, p, i] = await Promise.all([api.suppliers(), api.purchases(), api.ingredients()])
    suppliers.value = s
    purchases.value = p
    ingredients.value = i
    if (!draft.supplier_id) draft.supplier_id = s[0]?.id ?? ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load purchases.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function addSupplier() {
  if (newSupplier.name.trim().length < 2) {
    error.value = 'Give the supplier a name.'
    return
  }
  newSupplier.saving = true
  error.value = ''
  try {
    await api.createSupplier({
      name: newSupplier.name.trim(),
      contact: newSupplier.contact.trim(),
      phone: newSupplier.phone.trim(),
    })
    Object.assign(newSupplier, { open: false, name: '', contact: '', phone: '', saving: false })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not add the supplier.'
    newSupplier.saving = false
  }
}

function addLine() {
  const first = ingredients.value[0]
  if (first) draft.lines.push({ ingredient_id: first.id, typed: '', cost: '' })
}

function startDraft() {
  draft.open = true
  draft.invoice_number = ''
  draft.lines = []
  addLine()
}

async function saveDraft() {
  error.value = ''
  if (!draft.supplier_id) {
    error.value = 'Choose a supplier.'
    return
  }
  const lines: { ingredient_id: string; quantity_milli: number; unit_cost_ngwee: number }[] = []
  for (const line of draft.lines) {
    const ingredient = ingredientById.value.get(line.ingredient_id)
    const milli = ingredient ? toMilli(ingredient.unit, line.typed) : null
    const cost = toNgwee(line.cost || '')
    if (!ingredient || milli === null || cost === null) {
      error.value = 'Every line needs an amount and a price.'
      return
    }
    lines.push({ ingredient_id: ingredient.id, quantity_milli: milli, unit_cost_ngwee: cost })
  }
  if (!lines.length) {
    error.value = 'Add at least one line.'
    return
  }
  draft.saving = true
  try {
    await api.createPurchase({
      supplier_id: draft.supplier_id,
      invoice_number: draft.invoice_number.trim(),
      lines,
    })
    draft.open = false
    draft.lines = []
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save the purchase.'
  } finally {
    draft.saving = false
  }
}

async function receive(purchase: Purchase) {
  busyId.value = purchase.id
  error.value = ''
  try {
    await api.receivePurchase(purchase.id)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not check that delivery in.'
  } finally {
    busyId.value = ''
  }
}

async function cancel(purchase: Purchase) {
  busyId.value = purchase.id
  error.value = ''
  try {
    await api.cancelPurchase(purchase.id)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not cancel that purchase.'
  } finally {
    busyId.value = ''
  }
}

function amount(milli: number, unit: string) {
  const entry = entryUnit(unit)
  return entry === 'how many' ? `${milli / 1000}` : `${milli} ${entry}`
}

function when(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', timeZone: 'Africa/Lusaka',
  })
}
</script>

<template>
  <AppShell>
    <h1>Buying in</h1>
    <p class="lead">
      Suppliers and deliveries. A purchase is written first and checked in when the goods arrive —
      only then does stock go up, and the price on the delivery becomes the cost used for margins.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="tabs">
      <button class="tab" :class="{ on: tab === 'purchases' }" @click="tab = 'purchases'">Deliveries</button>
      <button class="tab" :class="{ on: tab === 'suppliers' }" @click="tab = 'suppliers'">Suppliers</button>
      <span class="spacer" />
      <button v-if="mayBuy && tab === 'purchases'" class="btn-primary btn-small" @click="startDraft">
        New purchase
      </button>
      <button v-if="mayBuy && tab === 'suppliers'" class="btn-primary btn-small" @click="newSupplier.open = true">
        Add a supplier
      </button>
    </div>

    <section v-if="draft.open" class="panel draft">
      <header>
        <b>New purchase</b>
        <button class="btn-quiet btn-small" @click="draft.open = false">Close</button>
      </header>
      <div class="head-grid">
        <label class="field">
          Supplier
          <select v-model="draft.supplier_id">
            <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <label class="field">
          Invoice number
          <input v-model="draft.invoice_number" type="text" placeholder="INV-8841" />
        </label>
      </div>

      <table v-if="draft.lines.length">
        <thead>
          <tr><th>Ingredient</th><th>Amount</th><th>Cost per unit</th><th>Line</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="(line, index) in draft.lines" :key="index">
            <td>
              <select v-model="line.ingredient_id">
                <option v-for="i in ingredients" :key="i.id" :value="i.id">{{ i.name }}</option>
              </select>
            </td>
            <td class="pair">
              <input v-model="line.typed" type="text" inputmode="decimal" />
              <span class="muted">{{ entryUnit(ingredientById.get(line.ingredient_id)?.unit ?? 'each') }}</span>
            </td>
            <td class="pair">
              <input v-model="line.cost" type="text" inputmode="decimal" placeholder="90.00" />
              <span class="muted">per {{ ingredientById.get(line.ingredient_id)?.unit ?? '' }}</span>
            </td>
            <td class="num muted">
              {{ kwacha(Math.round(((toNgwee(line.cost || '0') ?? 0) *
                (toMilli(ingredientById.get(line.ingredient_id)?.unit ?? 'each', line.typed) ?? 0)) / 1000)) }}
            </td>
            <td><button class="btn-quiet btn-small" @click="draft.lines.splice(index, 1)">Remove</button></td>
          </tr>
        </tbody>
      </table>

      <div class="row">
        <button class="btn-quiet btn-small" @click="addLine">Add a line</button>
        <b class="total">{{ kwacha(draftTotal) }}</b>
        <button class="btn-primary" :disabled="draft.saving" @click="saveDraft">Save the purchase</button>
      </div>
    </section>

    <section v-if="newSupplier.open" class="panel draft">
      <b>New supplier</b>
      <div class="head-grid">
        <label class="field">
          Name
          <input v-model="newSupplier.name" type="text" placeholder="Kitwe Fresh Produce" />
        </label>
        <label class="field">
          Contact
          <input v-model="newSupplier.contact" type="text" placeholder="Mr Zulu" />
        </label>
        <label class="field">
          Phone
          <input v-model="newSupplier.phone" type="text" placeholder="0977123456" />
        </label>
      </div>
      <div class="row">
        <button class="btn-primary" :disabled="newSupplier.saving" @click="addSupplier">Add</button>
        <button class="btn-quiet" @click="newSupplier.open = false">Cancel</button>
      </div>
    </section>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="tab === 'purchases'">
      <p v-if="!purchases.length" class="muted">No purchases yet.</p>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr><th>Number</th><th>Supplier</th><th>Date</th><th>Items</th><th>Total</th><th>State</th><th v-if="mayBuy"></th></tr>
          </thead>
          <tbody>
            <tr v-for="p in purchases" :key="p.id">
              <td>
                <b>{{ p.number }}</b>
                <small v-if="p.invoice_number" class="muted">{{ p.invoice_number }}</small>
              </td>
              <td>{{ p.supplier_name }}</td>
              <td class="num">{{ when(p.created_at) }}</td>
              <td class="items">
                {{ p.lines.map((l) => `${l.ingredient_name} ${amount(l.quantity_milli, l.unit)}`).join(', ') }}
              </td>
              <td class="num">{{ kwacha(p.total_ngwee) }}</td>
              <td>
                <span v-if="p.status === 'received'" class="tag">In stock</span>
                <span v-else-if="p.status === 'cancelled'" class="tag off">Cancelled</span>
                <span v-else class="tag off">Not arrived</span>
              </td>
              <td v-if="mayBuy" class="actions">
                <button
                  v-if="p.status === 'draft'"
                  class="btn-quiet btn-small"
                  :disabled="busyId === p.id"
                  @click="receive(p)"
                >
                  Check it in
                </button>
                <button
                  v-if="p.status === 'draft'"
                  class="btn-quiet btn-small"
                  :disabled="busyId === p.id"
                  @click="cancel(p)"
                >
                  Cancel
                </button>
                <small v-else-if="p.received_by" class="muted">by {{ p.received_by }}</small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else>
      <p v-if="!suppliers.length" class="muted">No suppliers yet.</p>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr><th>Supplier</th><th>Contact</th><th>Phone</th><th>Deliveries</th><th>Spent</th></tr>
          </thead>
          <tbody>
            <tr v-for="s in suppliers" :key="s.id">
              <td><b>{{ s.name }}</b><small v-if="s.note" class="muted">{{ s.note }}</small></td>
              <td>{{ s.contact || '—' }}</td>
              <td>{{ s.phone || '—' }}</td>
              <td class="num">{{ s.purchases }}</td>
              <td class="num">{{ kwacha(s.spent_ngwee) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.tabs { display: flex; gap: 0.4rem; align-items: center; margin: 1rem 0 0.9rem; }
.tab { background: #fff; border: 1px solid #cfd6cb; }
.tab.on { background: var(--green); color: #fff; border-color: var(--green); }
.spacer { flex: 1; }
.draft { margin-bottom: 1rem; }
.draft > header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.7rem; }
.head-grid { display: grid; gap: 0.7rem; grid-template-columns: 1fr; margin-bottom: 0.8rem; }
.pair { display: flex; gap: 0.4rem; align-items: center; }
.pair input { width: 6.5rem; }
.row { display: flex; gap: 0.8rem; align-items: center; flex-wrap: wrap; margin-top: 0.8rem; }
.total { margin-left: auto; font-size: 1.15rem; }
.num { white-space: nowrap; }
.items { max-width: 22rem; font-size: 0.85rem; }
td small { display: block; font-size: 0.75rem; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }

@media (min-width: 760px) {
  .head-grid { grid-template-columns: repeat(3, 1fr); }
}
</style>
