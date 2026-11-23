<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import {
  ApiError, api,
  type MenuCategory, type MenuOptionItem, type MenuProduct, type Order, type ProductOption,
  type Receipt, type Shift,
} from '../services/api'
import { fileUrl } from '../services/files'
import { kwacha, toNgwee } from '../services/money'

type CartLine = {
  product: MenuProduct
  quantity: number
  options: { group: string; item: MenuOptionItem }[]
  note: string
}

const shift = ref<Shift | null>(null)
const categories = ref<MenuCategory[]>([])
const products = ref<MenuProduct[]>([])
const cart = ref<CartLine[]>([])
const loading = ref(true)
const error = ref('')
const busy = ref(false)

const selectedCategory = ref('')
const search = ref('')
// One photograph per dish, so the tiles are recognisable at a glance.
const photos = ref<Record<string, string>>({})

// Choosing options for an item before it goes in the basket.
const building = ref<{ product: MenuProduct; chosen: Map<string, MenuOptionItem[]> } | null>(null)

const openFloat = ref('200')
const closing = reactive({ open: false, counted: '', saving: false })

const customer = reactive({ name: '', phone: '', order_type: 'takeaway', discount: '' })

const placed = ref<Order | null>(null)
const payment = reactive({ method: 'cash', amount: '', tendered: '', reference: '' })
const receipt = ref<Receipt | null>(null)

const shown = computed(() => {
  const term = search.value.trim().toLowerCase()
  return products.value.filter((p) => {
    if (!p.is_active) return false
    if (selectedCategory.value && p.category_id !== selectedCategory.value) return false
    if (!term) return true
    return p.name.toLowerCase().includes(term) || p.code.toLowerCase().includes(term)
  })
})

const subtotal = computed(() =>
  cart.value.reduce(
    (total, line) =>
      total +
      (line.product.price_ngwee + line.options.reduce((s, o) => s + o.item.price_ngwee, 0)) *
        line.quantity,
    0,
  ),
)
const discountNgwee = computed(() => Math.min(toNgwee(customer.discount || '0') ?? 0, subtotal.value))
const total = computed(() => subtotal.value - discountNgwee.value)

const owing = computed(() => placed.value?.outstanding_ngwee ?? 0)
const changeDue = computed(() => {
  if (payment.method !== 'cash') return 0
  const tendered = toNgwee(payment.tendered || '0') ?? 0
  const amount = toNgwee(payment.amount || '0') ?? 0
  return Math.max(tendered - amount, 0)
})

const methods = [
  { id: 'cash', label: 'Cash' },
  { id: 'airtel', label: 'Airtel Money' },
  { id: 'mtn', label: 'MTN MoMo' },
  { id: 'zamtel', label: 'Zamtel Kwacha' },
  { id: 'card', label: 'Card' },
  { id: 'account', label: 'On account' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, c, p] = await Promise.all([api.currentShift(), api.menuCategories(), api.menuProducts()])
    shift.value = s
    categories.value = c
    products.value = p
    loadPhotos().catch(() => undefined)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the till.'
  } finally {
    loading.value = false
  }
}
async function loadPhotos() {
  const stored = await api.storedFiles({ attached_to: 'product', kind: 'photo' })
  const primary = new Map<string, string>()
  for (const photo of stored) {
    if (!photo.attached_id) continue
    if (photo.is_primary || !primary.has(photo.attached_id)) primary.set(photo.attached_id, photo.id)
  }
  for (const [productId, photoId] of primary) {
    try {
      photos.value = { ...photos.value, [productId]: await fileUrl(photoId, true) }
    } catch {
      /* a tile without its picture still sells the dish */
    }
  }
}

onMounted(load)

async function openTill() {
  const float = toNgwee(openFloat.value || '0')
  if (float === null) {
    error.value = 'Enter the opening float as a number, for example 200.'
    return
  }
  busy.value = true
  error.value = ''
  try {
    shift.value = await api.openShift(float)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not open the till.'
  } finally {
    busy.value = false
  }
}

async function closeTill() {
  const counted = toNgwee(closing.counted || '')
  if (counted === null) {
    error.value = 'Count the drawer and enter the total, for example 1250.50.'
    return
  }
  closing.saving = true
  error.value = ''
  try {
    const closed = await api.closeShift(shift.value!.id, counted)
    shift.value = closed
    closing.open = false
    closing.counted = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not close the till.'
  } finally {
    closing.saving = false
  }
}

