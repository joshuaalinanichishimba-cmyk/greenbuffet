<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import AppShell from '../components/AppShell.vue'
import {
  ApiError, api,
  type MenuCategory, type MenuOptionItem, type MenuProduct, type Order, type ProductOption,
  type Receipt, type Shift,
} from '../services/api'
import { fileUrl } from '../services/files'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'
import ManagerApproval from '../components/ManagerApproval.vue'
import {
  keepMenu, keepReady, keepReceiptHeader, keptMenu, keptReady, keptReceiptHeader, reachable, sent,
  setAside, syncNow, takeOfflineSale, tryAgain, waiting, type OfflineSale,
} from '../services/offline'

type CartLine = {
  product: MenuProduct
  quantity: number
  // price is what the pick costs on this line: its own price, plus the
  // group's extra charge when it is beyond the included number.
  options: { group: string; item: MenuOptionItem; price: number }[]
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
const closing = reactive({ open: false, counted: '', note: '', saving: false, needsNote: false })

const customer = reactive({ name: '', phone: '', order_type: 'takeaway', discount: '', discountReason: '' })

const placed = ref<Order | null>(null)
const payment = reactive({ method: 'cash', amount: '', tendered: '', reference: '', confirmed: false })

// ---- a manager's approval on the spot -------------------------------------
// When the server says something needs a manager, the approval box opens and
// the same request is sent again with the manager's details.
const approval = reactive<{ what: string; error: string; retry: ((a: { email: string; password: string }) => Promise<void>) | null }>({
  what: '', error: '', retry: null,
})
function needsManager(e: unknown) {
  return e instanceof ApiError && /approv/i.test(e.message) && e.status === 403
}
async function approveWith(a: { email: string; password: string }) {
  if (!approval.retry) return
  approval.error = ''
  try {
    await approval.retry(a)
    approval.retry = null
  } catch (e) {
    approval.error = e instanceof ApiError ? e.message : 'Not approved.'
  }
}

// ---- cash moved in or out of the drawer -----------------------------------
const cashMove = reactive({ open: false, kind: 'drop', amount: '', reason: '', saving: false, done: '' })
async function moveCash() {
  const amount = toNgwee(cashMove.amount || '')
  if (amount === null || amount <= 0 || cashMove.reason.trim().length < 3) {
    error.value = 'Enter the amount and what it was for.'
    return
  }
  cashMove.saving = true
  error.value = ''
  try {
    await api.post('/sales/cash', { kind: cashMove.kind, amount_ngwee: amount, reason: cashMove.reason.trim() })
    cashMove.done = `${kwacha(amount)} recorded. A manager confirms it.`
    cashMove.amount = ''
    cashMove.reason = ''
    cashMove.open = false
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not record that.'
  } finally {
    cashMove.saving = false
  }
}

// ---- orders taken but not yet paid ----------------------------------------
const held = ref<Order[]>([])
async function loadHeld() {
  try {
    const open = await api.get<Order[]>('/sales/orders?status=open')
    held.value = open.filter((o) => o.created_by === shift.value?.opened_by)
  } catch {
    held.value = []
  }
}
function recall(o: Order) {
  placed.value = o
  payment.amount = (o.outstanding_ngwee / 100).toFixed(2)
  payment.tendered = ''
  payment.reference = ''
  payment.confirmed = false
}
// Put an unpaid order back into the basket to change it; placing it again
// changes the same order rather than making a new one.
const changing = ref<Order | null>(null)
function change(o: Order) {
  const lines: CartLine[] = []
  for (const l of o.lines) {
    const product = products.value.find((p) => p.id === l.product_id)
    if (!product) {
      error.value = `${l.product_name} is no longer on the menu, so this order cannot be changed. Cancel it instead.`
      return
    }
    const options = l.options.map((opt) => {
      for (const g of product.option_groups) {
        const item = g.items.find((i) => i.id === opt.option_item_id)
        if (item) return { group: g.name, item, price: opt.price_ngwee }
      }
      return null
    }).filter((x): x is { group: string; item: MenuOptionItem; price: number } => x !== null)
    lines.push({ product, quantity: l.quantity, options, note: l.note })
  }
  cart.value = lines
  customer.name = o.customer_name
  customer.phone = o.customer_phone
  customer.order_type = o.order_type
  changing.value = o
  placed.value = null
}
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
      (line.product.price_ngwee + line.options.reduce((s, o) => s + o.price, 0)) *
        line.quantity,
    0,
  ),
)
const discountNgwee = computed(() => Math.min(toNgwee(customer.discount || '0') ?? 0, subtotal.value))

