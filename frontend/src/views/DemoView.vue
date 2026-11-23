<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demoRequest, type Choice, type Group, type PaymentOutcome, type Product, type Tracking } from '../services/demo'
import { kwacha } from '../services/money'

type Line = { product: Product; choices: Choice[]; quantity: number; note: string }

const route = useRoute()
const router = useRouter()
const products = ref<Product[]>([])
const category = ref('')
const cart = ref<Line[]>([])
const product = ref<Product>()
const dialog = ref<HTMLDialogElement>()
const selection = ref<Record<string, Choice[]>>({})
const note = ref('')
const tracked = ref<Tracking>()
const submitting = ref(false)
const loadingMenu = ref(true)
const menuError = ref('')
const orderError = ref('')
let checkoutKey = ''
let timer: ReturnType<typeof setInterval>
const asset = `${import.meta.env.BASE_URL}demo/`
const token = computed(() => route.hash.slice(1))
const categories = computed(() => [...new Set(products.value.map(item => item.category))])
const visible = computed(() => products.value.filter(item => !category.value || item.category === category.value))
const unitPrice = (item: Product, choices: Choice[]) => item.price_ngwee + choices.reduce((sum, choice) => sum + choice.price_ngwee, 0)
const total = computed(() => cart.value.reduce((sum, line) => sum + unitPrice(line.product, line.choices) * line.quantity, 0))
const choices = computed(() => Object.values(selection.value).flat())
const valid = computed(() => product.value?.groups.every(group => (selection.value[group.id]?.length ?? 0) >= group.min))
function scrollToMenu() { document.getElementById('menu')?.scrollIntoView() }

const statuses: Record<string, string> = {
  initiated: 'Initiated', pending: 'Pending', successful: 'Successful', failed: 'Failed',
  waiting: 'Queued', preparing: 'Being made', ready: 'Ready for pickup', served: 'Collected', cancelled: 'Cancelled',
}

function illustration(item: Product) {
  if (item.code === 'BOWL-01') return 'bowl.webp'
  if (item.code === 'BOWL-02') return 'bowl-alt.webp'
  if (item.code.startsWith('BUR')) return 'burrito.webp'
  if (item.code.startsWith('SMO') || item.code.startsWith('JUI')) return 'drink.webp'
  return ''
}

async function selectProduct(item: Product) {
  if (!item.available) return
  product.value = item
  selection.value = {}
  note.value = ''
  await nextTick()
  dialog.value?.showModal()
}

function toggle(group: Group, item: Choice) {
  const current = selection.value[group.id] ?? []
  if (current.some(choice => choice.id === item.id)) {
    selection.value[group.id] = current.filter(choice => choice.id !== item.id)
  } else if (group.max === 1) {
    selection.value[group.id] = [item]
  } else if (current.length < group.max) {
    selection.value[group.id] = [...current, item]
  }
}

function add() {
  if (!product.value || !valid.value || cart.value.length >= 20) return
  cart.value.push({ product: product.value, choices: choices.value, quantity: 1, note: note.value.trim() })
  dialog.value?.close()
}

async function loadOrder(quiet = false) {
  const requested = token.value
  if (!requested || submitting.value) return
  try {
    const result = await demoRequest<Tracking>(`/orders/${encodeURIComponent(requested)}`)
    if (requested === token.value) {
      tracked.value = result
      if (tracked.value.kitchen || tracked.value.payment !== 'initiated') orderError.value = ''
    }
  } catch (error) {
    if (!quiet && requested === token.value) orderError.value = (error as Error).message
  }
}

async function checkout() {
  checkoutKey ||= crypto.randomUUID()
  const key = checkoutKey
  submitting.value = true
  orderError.value = ''
  try {
    const result = await demoRequest<Tracking>(`/orders/${key}`, {
      lines: cart.value.map(line => ({
        product_id: line.product.id, quantity: line.quantity, note: line.note,
        options: line.choices.map(choice => ({ option_item_id: choice.id })),
      })),
    })
    await router.replace({ path: '/demo', hash: `#${key}` })
    tracked.value = result
    cart.value = []
  } catch (error) {
    orderError.value = (error as Error).message
  } finally {
    submitting.value = false
  }
}

async function simulate(outcome: PaymentOutcome) {
  const key = token.value
  if (!key) return
  submitting.value = true
  orderError.value = ''
  try {
    const result = await demoRequest<Tracking>(`/orders/${encodeURIComponent(key)}/payment`, { outcome })
    if (key === token.value) tracked.value = result
  } catch (error) {
    if (key === token.value) orderError.value = (error as Error).message
  } finally {
    submitting.value = false
  }
}

async function clearOrder() {
  checkoutKey = ''
  await router.replace({ path: '/demo', hash: '' })
}

watch(token, () => {
  tracked.value = undefined
  orderError.value = ''
  void loadOrder()
}, { immediate: true })

watch(cart, () => {
  if (!submitting.value) checkoutKey = ''
}, { deep: true })