function choose(product: MenuProduct) {
  error.value = ''
  if (!product.is_available) {
    error.value = `${product.name} is sold out.`
    return
  }
  if (!product.option_groups.length) {
    addToCart(product, [])
    return
  }
  building.value = { product, chosen: new Map(product.option_groups.map((g) => [g.group_id, []])) }
}

function toggleOption(group: ProductOption, item: MenuOptionItem) {
  if (!building.value) return
  const current = building.value.chosen.get(group.group_id) ?? []
  const at = current.findIndex((i) => i.id === item.id)
  let next: MenuOptionItem[]
  if (at !== -1) {
    next = current.filter((i) => i.id !== item.id)
  } else if (group.max_select === 1) {
    next = [item]
  } else if (current.length >= group.max_select) {
    error.value = `At most ${group.max_select} from ${group.name}.`
    return
  } else {
    next = [...current, item]
  }
  error.value = ''
  building.value.chosen = new Map(building.value.chosen).set(group.group_id, next)
}

function isChosen(groupId: string, itemId: string) {
  return (building.value?.chosen.get(groupId) ?? []).some((i) => i.id === itemId)
}

const buildTotal = computed(() => {
  if (!building.value) return 0
  let value = building.value.product.price_ngwee
  for (const items of building.value.chosen.values()) {
    for (const item of items) value += item.price_ngwee
  }
  return value
})

const buildReady = computed(() => {
  if (!building.value) return false
  return building.value.product.option_groups.every(
    (g) => (building.value!.chosen.get(g.group_id) ?? []).length >= g.min_select,
  )
})

function confirmBuild() {
  if (!building.value || !buildReady.value) return
  const chosen: { group: string; item: MenuOptionItem }[] = []
  for (const group of building.value.product.option_groups) {
    for (const item of building.value.chosen.get(group.group_id) ?? []) {
      chosen.push({ group: group.name, item })
    }
  }
  addToCart(building.value.product, chosen)
  building.value = null
}

function addToCart(product: MenuProduct, options: { group: string; item: MenuOptionItem }[]) {
  const key = (line: CartLine) =>
    line.product.id + line.options.map((o) => o.item.id).sort().join(',') + line.note
  const candidate: CartLine = { product, quantity: 1, options, note: '' }
  const existing = cart.value.find((line) => key(line) === key(candidate))
  if (existing) existing.quantity += 1
  else cart.value.push(candidate)
}

function lineTotal(line: CartLine) {
  return (
    (line.product.price_ngwee + line.options.reduce((s, o) => s + o.item.price_ngwee, 0)) *
    line.quantity
  )
}

function clearCart() {
  cart.value = []
  customer.name = ''
  customer.phone = ''
  customer.discount = ''
  placed.value = null
  receipt.value = null
}

async function placeOrder() {
  if (!cart.value.length) return
  busy.value = true
  error.value = ''
  try {
    placed.value = await api.createOrder({
      order_type: customer.order_type,
      customer_name: customer.name.trim(),
      customer_phone: customer.phone.trim(),
      discount_ngwee: discountNgwee.value,
      lines: cart.value.map((line) => ({
        product_id: line.product.id,
        quantity: line.quantity,
        note: line.note.trim(),
        options: line.options.map((o) => ({ option_item_id: o.item.id })),
      })),
    })
    payment.amount = ((placed.value.outstanding_ngwee ?? 0) / 100).toFixed(2)
    payment.tendered = ''
    payment.reference = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not place the order.'
  } finally {
    busy.value = false
  }
}