// Loyalty at the counter, as the demo has it: a stamp card. A phone number
// finds the customer and shows their card. A full card makes the cheapest
// bowl or burrito free, and the server takes it off when the order is made;
// nobody has to remember to press anything.
const known = ref<{ id: string; name: string; stamps: number; stamps_needed: number; free_ready: boolean } | null>(null)

// Only look again when the number has changed. Leaving the box is also what
// happens when the cashier clicks "Go to payment", and clearing the card here
// would move that button between mouse-down and mouse-up and lose the click.
let lookedUp = ''
async function lookUpCustomer() {
  const digits = customer.phone.replace(/\D/g, '')
  if (digits === lookedUp) return
  lookedUp = digits
  known.value = null
  if (digits.length < 9) return
  try {
    known.value = await api.get(`/customers/by-phone/${encodeURIComponent(customer.phone.trim())}`)
  } catch {
    // Not a customer yet. They become one when this order is paid for.
  }
}

// A promotion code. The till asks the server what it is worth so the
// cashier can tell the customer before taking money; the server works it
// out again when the order is made, which is the figure that counts.
const promo = reactive({ code: '', off: 0, message: '' })
let checkedCode = ''
let checkedFood = -1
async function checkPromo() {
  const code = promo.code.trim()
  const foodNow = Math.max(0, subtotal.value - discountNgwee.value)
  // The same rule as the phone box: nothing changed, nothing to redraw.
  if (code.toUpperCase() === checkedCode && foodNow === checkedFood) return
  checkedCode = code.toUpperCase()
  checkedFood = foodNow
  promo.off = 0
  promo.message = ''
  if (!code) return
  try {
    const food = Math.max(0, subtotal.value - discountNgwee.value)
    const result = await api.get<{ code: string; discount_ngwee: number }>(
      `/dashboard/promotions/check/${encodeURIComponent(code)}?food_ngwee=${food}`,
    )
    promo.off = result.discount_ngwee
    promo.message = `${result.code}: ${kwacha(result.discount_ngwee)} off`
  } catch (e) {
    promo.message = e instanceof ApiError ? e.message : 'That code could not be checked.'
  }
}

const total = computed(() => Math.max(0, subtotal.value - discountNgwee.value - promo.off))

// A code checked against one basket says nothing about a bigger one: check
// it again whenever the food total moves. The server works it out once more
// when the order is made, so this only keeps the screen truthful.
watch(subtotal, () => {
  if (promo.code.trim()) checkPromo()
})

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
    offline.value = false
    loadPhotos().catch(() => undefined)
    // Kept on this device for the moment the network drops.
    keepMenu(c, p)
    api.get<{ shift_id: string | null; user_id: string; user_name: string }>('/sales/offline/ready')
      .then((r) => keepReady(r)).catch(() => undefined)
  } catch (e) {
    if (e instanceof ApiError && e.status === 0 && (await startOfflineTill())) return
    error.value = e instanceof ApiError ? e.message : 'Could not load the till.'
  } finally {
    loading.value = false
  }
}
// ---- selling with the server out of reach ---------------------------------
// The menu and this person's open till come from the last time the till
// loaded. Cash only, at the prices on screen; no discounts, codes or stamp
// cards, because the server decides those. Each sale is saved on this device
// first and sent when the server answers.
const offline = ref(false)
const offlinePay = reactive({ open: false, tendered: '', saving: false })
const offlineReceipt = ref<OfflineSale | null>(null)

async function startOfflineTill(): Promise<boolean> {
  const me = session.user.value
  if (!me) return false
  const [menu, ready] = await Promise.all([keptMenu(), keptReady(me.id)])
  if (!menu || !ready?.shift_id) {
    error.value = !menu
      ? 'No connection to the server, and this device has not loaded the menu before. Cash sales offline need the till to have opened once with the network up.'
      : 'No connection to the server, and your till was not open when it was last reached. Open the till once the connection is back.'
    return false
  }
  offline.value = true
  categories.value = menu.categories
  products.value = menu.products
  shift.value = {
    id: ready.shift_id, opened_by: me.name, opened_at: '', float_ngwee: 0, closed_at: null, closed_by: null,
    expected_ngwee: null, counted_ngwee: null, variance_ngwee: null, note: '', is_open: true, orders: 0,
    sales_ngwee: 0, cash_ngwee: null, by_method: [],
  }
  menuKeptAt.value = menu.at
  return true
}
const menuKeptAt = ref('')