onMounted(async () => {
  timer = setInterval(() => { void loadOrder(true) }, 4000)
  try {
    products.value = await demoRequest<Product[]>('/menu')
  } catch (error) {
    menuError.value = (error as Error).message
  } finally {
    loadingMenu.value = false
  }
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="storefront">
    <header class="top">
      <RouterLink to="/demo" aria-label="The Green Buffet demo home"><img :src="asset + 'logo.png'" alt="The Green Buffet" /></RouterLink>
      <nav aria-label="Demo">
        <a href="#menu" @click.prevent="scrollToMenu">Menu</a>
        <RouterLink to="/login">Staff sign in</RouterLink>
      </nav>
    </header>
    <div class="demo-strip">Client demonstration · Sample menu prices · Simulated payments</div>
    <main>
      <section class="hero">
        <div class="hero-text">
          <h1>Create a Bowl That Describes You.</h1>
          <p>Pick your base, protein and toppings, then follow your demo order from the kitchen to pickup.</p>
          <button class="primary" @click="scrollToMenu">Explore the menu</button>
        </div>
        <figure><img :src="asset + 'bowl.webp'" alt="Illustrative bowl with avocado and vegetables" /><figcaption>Illustrative photography</figcaption></figure>
      </section>

      <section v-if="token" class="tracking" aria-live="polite">
        <h2>Track your demo order</h2>
        <p v-if="!tracked && !orderError">Loading order…</p>
        <template v-if="tracked">
          <p><b>{{ tracked.order_number }}</b> · {{ kwacha(tracked.total_ngwee) }}</p>
          <p>Simulated payment <b>{{ statuses[tracked.payment] }}</b></p>
          <p v-if="tracked.kitchen">Demo kitchen <b>{{ statuses[tracked.kitchen] }}</b></p>
          <div v-if="tracked.payment === 'initiated' || tracked.payment === 'pending'" class="actions">
            <button class="primary" :disabled="submitting" @click="simulate('successful')">Simulate success</button>
            <button :disabled="submitting || tracked.payment === 'pending'" @click="simulate('pending')">Simulate pending</button>
            <button :disabled="submitting" @click="simulate('failed')">Simulate failure</button>
          </div>
        </template>
        <p v-if="orderError" role="alert" class="error">{{ orderError }}</p>
        <button :disabled="submitting" @click="clearOrder">Start a new order</button>
      </section>

      <section id="menu" class="menu">
        <h2>Explore the menu</h2>
        <div class="filters" aria-label="Menu categories">
          <button :aria-pressed="category === ''" @click="category = ''">All</button>
          <button v-for="name in categories" :key="name" :aria-pressed="category === name" @click="category = name">{{ name }}</button>
        </div>
        <p v-if="loadingMenu" role="status">Loading the demo menu…</p>
        <p v-if="menuError" role="alert" class="error">{{ menuError }}</p>
        <div class="shop">
          <div class="products">
            <article v-for="item in visible" :key="item.id" class="dish">
              <img v-if="illustration(item)" :src="asset + illustration(item)" alt="" loading="lazy" />
              <div class="dish-body">
                <h3>{{ item.name }}</h3>
                <p>{{ item.description }}</p>
                <div class="dish-action">
                  <b>{{ kwacha(item.price_ngwee) }}</b>
                  <button :disabled="!item.available || !!token || submitting || cart.length >= 20" @click="selectProduct(item)">
                    {{ !item.available ? 'Sold out' : item.groups.length ? 'Customize' : 'Select' }}
                    <span class="sr-only" v-if="item.available"> {{ item.name }}</span>
                  </button>
                </div>
              </div>
            </article>
          </div>
          <aside v-if="!token" class="cart">
            <h2>Your order</h2>
            <p v-if="!cart.length">Choose a dish to get started.</p>
            <ul>
              <li v-for="(line, index) in cart" :key="index">
                <b>{{ line.product.name }}</b>
                <small v-if="line.choices.length">{{ line.choices.map(choice => choice.name).join(', ') }}</small>
                <label>Quantity <input v-model.number="line.quantity" :disabled="submitting" type="number" min="1" max="20" required /></label>
                <button :disabled="submitting" @click="cart.splice(index, 1)">Remove</button>
              </li>
            </ul>
            <p class="total"><span>Estimated total</span><b>{{ kwacha(total) }}</b></p>
            <p v-if="orderError" role="alert" class="error">{{ orderError }}</p>
            <button class="primary" :disabled="!cart.length || submitting || cart.some(line => !Number.isInteger(line.quantity) || line.quantity < 1 || line.quantity > 20)" @click="checkout">Start demo checkout</button>
          </aside>
        </div>
      </section>
    </main>

    <dialog ref="dialog" @close="product = undefined">
      <template v-if="product">
        <div class="dialog-head">
          <h2>{{ product.name }}</h2>
          <button @click="dialog?.close()">Close</button>
        </div>
        <p>{{ product.description }}</p>
        <fieldset v-for="group in product.groups" :key="group.id">
          <legend>{{ group.name }} <small>{{ group.min === group.max ? `Choose ${group.min}` : `Choose ${group.min}–${group.max}` }}</small></legend>
          <div class="filters">
            <button v-for="choice in group.items" :key="choice.id" :disabled="!choice.available"
              :aria-pressed="(selection[group.id] ?? []).some(selected => selected.id === choice.id)" @click="toggle(group, choice)">
              {{ choice.name }}{{ choice.price_ngwee ? ` +${kwacha(choice.price_ngwee)}` : '' }}
            </button>
          </div>
        </fieldset>
        <label class="note">Special instructions <input v-model="note" maxlength="160" /></label>
        <button class="primary" :disabled="!valid" @click="add">Add to order · {{ kwacha(unitPrice(product, choices)) }}</button>
      </template>
    </dialog>
  </div>
</template>

<style scoped>
.storefront { --forest: #195332; --ink: #29221b; --paper: #faf7ef; background: var(--paper); min-height: 100vh; color: var(--ink); }
.top, main { max-width: 75rem; margin: auto; padding-inline: clamp(1rem, 4vw, 3rem); }
.top, .top nav, .dish-action, .dialog-head, .total, .actions { display: flex; align-items: center; justify-content: space-between; gap: .75rem; flex-wrap: wrap; }
.top { min-height: 5rem; }
.top img { width: 10rem; vertical-align: middle; }
.top a { color: var(--forest); font-weight: 700; }
.demo-strip { background: var(--forest); color: #fff; text-align: center; padding: .55rem 1rem; font-size: .9rem; }
.hero { display: grid; grid-template-columns: 1.1fr 1fr; align-items: center; gap: 1.75rem; margin: 1.5rem 0 3rem; background: #e9efdc; border-radius: 1.5rem; overflow: hidden; }
.hero-text { padding: clamp(1.25rem, 5vw, 4rem); }
h1, h2, h3 { color: var(--ink); margin: 0; }
h1 { font-size: clamp(2.6rem, 5.6vw, 5rem); line-height: .99; letter-spacing: -.06em; }
h2 { font-size: clamp(1.4rem, 3vw, 2rem); }
.hero p { max-width: 34ch; font-size: 1.1rem; }
figure { margin: 0; position: relative; min-height: 100%; }
figure img { display: block; width: 100%; height: 100%; min-height: 17rem; object-fit: cover; }
figcaption { position: absolute; right: .5rem; bottom: .5rem; background: white; padding: .25rem .6rem; border-radius: 1rem; font-size: .75rem; }
button { background: white; color: var(--forest); border: 1px solid #cad4c6; border-radius: 1.5rem; padding: .55rem .9rem; font: inherit; font-weight: 700; cursor: pointer; }
button.primary, button[aria-pressed="true"] { background: var(--forest); color: white; border-color: var(--forest); }
button:disabled { opacity: .52; cursor: default; }
.menu { padding-bottom: 3rem; scroll-margin: 1rem; }
.filters { display: flex; flex-wrap: wrap; gap: .45rem; margin: .75rem 0; }
.shop { display: grid; grid-template-columns: minmax(0, 1fr) minmax(15rem, 22%); gap: 1.3rem; align-items: start; }
.products { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 13.5rem), 1fr)); gap: 1rem; }
.dish, .cart, .tracking, dialog { background: #fff; border: 1px solid #e2ded2; border-radius: 1rem; }
.dish { display: flex; flex-direction: column; overflow: hidden; }
.dish > img { width: 100%; height: 10rem; object-fit: cover; }
.dish-body { padding: 1rem; display: flex; flex: 1; flex-direction: column; }
.dish-action { margin-top: auto; }
.cart, .tracking { padding: 1rem; }
.cart { position: sticky; top: .75rem; }
.cart ul { list-style: none; padding: 0; }
.cart li { border-bottom: 1px solid #e2ded2; padding-block: .65rem; }
.cart small { display: block; margin-bottom: .4rem; }
.cart input { width: 4rem; }
.tracking { margin-bottom: 2rem; }
.actions { justify-content: start; margin-bottom: .9rem; }
dialog { padding: 1.2rem; width: min(36rem, 94vw); max-height: 88vh; color: inherit; }
dialog::backdrop { background: #14241d88; }
fieldset { margin: .7rem 0; border: 1px solid #e2ded2; border-radius: .6rem; }
legend { font-weight: 700; }
legend small { margin-left: .5rem; font-weight: 400; }
.note { display: grid; gap: .35rem; margin: .9rem 0; }
.error { color: #8d1d19; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (max-width: 720px) {
  .hero, .shop { grid-template-columns: 1fr; }
  .hero { gap: 0; margin-bottom: 1.5rem; }
  .hero figure img { height: 15rem; min-height: 0; }
  .cart { position: static; order: -1; }
}
</style>