async function pay() {
  if (!placed.value) return
  const amount = toNgwee(payment.amount || '')
  if (amount === null || amount <= 0) {
    error.value = 'Enter the amount being paid.'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const body: Record<string, unknown> = { method: payment.method, amount_ngwee: amount }
    if (payment.method === 'cash' && payment.tendered.trim()) {
      body.tendered_ngwee = toNgwee(payment.tendered)
    }
    if (payment.reference.trim()) body.reference = payment.reference.trim()
    const updated = await api.takePayment(placed.value.id, body)
    placed.value = updated
    if (updated.status === 'paid') {
      receipt.value = await api.receipt(updated.id)
      shift.value = await api.currentShift()
    } else {
      payment.amount = (updated.outstanding_ngwee / 100).toFixed(2)
      payment.tendered = ''
      payment.reference = ''
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not take the payment.'
  } finally {
    busy.value = false
  }
}

function printReceipt() {
  window.print()
}

function startNextOrder() {
  cart.value = []
  customer.name = ''
  customer.phone = ''
  customer.discount = ''
  placed.value = null
  receipt.value = null
}
</script>

<template>
  <AppShell>
    <div class="screen-only">
      <h1>Till</h1>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="loading" class="muted">Loading…</p>

      <!-- no till open yet -->
      <section v-else-if="!shift || !shift.is_open" class="panel open-till">
        <b>Open the till to start selling</b>
        <p class="muted">
          Count the float in the drawer and enter it. At the end of the shift the system works out
          what should be there and compares it with what you count.
        </p>
        <div class="row">
          <label class="field">
            Opening float
            <input v-model="openFloat" type="text" inputmode="decimal" />
          </label>
          <button class="btn-primary" :disabled="busy" @click="openTill">Open the till</button>
        </div>
        <p v-if="shift && !shift.is_open" class="muted">
          Last till closed by {{ shift.closed_by }}: expected {{ kwacha(shift.expected_ngwee ?? 0) }},
          counted {{ kwacha(shift.counted_ngwee ?? 0) }},
          {{ (shift.variance_ngwee ?? 0) === 0 ? 'exactly right' :
             (shift.variance_ngwee ?? 0) > 0 ? `${kwacha(shift.variance_ngwee ?? 0)} over` :
             `${kwacha(Math.abs(shift.variance_ngwee ?? 0))} short` }}.
        </p>
      </section>

      <template v-else>
        <section class="shift-bar panel">
          <div>
            <b>Till open</b>
            <span class="muted">
              {{ shift.opened_by }} · float {{ kwacha(shift.float_ngwee) }} ·
              {{ shift.orders }} order{{ shift.orders === 1 ? '' : 's' }} ·
              {{ kwacha(shift.sales_ngwee) }} taken
            </span>
          </div>
          <button class="btn-quiet btn-small" @click="closing.open = !closing.open">Close the till</button>
        </section>

        <div v-if="closing.open" class="panel closing">
          <b>Count the drawer</b>
          <p class="muted">
            The drawer should hold {{ kwacha(shift.float_ngwee + shift.cash_ngwee) }} —
            {{ kwacha(shift.float_ngwee) }} float and {{ kwacha(shift.cash_ngwee) }} cash taken.
          </p>
          <div class="row">
            <label class="field">
              Counted
              <input v-model="closing.counted" type="text" inputmode="decimal" placeholder="0.00" />
            </label>
            <button class="btn-primary" :disabled="closing.saving" @click="closeTill">Close the till</button>
            <button class="btn-quiet" @click="closing.open = false">Cancel</button>
          </div>
        </div>

        <!-- receipt, after payment -->
        <section v-if="receipt" class="panel done">
          <b>{{ receipt.number }} paid</b>
          <p class="muted">
            {{ kwacha(receipt.total_ngwee) }} ·
            {{ receipt.payments.filter((p) => !p.is_refund).map((p) => p.label).join(' + ') }}
            <template v-if="receipt.change_ngwee">· change {{ kwacha(receipt.change_ngwee) }}</template>
          </p>
          <div class="row">
            <button class="btn-primary" @click="printReceipt">Print the receipt</button>
            <button class="btn-quiet" @click="startNextOrder">Next order</button>
          </div>
        </section>

        <!-- payment, after the order is placed -->
        <section v-else-if="placed" class="panel paying">
          <header>
            <b>{{ placed.number }} · {{ kwacha(owing) }} to pay</b>
            <span v-if="placed.paid_ngwee" class="muted">{{ kwacha(placed.paid_ngwee) }} already paid</span>
          </header>
          <div class="methods">
            <button
              v-for="m in methods"
              :key="m.id"
              class="method"
              :class="{ on: payment.method === m.id }"
              @click="payment.method = m.id"
            >
              {{ m.label }}
            </button>
          </div>
          <div class="pay-grid">
            <label class="field">
              Amount
              <input v-model="payment.amount" type="text" inputmode="decimal" />
            </label>
            <label v-if="payment.method === 'cash'" class="field">
              Cash given
              <input v-model="payment.tendered" type="text" inputmode="decimal" placeholder="optional" />
            </label>
            <label v-if="['airtel', 'mtn', 'zamtel', 'card'].includes(payment.method)" class="field wide">
              Transaction number
              <input v-model="payment.reference" type="text" placeholder="MP26112412345" />
            </label>
            <div v-if="payment.method === 'cash' && changeDue" class="change">
              Change <b>{{ kwacha(changeDue) }}</b>
            </div>
            <button class="btn-primary" :disabled="busy" @click="pay">Take payment</button>
          </div>
          <p class="muted">
            Mobile money and card are taken on the operator's own device; the transaction number is
            recorded here so the money can be matched later.
          </p>
        </section>

        <!-- taking the order -->
        <div v-else class="till">
          <section class="menu-side">
            <div class="toolbar">
              <label class="field grow">
                Search
                <input v-model="search" type="text" placeholder="bowl, juice" />
              </label>
              <label class="field">
                Section
                <select v-model="selectedCategory">
                  <option value="">All</option>
                  <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
              </label>
            </div>
            <ul class="grid">
              <li v-for="p in shown" :key="p.id">
                <button class="tile" :class="{ out: !p.is_available, pictured: photos[p.id] }" @click="choose(p)">
                  <img v-if="photos[p.id]" :src="photos[p.id]" alt="" />
                  <b>{{ p.name }}</b>
                  <span class="price">{{ kwacha(p.price_ngwee) }}</span>
                  <small v-if="!p.is_available">Sold out</small>
                  <small v-else-if="p.option_groups.length">{{ p.option_groups.length }} choices</small>
                </button>
              </li>
            </ul>
          </section>

          <aside class="cart panel">
            <b>Order</b>
            <p v-if="!cart.length" class="muted">Tap an item to start.</p>
            <ul v-else class="lines">
              <li v-for="(line, index) in cart" :key="index">
                <div class="line-top">
                  <b>{{ line.product.name }}</b>
                  <span>{{ kwacha(lineTotal(line)) }}</span>
                </div>
                <p v-if="line.options.length" class="muted options">
                  {{ line.options.map((o) => o.item.name).join(', ') }}
                </p>
                <div class="line-actions">
                  <button class="btn-quiet btn-small" @click="line.quantity > 1 ? line.quantity-- : cart.splice(index, 1)">−</button>
                  <span>{{ line.quantity }}</span>
                  <button class="btn-quiet btn-small" @click="line.quantity++">+</button>
                  <input v-model="line.note" type="text" class="note" placeholder="no onion" />
                  <button class="btn-quiet btn-small" @click="cart.splice(index, 1)">Remove</button>
                </div>
              </li>
            </ul>

            <div class="who">
              <label class="field">
                Order
                <select v-model="customer.order_type">
                  <option value="takeaway">Takeaway</option>
                  <option value="eat_in">Eat in</option>
                  <option value="delivery">Delivery</option>
                </select>
              </label>
              <label class="field">
                Customer
                <input v-model="customer.name" type="text" placeholder="optional" />
              </label>
              <label class="field">
                Discount
                <input v-model="customer.discount" type="text" inputmode="decimal" placeholder="0.00" />
              </label>
            </div>

            <dl class="totals">
              <div><dt>Subtotal</dt><dd>{{ kwacha(subtotal) }}</dd></div>
              <div v-if="discountNgwee"><dt>Discount</dt><dd>−{{ kwacha(discountNgwee) }}</dd></div>
              <div class="grand"><dt>Total</dt><dd>{{ kwacha(total) }}</dd></div>
            </dl>

            <div class="row">
              <button class="btn-primary" :disabled="!cart.length || busy" @click="placeOrder">
                Go to payment
              </button>
              <button class="btn-quiet" :disabled="!cart.length" @click="clearCart">Clear</button>
            </div>
          </aside>
        </div>
      </template>

      <!-- choosing options -->
      <div v-if="building" class="builder-backdrop" @click.self="building = null">
        <section class="builder panel">
          <header>
            <b>{{ building.product.name }}</b>
            <button class="btn-quiet btn-small" @click="building = null">Close</button>
          </header>
          <div v-for="g in building.product.option_groups" :key="g.group_id" class="group">
            <div class="group-head">
              <b>{{ g.name }}</b>
              <span class="muted">
                {{ g.min_select === g.max_select ? `pick ${g.max_select}` : `pick ${g.min_select} to ${g.max_select}` }}
              </span>
            </div>
            <ul class="options-grid">
              <li v-for="item in g.items" :key="item.id">
                <button
                  class="option"
                  :class="{ on: isChosen(g.group_id, item.id), out: !item.is_available }"
                  :disabled="!item.is_available"
                  @click="toggleOption(g, item)"
                >
                  {{ item.name }}
                  <small v-if="item.price_ngwee">+{{ kwacha(item.price_ngwee) }}</small>
                  <small v-else-if="!item.is_available">sold out</small>
                </button>
              </li>
            </ul>
          </div>
          <footer>
            <b>{{ kwacha(buildTotal) }}</b>
            <button class="btn-primary" :disabled="!buildReady" @click="confirmBuild">Add to the order</button>
          </footer>
        </section>
      </div>
    </div>

    <!-- what the printer gets -->
    <div v-if="receipt" class="print-only receipt">
      <h2>{{ receipt.business }}</h2>
      <p>{{ receipt.address }}<br />{{ receipt.phone }}</p>
      <p>
        {{ receipt.number }}<br />
        {{ receipt.at }}<br />
        {{ receipt.order_type }}<template v-if="receipt.customer"> · {{ receipt.customer }}</template><br />
        Served by {{ receipt.served_by }}
      </p>
      <table>
        <tbody>
          <tr v-for="(line, i) in receipt.lines" :key="i">
            <td>
              {{ line.quantity }} × {{ line.name }}
              <small v-if="line.options.length"><br />{{ line.options.join(', ') }}</small>
              <small v-if="line.note"><br />{{ line.note }}</small>
            </td>
            <td class="r">{{ kwacha(line.total_ngwee, false) }}</td>
          </tr>
        </tbody>
      </table>
      <table class="sums">
        <tbody>
          <tr v-if="receipt.discount_ngwee">
            <td>Subtotal</td><td class="r">{{ kwacha(receipt.subtotal_ngwee, false) }}</td>
          </tr>
          <tr v-if="receipt.discount_ngwee">
            <td>Discount</td><td class="r">−{{ kwacha(receipt.discount_ngwee, false) }}</td>
          </tr>
          <tr class="grand"><td>TOTAL</td><td class="r">{{ kwacha(receipt.total_ngwee, false) }}</td></tr>
          <tr v-for="(p, i) in receipt.payments" :key="i">
            <td>{{ p.is_refund ? 'Refund' : p.label }}<small v-if="p.reference"><br />{{ p.reference }}</small></td>
            <td class="r">{{ kwacha(p.amount_ngwee, false) }}</td>
          </tr>
          <tr v-if="receipt.change_ngwee">
            <td>Change</td><td class="r">{{ kwacha(receipt.change_ngwee, false) }}</td>
          </tr>
          <tr><td>VAT included</td><td class="r">{{ kwacha(receipt.vat_ngwee, false) }}</td></tr>
        </tbody>
      </table>
      <p class="footer">{{ receipt.footer }}</p>
    </div>
  </AppShell>
</template>

<style scoped>
.open-till, .shift-bar, .closing, .done, .paying { margin-bottom: 1rem; }
.shift-bar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
.shift-bar span { display: block; font-size: 0.84rem; }
.row { display: flex; gap: 0.6rem; align-items: end; flex-wrap: wrap; margin-top: 0.6rem; }
.open-till p, .closing p, .done p, .paying p { margin: 0.3rem 0 0; }

.till { display: grid; gap: 1rem; grid-template-columns: 1fr; align-items: start; }
.toolbar { display: flex; gap: 0.6rem; align-items: end; margin-bottom: 0.7rem; }
.toolbar .grow { flex: 1; }
.grid { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
.tile {
  width: 100%; min-height: 84px; text-align: left; background: var(--panel);
  border: 1px solid var(--line); border-radius: 14px; padding: 0.6rem 0.7rem;
  display: grid; gap: 0.15rem; align-content: start; font-weight: 400;
}
.tile img { width: calc(100% + 1.4rem); height: 66px; object-fit: cover; margin: -0.6rem -0.7rem 0.4rem; border-radius: 13px 13px 0 0; }
.tile.pictured { padding-top: 0.6rem; }
.tile b { font-size: 0.92rem; }
.tile .price { font-weight: 700; color: var(--green-mid); }
.tile small { font-size: 0.74rem; color: var(--muted); }
.tile.out { opacity: 0.5; }

.cart { position: sticky; top: 1rem; }
.cart > b { display: block; margin-bottom: 0.5rem; }
.lines { list-style: none; margin: 0 0 0.8rem; padding: 0; display: grid; gap: 0.6rem; }
.lines li { border-bottom: 1px solid var(--line); padding-bottom: 0.5rem; }
.line-top { display: flex; justify-content: space-between; gap: 0.6rem; }
.options { margin: 0.1rem 0; font-size: 0.8rem; }
.line-actions { display: flex; gap: 0.35rem; align-items: center; margin-top: 0.3rem; }
.line-actions .note { flex: 1; min-width: 4rem; font-size: 0.82rem; padding: 0.3rem 0.45rem; }
.who { display: grid; gap: 0.5rem; grid-template-columns: 1fr 1fr; margin-bottom: 0.7rem; }
.who .field:first-child { grid-column: span 2; }
.totals { margin: 0; display: grid; gap: 0.2rem; }
.totals > div { display: flex; justify-content: space-between; }
.totals dt, .totals dd { margin: 0; font-size: 0.9rem; }
.totals .grand dt, .totals .grand dd { font-weight: 800; font-size: 1.1rem; }

.methods { display: flex; gap: 0.4rem; flex-wrap: wrap; margin: 0.7rem 0; }
.method { background: #fff; border: 1px solid #cfd6cb; }
.method.on { background: var(--green-mid); color: #fff; border-color: var(--green-mid); }
.pay-grid { display: flex; gap: 0.7rem; align-items: end; flex-wrap: wrap; }
.pay-grid .wide { min-width: 14rem; }
.change { padding-bottom: 0.4rem; font-size: 0.95rem; }
.paying header { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }

.builder-backdrop {
  position: fixed; inset: 0; background: rgba(12, 30, 16, 0.45);
  display: grid; place-items: center; padding: 1rem; z-index: 20;
}
.builder { max-width: 560px; width: 100%; max-height: 86vh; overflow-y: auto; }
.builder > header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
.group { border-top: 1px solid var(--line); padding-top: 0.6rem; margin-top: 0.6rem; }
.group-head { display: flex; justify-content: space-between; align-items: baseline; gap: 0.6rem; }
.group-head span { font-size: 0.8rem; }
.options-grid { list-style: none; margin: 0.5rem 0 0; padding: 0; display: grid; gap: 0.4rem; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
.option { width: 100%; background: #fff; border: 1px solid #cfd6cb; text-align: left; font-weight: 400; }
.option.on { background: #e8f5e3; border-color: var(--green-mid); font-weight: 700; }
.option.out { opacity: 0.45; }
.option small { display: block; font-size: 0.74rem; color: var(--muted); }
.builder > footer { display: flex; justify-content: space-between; align-items: center; margin-top: 1rem; }
.builder > footer b { font-size: 1.2rem; }

.print-only { display: none; }

@media (min-width: 960px) {
  .till { grid-template-columns: 1fr 340px; }
}

@media print {
  .screen-only { display: none !important; }
  .print-only { display: block; font-family: 'Courier New', monospace; width: 72mm; color: #000; }
  .receipt h2 { text-align: center; margin: 0 0 0.3rem; font-size: 1.1rem; }
  .receipt p { margin: 0.3rem 0; font-size: 0.78rem; text-align: center; }
  .receipt table { width: 100%; border-collapse: collapse; font-size: 0.78rem; margin-top: 0.4rem; }
  .receipt td { padding: 0.12rem 0; vertical-align: top; border: 0; }
  .receipt .r { text-align: right; white-space: nowrap; }
  .receipt .sums { border-top: 1px dashed #000; margin-top: 0.4rem; padding-top: 0.3rem; }
  .receipt .grand td { font-weight: 700; font-size: 0.92rem; padding-top: 0.2rem; }
  .receipt small { font-size: 0.68rem; }
  .receipt .footer { margin-top: 0.6rem; border-top: 1px dashed #000; padding-top: 0.3rem; }
}
</style>