// When the server answers again, the till goes back to normal by itself,
// unless a sale is half way through.
watch(reachable, async (ok) => {
  if (ok && offline.value && !offlinePay.open && !offlineReceipt.value && !cart.value.length) await load()
})

const myProblems = computed(() => waiting.value.filter((s) => s.state === 'problem' && (s.user_id === session.user.value?.id || session.can('cash.approve'))))
const myWaiting = computed(() => waiting.value.filter((s) => s.state === 'waiting' && s.user_id === session.user.value?.id))
const recentlySent = computed(() => sent.value.filter((s) => s.notes.length).slice(0, 5))

function goOfflinePay() {
  if (!cart.value.length) return
  if (discountNgwee.value || promo.code.trim() || customer.phone.trim()) {
    error.value = 'Offline, the till takes cash at menu prices only. Clear the discount, promotion code and phone number, or wait for the connection.'
    return
  }
  error.value = ''
  offlinePay.tendered = ''
  offlinePay.open = true
}

const offlineChange = computed(() => {
  const given = toNgwee(offlinePay.tendered || '0') ?? 0
  return Math.max(given - total.value, 0)
})

async function takeOfflineCash() {
  const given = offlinePay.tendered.trim() ? toNgwee(offlinePay.tendered) : null
  if (given !== null && given < total.value) {
    error.value = 'The cash given is less than the total.'
    return
  }
  const me = session.user.value
  if (!me || !shift.value) return
  offlinePay.saving = true
  error.value = ''
  try {
    const saved = await takeOfflineSale({
      user_id: me.id, user_name: me.name, shift_id: shift.value.id,
      order_type: customer.order_type, customer_name: customer.name.trim(), note: '',
      charged_ngwee: total.value, tendered_ngwee: given,
      lines: cart.value.map((line) => ({
        product_id: line.product.id, quantity: line.quantity, note: line.note.trim(),
        options: line.options.map((o) => ({ option_item_id: o.item.id })),
        name: line.product.name, option_names: line.options.map((o) => o.item.name), total_ngwee: lineTotal(line),
      })),
    })
    offlineReceipt.value = saved
    offlinePay.open = false
    const header = await keptReceiptHeader()
    receipt.value = {
      business: header?.business || 'The Green Buffet', address: header?.address || '', phone: header?.phone || '',
      tpin: header?.tpin || '', number: `${saved.receipt_number} (offline)`,
      at: new Date(saved.taken_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
      served_by: me.name, order_type: saved.order_type.replace('_', ' '), customer: saved.customer_name, status: 'paid',
      lines: saved.lines.map((l) => ({ name: l.name, quantity: l.quantity, each_ngwee: Math.round(l.total_ngwee / l.quantity), total_ngwee: l.total_ngwee, options: l.option_names, note: l.note })),
      subtotal_ngwee: saved.charged_ngwee, discount_ngwee: 0, total_ngwee: saved.charged_ngwee, vat_ngwee: 0,
      payments: [{ label: 'Cash', amount_ngwee: given ?? saved.charged_ngwee, reference: '', is_refund: false }],
      change_ngwee: given !== null ? given - saved.charged_ngwee : 0,
      footer: 'Taken while the till was offline. Your order number follows when the system reconnects. ' + (header?.footer || ''),
    }
  } catch {
    error.value = 'This device could not save the sale, so it was not taken. Do not hand over the food; try again.'
  } finally {
    offlinePay.saving = false
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

// ---- the basket survives a lock or a change of person ----------------------
// On a shared counter computer someone may lock the screen or hand over
// mid-order. Each person's unfinished basket is kept on this computer under
// their own account and comes back when they sign in again. It is only a
// draft: nothing reaches the server until the order is placed, so nothing can
// be charged twice or appear under the wrong name.
const draftKey = () => `gb-till-draft-${session.user.value?.id ?? ''}`
function saveDraft() {
  try {
    if (!cart.value.length) localStorage.removeItem(draftKey())
    else localStorage.setItem(draftKey(), JSON.stringify({ cart: cart.value, customer: { ...customer }, at: Date.now() }))
  } catch {
    /* storage full or blocked: the basket simply is not kept */
  }
}
function restoreDraft() {
  try {
    const raw = localStorage.getItem(draftKey())
    if (!raw || cart.value.length) return
    const draft = JSON.parse(raw) as { cart: CartLine[]; customer: typeof customer; at: number }
    // A basket from another day is stale: prices and stock may have moved on.
    if (Date.now() - draft.at > 12 * 3600_000) {
      localStorage.removeItem(draftKey())
      return
    }
    cart.value = draft.cart
    Object.assign(customer, draft.customer)
  } catch {
    /* unreadable draft: start clean */
  }
}
watch([cart, () => ({ ...customer })], saveDraft, { deep: true })

onMounted(async () => {
  await load()
  await loadHeld()
  restoreDraft()
})

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
    const closed = await api.closeShift(shift.value!.id, counted, closing.note.trim())
    shift.value = closed
    closing.open = false
    closing.counted = ''
    closing.note = ''
    closing.needsNote = false
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not close the till.'
    // Out by more than the limit: the reason box opens and the same count
    // is sent again with it.
    if (e instanceof ApiError && e.status === 409 && /note/.test(e.message)) closing.needsNote = true
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

// The picks priced as the server will price them: in a group with an
// "N included" rule, every pick after the first N carries the extra charge.
function pricedPicks(product: MenuProduct, chosen: Map<string, MenuOptionItem[]>) {
  const out: { group: string; item: MenuOptionItem; price: number }[] = []
  for (const group of product.option_groups) {
    ;(chosen.get(group.group_id) ?? []).forEach((item, index) => {
      const extra = group.free_count && index >= group.free_count ? group.extra_ngwee ?? 0 : 0
      out.push({ group: group.name, item, price: item.price_ngwee + extra })
    })
  }
  return out
}

function groupRule(g: ProductOption) {
  const pick = g.min_select === g.max_select ? `pick ${g.max_select}` : `pick ${g.min_select} to ${g.max_select}`
  return g.free_count ? `${pick} · ${g.free_count} included, then +${kwacha(g.extra_ngwee ?? 0)} each` : pick
}

function overIncluded(g: ProductOption) {
  const n = (building.value?.chosen.get(g.group_id) ?? []).length
  return g.free_count ? Math.max(0, n - g.free_count) : 0
}

const buildTotal = computed(() => {
  if (!building.value) return 0
  return pricedPicks(building.value.product, building.value.chosen)
    .reduce((sum, pick) => sum + pick.price, building.value.product.price_ngwee)
})

const buildReady = computed(() => {
  if (!building.value) return false
  return building.value.product.option_groups.every(
    (g) => (building.value!.chosen.get(g.group_id) ?? []).length >= g.min_select,
  )
})

function confirmBuild() {
  if (!building.value || !buildReady.value) return
  addToCart(building.value.product, pricedPicks(building.value.product, building.value.chosen))
  building.value = null
}

function addToCart(product: MenuProduct, options: { group: string; item: MenuOptionItem; price: number }[]) {
  const key = (line: CartLine) =>
    line.product.id + line.options.map((o) => o.item.id).sort().join(',') + line.note
  const candidate: CartLine = { product, quantity: 1, options, note: '' }
  const existing = cart.value.find((line) => key(line) === key(candidate))
  if (existing) existing.quantity += 1
  else cart.value.push(candidate)
}

function lineTotal(line: CartLine) {
  return (
    (line.product.price_ngwee + line.options.reduce((s, o) => s + o.price, 0)) *
    line.quantity
  )
}

function clearCart() {
  cart.value = []
  customer.name = ''
  customer.phone = ''
  customer.discount = ''
  customer.phone = ''
  known.value = null
  promo.code = ''
  promo.off = 0
  promo.message = ''
  lookedUp = ''
  checkedCode = ''
  checkedFood = -1
  placed.value = null
  receipt.value = null
}

async function placeOrder(approvedBy?: { email: string; password: string }) {
  if (!cart.value.length) return
  if (offline.value && reachable.value) await load()
  if (offline.value) {
    goOfflinePay()
    return
  }
  if (discountNgwee.value > 0 && customer.discountReason.trim().length < 2) {
    error.value = 'Say why the discount is given.'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const body = {
      order_type: customer.order_type,
      customer_name: customer.name.trim(),
      customer_phone: customer.phone.trim(),
      discount_ngwee: discountNgwee.value,
      // Whatever is in the box goes to the server, even if the preview has
      // not come back yet. The server decides what the code is worth, and a
      // code it will not accept stops the order with the reason on screen,
      // so a typed code can never be silently dropped.
      promo_code: promo.code.trim(),
      lines: cart.value.map((line) => ({
        product_id: line.product.id,
        quantity: line.quantity,
        note: line.note.trim(),
        options: line.options.map((o) => ({ option_item_id: o.item.id })),
      })),
      discount_reason: customer.discountReason.trim(),
      approval: approvedBy ?? null,
    }
    placed.value = changing.value
      ? await api.put<Order>(`/sales/orders/${changing.value.id}`, body)
      : await api.createOrder(body)
    changing.value = null
    payment.confirmed = false
    payment.amount = ((placed.value.outstanding_ngwee ?? 0) / 100).toFixed(2)
    payment.tendered = ''
    payment.reference = ''
  } catch (e) {
    if (needsManager(e) && !approvedBy) {
      approval.what = (e as ApiError).message
      approval.error = ''
      approval.retry = async (a) => {
        await placeOrder(a)
        if (error.value) throw new ApiError(403, error.value)
      }
    } else if (approvedBy) {
      error.value = e instanceof ApiError ? e.message : 'Could not place the order.'
    } else if (e instanceof ApiError && e.status === 0 && !changing.value && (await startOfflineTill())) {
      // The network dropped just now. Nothing reached the server, so the
      // same basket goes through as an offline cash sale.
      goOfflinePay()
    } else {
      error.value = e instanceof ApiError ? e.message : 'Could not place the order.'
    }
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
    if (payment.confirmed) body.confirmed = true
    const updated = await api.takePayment(placed.value.id, body)
    placed.value = updated
    if (updated.status === 'paid') {
      receipt.value = await api.receipt(updated.id)
      keepReceiptHeader(receipt.value)
      shift.value = await api.currentShift()
    } else {
      payment.amount = (updated.outstanding_ngwee / 100).toFixed(2)
      payment.tendered = ''
      payment.reference = ''
      payment.confirmed = false
    }
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 0
      ? 'The connection dropped while the payment was being sent, so it may or may not have been recorded. Keep the money aside and press Take payment again once the connection is back: it will not be recorded twice, and the order shows as paid if it already went through.'
      : e instanceof ApiError ? e.message : 'Could not take the payment.'
  } finally {
    busy.value = false
  }
}

function printReceipt() {
  window.print()
}

function startNextOrder() {
  loadHeld()
  cart.value = []
  customer.name = ''
  customer.phone = ''
  customer.discount = ''
  customer.phone = ''
  known.value = null
  promo.code = ''
  promo.off = 0
  promo.message = ''
  lookedUp = ''
  checkedCode = ''
  checkedFood = -1
  placed.value = null
  receipt.value = null
  offlineReceipt.value = null
  // Back online since that sale: the till returns to normal now.
  if (offline.value && reachable.value) load()
}
</script>

<template>
  <AppShell>
    <div class="screen-only">
      <h1>Till</h1>
      <p v-if="offline" class="notice offline-note">
        <b>Offline.</b> Cash sales only, at the menu prices from
        {{ menuKeptAt ? new Date(menuKeptAt).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'the last load' }}.
        Each sale is saved on this device and sent as soon as the server answers.
        No discounts, promotion codes or stamp cards until then.
      </p>
      <p v-if="error" class="error">{{ error }}</p>

      <section v-if="myProblems.length" class="panel problems">
        <b>Offline sales the server could not take</b>
        <p class="muted">The cash is in the drawer. A manager enters each one by hand, then sets it aside here.</p>
        <ul>
          <li v-for="s in myProblems" :key="s.id">
            <span>
              <b>{{ s.receipt_number }}</b> · {{ s.user_name }} · {{ kwacha(s.charged_ngwee) }} ·
              {{ new Date(s.taken_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) }}
              <br /><span class="muted">{{ s.lines.map((l) => `${l.quantity} × ${l.name}`).join(', ') }}</span>
              <br /><span class="warn-note">{{ s.problem }}</span>
            </span>
            <span class="row">
              <button class="btn-quiet btn-small" @click="tryAgain(s.id)">Try again</button>
              <button v-if="session.can('cash.approve')" class="btn-quiet btn-small" @click="setAside(s.id)">Entered by hand, set aside</button>
            </span>
          </li>
        </ul>
      </section>
      <section v-if="recentlySent.length && !offline" class="panel problems">
        <b>Offline sales sent, with something to check</b>
        <ul>
          <li v-for="s in recentlySent" :key="s.id">
            <span><b>{{ s.receipt_number }}</b> is now <b>{{ s.order_number }}</b><br /><span class="muted">{{ s.notes.join(' ') }}</span></span>
          </li>
        </ul>
      </section>
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
            <span v-if="offline" class="muted">
              {{ shift.opened_by }} · {{ myWaiting.length }} offline sale{{ myWaiting.length === 1 ? '' : 's' }} waiting to send
            </span>
            <span v-else class="muted">
              {{ shift.opened_by }} · float {{ kwacha(shift.float_ngwee) }} ·
              {{ shift.orders }} order{{ shift.orders === 1 ? '' : 's' }} ·
              {{ kwacha(shift.sales_ngwee) }} taken
            </span>
          </div>
          <div v-if="!offline" class="bar-actions">
            <button v-if="myWaiting.length" class="btn-quiet btn-small" @click="syncNow()">Send waiting sales</button>
            <button v-if="session.can('cash.move')" class="btn-quiet btn-small" @click="cashMove.open = !cashMove.open">Cash drop or petty cash</button>
            <button class="btn-quiet btn-small" :disabled="myWaiting.length > 0" :title="myWaiting.length ? 'Send the waiting offline sales first' : ''" @click="closing.open = !closing.open">Close the till</button>
          </div>
        </section>
        <p v-if="cashMove.done" class="notice">{{ cashMove.done }}</p>

        <div v-if="cashMove.open" class="panel closing">
          <b>Cash out of, or into, the drawer</b>
          <p class="muted">Not a sale and not a refund. A manager confirms it, and it counts in your till straight away.</p>
          <div class="row">
            <label class="field">
              What
              <select v-model="cashMove.kind">
                <option value="drop">Drop to the safe</option>
                <option value="petty">Petty cash spent</option>
                <option value="added">Cash added from the safe</option>
              </select>
            </label>
            <label class="field">
              Amount
              <input v-model="cashMove.amount" type="text" inputmode="decimal" placeholder="0.00" />
            </label>
            <label class="field wide">
              {{ cashMove.kind === 'petty' ? 'What was bought' : 'Note' }}
              <input v-model="cashMove.reason" type="text" maxlength="200" :placeholder="cashMove.kind === 'petty' ? 'for example: 2 bags of ice' : 'for example: lunchtime drop'" />
            </label>
            <button class="btn-primary" :disabled="cashMove.saving" @click="moveCash">Record it</button>
            <button class="btn-quiet" @click="cashMove.open = false">Cancel</button>
          </div>
        </div>

        <div v-if="closing.open" class="panel closing">
          <b>Count the drawer</b>
          <p class="muted">
            Count every note and coin, float included, and type the total. The system compares it with what
            should be there only after you have entered it.
          </p>
          <div class="row">
            <label class="field">
              Counted
              <input v-model="closing.counted" type="text" inputmode="decimal" placeholder="0.00" />
            </label>
            <label v-if="closing.needsNote" class="field wide">
              What happened?
              <input v-model="closing.note" type="text" maxlength="300" placeholder="for example: gave K20 too much change" />
            </label>
            <button class="btn-primary" :disabled="closing.saving" @click="closeTill">Close the till</button>
            <button class="btn-quiet" @click="closing.open = false">Cancel</button>
          </div>
        </div>

        <section v-if="held.length && !placed && !receipt && !offline" class="panel held">
          <b>Waiting for payment</b>
          <ul>
            <li v-for="o in held" :key="o.id">
              <span><b>{{ o.number }}</b> <span class="muted">· {{ o.customer_name || 'Walk-in' }} · {{ kwacha(o.outstanding_ngwee) }}</span></span>
              <span class="row">
                <button class="btn-primary btn-small" @click="recall(o)">Take payment</button>
                <button class="btn-quiet btn-small" @click="change(o)">Change</button>
              </span>
            </li>
          </ul>
        </section>

        <!-- receipt, after payment -->
        <section v-if="receipt && offlineReceipt" class="panel done">
          <b>{{ offlineReceipt.receipt_number }} saved on this device</b>
          <p class="muted">
            {{ kwacha(offlineReceipt.charged_ngwee) }} cash
            <template v-if="receipt.change_ngwee">· change {{ kwacha(receipt.change_ngwee) }}</template>.
            Print the receipt and give the kitchen its copy: the kitchen screen only sees it once the
            connection is back.
          </p>
          <div class="row">
            <button class="btn-primary" @click="printReceipt">Print the receipt</button>
            <button class="btn-quiet" @click="startNextOrder">Next order</button>
          </div>
        </section>

        <section v-else-if="receipt" class="panel done">
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

        <!-- cash, taken offline -->
        <section v-else-if="offlinePay.open" class="panel paying">
          <header>
            <b>{{ kwacha(total) }} to pay, cash</b>
            <span class="muted">Offline: saved on this device and sent later</span>
          </header>
          <div class="pay-grid">
            <label class="field">
              Cash given
              <input v-model="offlinePay.tendered" type="text" inputmode="decimal" placeholder="optional" />
            </label>
            <div v-if="offlineChange" class="change">Change <b>{{ kwacha(offlineChange) }}</b></div>
            <button class="btn-primary" :disabled="offlinePay.saving" @click="takeOfflineCash">Take cash</button>
            <button class="btn-quiet" :disabled="offlinePay.saving" @click="offlinePay.open = false">Back</button>
          </div>
          <p class="muted">Mobile money and card need the connection, because the payment has to be matched.</p>
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
            <label v-if="['airtel', 'mtn', 'zamtel', 'card'].includes(payment.method)" class="switch seen">
              <input v-model="payment.confirmed" type="checkbox" />
              I have seen the message saying the money arrived
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
                  <small v-else-if="p.option_groups.length">{{ p.option_groups.length }} {{ p.option_groups.length === 1 ? 'choice' : 'choices' }}</small>
                </button>
              </li>
            </ul>
          </section>

          <aside class="cart panel">
            <b>{{ changing ? `Changing ${changing.number}` : 'Order' }}</b>
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
                  <button class="btn-quiet btn-small step" :aria-label="`One fewer ${line.product.name}`" @click="line.quantity > 1 ? line.quantity-- : cart.splice(index, 1)">−</button>
                  <span>{{ line.quantity }}</span>
                  <button class="btn-quiet btn-small step" :aria-label="`One more ${line.product.name}`" @click="line.quantity++">+</button>
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
              <label class="field">
                Phone (stamp card)
                <input
                  v-model="customer.phone"
                  type="tel"
                  placeholder="0976…"
                  @blur="lookUpCustomer"
                />
              </label>
              <label class="field">
                Promo code
                <input
                  v-model="promo.code"
                  type="text"
                  placeholder="STUDENT10"
                  style="text-transform: uppercase"
                  @blur="checkPromo"
                  @keydown.enter.prevent="checkPromo"
                />
              </label>
            </div>

            <label v-if="discountNgwee" class="field reason">
              Why the discount?
              <input v-model="customer.discountReason" type="text" maxlength="160" placeholder="for example: spilt drink, staff meal" />
            </label>

            <p v-if="promo.message" :class="promo.off ? 'notice' : 'warn-note'" style="margin: .5rem 0">{{ promo.message }}</p>

            <div v-if="known" class="stampcard">
              <div>
                <b>{{ known.name || 'Customer' }}</b>
                <span class="muted"> · {{ known.stamps }} of {{ known.stamps_needed }} stamps</span>
              </div>
              <div class="dots" aria-hidden="true">
                <i v-for="n in known.stamps_needed" :key="n" :class="{ on: n <= known.stamps }" />
              </div>
              <p v-if="known.free_ready" class="free">Card full: the cheapest bowl or burrito comes off when you go to payment.</p>
            </div>

            <dl class="totals">
              <div><dt>Subtotal</dt><dd>{{ kwacha(subtotal) }}</dd></div>
              <div v-if="discountNgwee"><dt>Discount</dt><dd>−{{ kwacha(discountNgwee) }}</dd></div>
              <div v-if="promo.off"><dt>{{ promo.code.toUpperCase() }}</dt><dd>−{{ kwacha(promo.off) }}</dd></div>
              <div class="grand"><dt>Total</dt><dd>{{ kwacha(total) }}</dd></div>
            </dl>

            <div class="row">
              <button class="btn-primary" :disabled="!cart.length || busy" @click="placeOrder()">
                {{ offline ? 'Take cash (offline)' : changing ? `Save ${changing.number} and pay` : 'Go to payment' }}
              </button>
              <button class="btn-quiet" :disabled="!cart.length" @click="clearCart(); changing = null">Clear</button>
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
              <span class="muted">{{ groupRule(g) }}</span>
              <span v-if="overIncluded(g)" class="over">+{{ kwacha(overIncluded(g) * (g.extra_ngwee ?? 0)) }} for {{ overIncluded(g) }} extra</span>
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
    <ManagerApproval
      v-if="approval.retry"
      :what="approval.what"
      :error="approval.error"
      @approve="approveWith"
      @cancel="approval.retry = null"
    />

    <div v-if="receipt" class="print-only receipt">
      <h2>{{ receipt.business }}</h2>
      <p>{{ receipt.address }}<br />{{ receipt.phone }}<template v-if="receipt.tpin"><br />TPIN {{ receipt.tpin }}</template></p>
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
          <tr v-if="receipt.vat_ngwee"><td>VAT included</td><td class="r">{{ kwacha(receipt.vat_ngwee, false) }}</td></tr>
        </tbody>
      </table>
      <p class="footer">{{ receipt.footer }}</p>
    </div>
  </AppShell>
</template>

<style scoped>
.open-till, .shift-bar, .closing, .done, .paying, .problems { margin-bottom: 1rem; }
.offline-note { margin: 0 0 1rem; }
.problems ul { list-style: none; margin: .6rem 0 0; padding: 0; display: grid; gap: .6rem; }
.problems li { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; border-top: 1px solid var(--line); padding-top: .6rem; }
.problems p { margin: .3rem 0 0; }
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
.line-actions { display: flex; gap: 0.35rem; align-items: center; margin-top: 0.3rem; flex-wrap: wrap; }
.line-actions .note { flex: 1 1 6rem; min-width: 0; min-height: 32px; font-size: 0.82rem; padding: 0.3rem 0.45rem; }
.line-actions .step { width: 32px; padding: 0; justify-content: center; }
.line-top span { white-space: nowrap; font-variant-numeric: tabular-nums; }
.who { display: grid; gap: 0.5rem; grid-template-columns: 1fr 1fr; margin-bottom: 0.7rem; }
.who .field:first-child { grid-column: span 2; }
.totals { margin: 0; display: grid; gap: 0.2rem; }
.totals > div { display: flex; justify-content: space-between; }
.totals dt, .totals dd { margin: 0; font-size: 0.9rem; }
.totals .grand dt, .totals .grand dd { font-weight: 800; font-size: 1.1rem; }

.methods { display: flex; gap: 0.4rem; flex-wrap: wrap; margin: 0.7rem 0; }
.method { background: var(--paper); color: var(--ink); border: 1.5px solid var(--line); border-radius: 999px; min-height: 44px; padding: .45rem 1rem; font-weight: 700; cursor: pointer; }
.method:hover { border-color: var(--green); }
.method.on { background: var(--green); color: var(--green-ink); border-color: var(--green); }
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
.group-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 0.2rem 0.6rem; }
.group-head span { font-size: 0.8rem; }
.options-grid { list-style: none; margin: 0.5rem 0 0; padding: 0; display: grid; gap: 0.4rem; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
.option { width: 100%; background: var(--paper); color: var(--ink); border: 1.5px solid var(--line); text-align: left; font-weight: 400; }
.option.on { background: var(--leaf-soft); border-color: var(--green); color: var(--green-deep); font-weight: 700; }
.over { color: var(--warn); font-weight: 700; font-size: .85rem; }
.option.out { opacity: 0.45; }
.option small { display: block; font-size: 0.74rem; color: var(--muted); }
.builder > footer { display: flex; justify-content: space-between; align-items: center; margin-top: 1rem; }
.builder > footer b { font-size: 1.2rem; }

.print-only { display: none; }

@media (min-width: 960px) {
  .till { grid-template-columns: 1fr 340px; }
}

/* The receipt fits an 80 mm till roll; on A4 it prints at the top left. */
@page { margin: 4mm; }
@media print {
  .screen-only { display: none !important; }
  .print-only { display: block; font-family: 'Courier New', monospace; width: 72mm; color: #000; background: #fff; }
  .print-only * { color: #000 !important; }
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
.bar-actions { display: flex; gap: .5rem; flex-wrap: wrap; }
.held ul { list-style: none; margin: .5rem 0 0; padding: 0; display: grid; gap: .4rem; }
.held li { display: flex; justify-content: space-between; align-items: center; gap: .6rem; flex-wrap: wrap; }
.held .row { margin: 0; }
.reason { margin-top: .4rem; }
.seen { white-space: normal; grid-column: 1 / -1; }
.stampcard { background: var(--leaf-soft); border-radius: 12px; padding: .7rem .85rem; margin: .6rem 0; display: grid; gap: .45rem; }
.stampcard .dots { display: flex; gap: .3rem; flex-wrap: wrap; }
.stampcard .dots i { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--green); background: transparent; }
.stampcard .dots i.on { background: var(--green); }
.stampcard .free { margin: 0; color: var(--green-deep); font-weight: 700; font-size: .9rem; }
</style>
