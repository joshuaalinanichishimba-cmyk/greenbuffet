<!--
  The customer's page: the menu, a basket and a checkout.

  Nobody signs in here. This is the only screen in the system a stranger can
  reach, so it asks for the least it can get away with - a name, a phone
  number, and an address only when the food has to be carried somewhere.

  It is written phone-first because that is how it will be used: standing in
  a queue, on a slow connection, with one thumb.
-->
<template>
  <div class="shop">
    <header class="shop-bar">
      <div class="mark">GB</div>
      <div class="who">
        <strong>{{ shop?.name || 'The Green Buffet' }}</strong>
        <span>{{ shop?.location || 'Liberty Mall, Kitwe' }}</span>
      </div>
      <a v-if="firstPhone" class="call" :href="`tel:${firstPhone}`">Call {{ firstPhone }}</a>
    </header>

    <section class="shop-hero">
      <h1>Fresh food, made to order</h1>
      <p>Build your bowl, pick it up at Liberty Mall or have it delivered. Pay when it reaches you.</p>
      <div v-if="shop && !shop.accepting_orders" class="closed">
        {{ shop.closed_message }}
      </div>
    </section>

    <div class="shop-body">
      <p v-if="loadError" class="error">{{ loadError }}</p>
      <p v-else-if="loading" class="muted">Loading the menu…</p>

      <template v-else>
        <nav class="cat-strip" aria-label="Menu sections">
          <button
            v-for="category in menu"
            :key="category.id"
            :class="{ on: visibleCategory === category.id }"
            @click="jumpTo(category.id)"
          >
            {{ category.name }}
          </button>
        </nav>

        <section
          v-for="category in menu"
          :id="`cat-${category.id}`"
          :key="category.id"
          class="shop-section"
        >
          <h2>{{ category.name }}</h2>
          <p v-if="category.description">{{ category.description }}</p>
          <div class="dish-grid">
            <article
              v-for="dish in category.products"
              :key="dish.id"
              class="dish"
              :class="{ 'sold-out': !dish.is_available }"
            >
              <div class="shot">
                <img
                  v-if="dish.photo_id && !brokenPhotos.has(dish.photo_id)"
                  :src="photoUrl(dish.photo_id)"
                  :alt="dish.name"
                  loading="lazy"
                  @error="brokenPhotos = new Set([...brokenPhotos, dish.photo_id])"
                />
                <span v-else>{{ initials(dish.name) }}</span>
              </div>
              <div class="about">
                <h3>{{ dish.name }}</h3>
                <p v-if="dish.description">{{ dish.description }}</p>
                <div class="foot">
                  <span class="price">{{ kwacha(dish.price_ngwee) }}</span>
                  <span v-if="!dish.is_available" class="tag off">Sold out</span>
                  <button
                    v-else
                    class="btn-primary btn-small"
                    @click="open(dish)"
                  >
                    {{ dish.groups.length ? 'Choose' : 'Add' }}
                  </button>
                </div>
              </div>
            </article>
          </div>
        </section>
      </template>
    </div>

    <!-- the basket bar, always within reach of a thumb -->
    <div v-if="basket.length" class="basket-bar">
      <span class="count">{{ itemCount }}</span>
      <span class="total">{{ kwacha(basketTotal) }}</span>
      <button class="btn-big" @click="checkoutOpen = true">See basket</button>
    </div>

    <!-- choosing options on one dish -->
    <div v-if="chosen" class="sheet-back" @click.self="chosen = null">
      <div class="sheet" role="dialog" aria-modal="true">
        <div class="sheet-head">
          <div>
            <h2>{{ chosen.name }}</h2>
            <p class="muted">{{ chosen.description }}</p>
          </div>
          <button class="btn-quiet btn-small" @click="chosen = null">Close</button>
        </div>

        <div v-for="group in chosen.groups" :key="group.id" class="choice-group">
          <h4>{{ group.name }}</h4>
          <p class="rule">{{ ruleFor(group) }}</p>
          <label
            v-for="item in group.items"
            :key="item.id"
            class="choice"
            :class="{ on: isPicked(group.id, item.id) }"
          >
            <input
              :type="group.max_select === 1 ? 'radio' : 'checkbox'"
              :name="group.id"
              :checked="isPicked(group.id, item.id)"
              :disabled="!item.is_available"
              @change="pick(group, item)"
            />
            <span>{{ item.name }}<em v-if="!item.is_available" class="muted"> (sold out)</em></span>
            <span v-if="item.price_ngwee" class="extra">+{{ kwacha(item.price_ngwee) }}</span>
          </label>
        </div>

        <label class="field" style="margin-top: 1rem">
          Anything to tell the kitchen?
          <input v-model="chosenNote" type="text" maxlength="160" placeholder="No chilli, extra sauce…" />
        </label>

        <p v-if="chooseError" class="error">{{ chooseError }}</p>

        <div class="row" style="margin-top: 1rem">
          <div class="qty">
            <button class="btn-quiet" @click="chosenQty = Math.max(1, chosenQty - 1)">−</button>
            <strong>{{ chosenQty }}</strong>
            <button class="btn-quiet" @click="chosenQty = Math.min(20, chosenQty + 1)">+</button>
          </div>
          <button class="btn-primary btn-block" style="flex: 1" @click="addChosen">
            Add {{ kwacha(chosenTotal) }}
          </button>
        </div>
      </div>
    </div>

    <!-- the basket and checkout -->
    <div v-if="checkoutOpen" class="sheet-back" @click.self="checkoutOpen = false">
      <div class="sheet" role="dialog" aria-modal="true">
        <div class="sheet-head">
          <h2>Your order</h2>
          <button class="btn-quiet btn-small" @click="checkoutOpen = false">Close</button>
        </div>

        <div v-for="(line, index) in basket" :key="index" class="basket-line">
          <div class="what">
            <strong>{{ line.name }}</strong>
            <span v-if="line.optionNames.length">{{ line.optionNames.join(', ') }}</span>
            <span v-if="line.note">“{{ line.note }}”</span>
          </div>
          <div class="qty">
            <button class="btn-quiet" @click="changeQty(index, -1)">−</button>
            <strong>{{ line.quantity }}</strong>
            <button class="btn-quiet" @click="changeQty(index, 1)">+</button>
          </div>
          <span class="amount">{{ kwacha(line.each * line.quantity) }}</span>
        </div>

        <div class="tabs" style="margin-top: 1.2rem">
          <button :class="{ on: fulfilment === 'collection' }" @click="fulfilment = 'collection'">
            I will collect
          </button>
          <button :class="{ on: fulfilment === 'delivery' }" @click="fulfilment = 'delivery'">
            Deliver to me
          </button>
        </div>

        <div class="grid-2">
          <label class="field">
            Your name
            <input v-model="customerName" type="text" maxlength="80" autocomplete="name" />
          </label>
          <label class="field">
            Phone number
            <input v-model="customerPhone" type="tel" maxlength="24" autocomplete="tel" placeholder="0976 000 000" />
          </label>
        </div>

        <template v-if="fulfilment === 'delivery'">
          <label class="field" style="margin-top: 0.7rem">
            Area
            <select v-model="zoneId">
              <option value="">Choose your area</option>
              <option v-for="zone in zones" :key="zone.id" :value="zone.id">
                {{ zone.name }} — {{ kwacha(zone.fee_ngwee) }}, about {{ zone.minutes }} min
              </option>
            </select>
          </label>
          <label class="field" style="margin-top: 0.7rem">
            Address
            <input v-model="address" type="text" maxlength="200" placeholder="House number and street" />
          </label>
          <label class="field" style="margin-top: 0.7rem">
            How to find you
            <input v-model="directions" type="text" maxlength="300" placeholder="Green gate opposite the school" />
          </label>
          <p v-if="zone && zone.minimum_ngwee" class="muted" style="margin-top: 0.4rem">
            Orders to {{ zone.name }} start at {{ kwacha(zone.minimum_ngwee) }}.
          </p>
        </template>

        <div class="totals">
          <div><span>Food</span><span>{{ kwacha(basketTotal) }}</span></div>
          <div v-if="deliveryFee"><span>Delivery to {{ zone?.name }}</span><span>{{ kwacha(deliveryFee) }}</span></div>
          <div class="sum"><span>Total</span><span>{{ kwacha(basketTotal + deliveryFee) }}</span></div>
        </div>

        <p class="muted">You pay when you collect, or when the food reaches you.</p>
        <p v-if="sendError" class="error">{{ sendError }}</p>

        <button
          class="btn-primary btn-big btn-block"
          style="margin-top: 0.8rem"
          :disabled="sending || !shop?.accepting_orders"
          @click="send"
        >
          {{ sending ? 'Sending…' : `Place order · ${kwacha(basketTotal + deliveryFee)}` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { kwacha } from '../services/money'
import { publicApi, type PublicGroup, type PublicItem, type PublicProduct, type PublicZone, type ShopInfo } from '../services/publicApi'

interface BasketLine {
  productId: string
  name: string
  each: number
  quantity: number
  note: string
  optionIds: string[]
  optionNames: string[]
}

const router = useRouter()

const shop = ref<ShopInfo | null>(null)
const menu = ref<{ id: string; name: string; description: string; products: PublicProduct[] }[]>([])
const loading = ref(true)
const loadError = ref('')
const visibleCategory = ref('')

// A photo that will not load must never become a wall of alt text where the
// picture should be; the dish falls back to its initials instead.
const brokenPhotos = ref<Set<string>>(new Set())

const basket = ref<BasketLine[]>([])
const checkoutOpen = ref(false)
const chosen = ref<PublicProduct | null>(null)
const chosenQty = ref(1)
const chosenNote = ref('')
const chooseError = ref('')
const picked = ref<Record<string, string[]>>({})

const fulfilment = ref<'collection' | 'delivery'>('collection')
const customerName = ref('')
const customerPhone = ref('')
const address = ref('')
const directions = ref('')
const zoneId = ref('')
const sending = ref(false)
const sendError = ref('')

const zones = computed(() => shop.value?.zones ?? [])
const zone = computed<PublicZone | undefined>(() => zones.value.find((z) => z.id === zoneId.value))
const firstPhone = computed(() => shop.value?.phones?.[0] ?? '')

const itemCount = computed(() => basket.value.reduce((n, line) => n + line.quantity, 0))
const basketTotal = computed(() => basket.value.reduce((n, line) => n + line.each * line.quantity, 0))
const deliveryFee = computed(() => (fulfilment.value === 'delivery' && zone.value ? zone.value.fee_ngwee : 0))
const chosenTotal = computed(() => {
  if (!chosen.value) return 0
  const extras = Object.values(picked.value)
    .flat()
    .reduce((sum, id) => sum + (priceOf(id) ?? 0), 0)
  return (chosen.value.price_ngwee + extras) * chosenQty.value
})

function photoUrl(id: string) {
  return publicApi.photoUrl(id)
}

function initials(name: string) {
  return name
    .split(' ')
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

function priceOf(optionId: string): number | undefined {
  for (const group of chosen.value?.groups ?? []) {
    const found = group.items.find((item) => item.id === optionId)
    if (found) return found.price_ngwee
  }
  return undefined
}

function nameOf(optionId: string): string {
  for (const group of chosen.value?.groups ?? []) {
    const found = group.items.find((item) => item.id === optionId)
    if (found) return found.name
  }
  return ''
}

function ruleFor(group: PublicGroup) {
  if (group.min_select === 1 && group.max_select === 1) return 'Choose one'
  if (group.min_select === 0 && group.max_select === 1) return 'Choose one, or none'
  if (group.min_select === group.max_select) return `Choose ${group.min_select}`
  if (group.min_select === 0) return `Up to ${group.max_select}`
  return `Choose ${group.min_select} to ${group.max_select}`
}

function open(dish: PublicProduct) {
  chosen.value = dish
  chosenQty.value = 1
  chosenNote.value = ''
  chooseError.value = ''
  picked.value = {}
  if (!dish.groups.length) addChosen()
}

function isPicked(groupId: string, itemId: string) {
  return (picked.value[groupId] ?? []).includes(itemId)
}

function pick(group: PublicGroup, item: PublicItem) {
  const current = picked.value[group.id] ?? []
  if (group.max_select === 1) {
    picked.value = { ...picked.value, [group.id]: [item.id] }
    return
  }
  if (current.includes(item.id)) {
    picked.value = { ...picked.value, [group.id]: current.filter((id) => id !== item.id) }
  } else {
    if (current.length >= group.max_select) {
      chooseError.value = `${group.name}: at most ${group.max_select}.`
      return
    }
    picked.value = { ...picked.value, [group.id]: [...current, item.id] }
  }
  chooseError.value = ''
}

function addChosen() {
  const dish = chosen.value
  if (!dish) return
  // The same rules the server will apply, checked here so the customer is
  // told before the order is sent rather than after.
  for (const group of dish.groups) {
    const count = (picked.value[group.id] ?? []).length
    if (count < group.min_select) {
      chooseError.value = ruleFor(group) + ` from ${group.name}.`
      return
    }
  }
  const optionIds = Object.values(picked.value).flat()
  const extras = optionIds.reduce((sum, id) => sum + (priceOf(id) ?? 0), 0)
  basket.value = [
    ...basket.value,
    {
      productId: dish.id,
      name: dish.name,
      each: dish.price_ngwee + extras,
      quantity: chosenQty.value,
      note: chosenNote.value.trim(),
      optionIds,
      optionNames: optionIds.map(nameOf).filter(Boolean),
    },
  ]
  chosen.value = null
}

function changeQty(index: number, by: number) {
  const line = basket.value[index]
  if (!line) return
  const next = line.quantity + by
  if (next <= 0) {
    basket.value = basket.value.filter((_, i) => i !== index)
    if (!basket.value.length) checkoutOpen.value = false
    return
  }
  basket.value = basket.value.map((l, i) => (i === index ? { ...l, quantity: Math.min(20, next) } : l))
}

function jumpTo(categoryId: string) {
  document.getElementById(`cat-${categoryId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function send() {
  sendError.value = ''
  if (!customerName.value.trim()) {
    sendError.value = 'Please tell us your name.'
    return
  }
  if (customerPhone.value.replace(/\D/g, '').length < 9) {
    sendError.value = 'Please give a phone number we can reach you on.'
    return
  }
  if (fulfilment.value === 'delivery' && !zoneId.value) {
    sendError.value = 'Choose the area to deliver to.'
    return
  }
  if (fulfilment.value === 'delivery' && !address.value.trim()) {
    sendError.value = 'Enter the address to deliver to.'
    return
  }
  sending.value = true
  try {
    const placed = await publicApi.placeOrder({
      lines: basket.value.map((line) => ({
        product_id: line.productId,
        quantity: line.quantity,
        note: line.note,
        options: line.optionIds.map((id) => ({ option_item_id: id })),
      })),
      customer_name: customerName.value.trim(),
      customer_phone: customerPhone.value.trim(),
      fulfilment: fulfilment.value,
      address: address.value.trim(),
      directions: directions.value.trim(),
      zone_id: zoneId.value,
      note: '',
    })
    try {
      localStorage.setItem('gb-last-order', placed.token)
    } catch {
      /* private browsing */
    }
    basket.value = []
    checkoutOpen.value = false
    router.push(`/order/${placed.token}`)
  } catch (problem) {
    sendError.value = problem instanceof Error ? problem.message : 'That did not go through. Please try again.'
  } finally {
    sending.value = false
  }
}

// Which section is on screen, so the strip of category buttons keeps up.
let watcher: IntersectionObserver | null = null
function watchSections() {
  watcher?.disconnect()
  watcher = new IntersectionObserver(
    (entries) => {
      const seen = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (seen) visibleCategory.value = seen.target.id.replace('cat-', '')
    },
    { rootMargin: '-120px 0px -70% 0px', threshold: [0.01, 0.3] },
  )
  menu.value.forEach((category) => {
    const node = document.getElementById(`cat-${category.id}`)
    if (node) watcher?.observe(node)
  })
}

onMounted(async () => {
  try {
    const [info, card] = await Promise.all([publicApi.shop(), publicApi.menu()])
    shop.value = info
    menu.value = card.categories
    visibleCategory.value = card.categories[0]?.id ?? ''
    document.title = `${info.name} · Order online`
    setTimeout(watchSections, 60)
  } catch (problem) {
    loadError.value =
      problem instanceof Error ? problem.message : 'The menu could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => watcher?.disconnect())
</script>
