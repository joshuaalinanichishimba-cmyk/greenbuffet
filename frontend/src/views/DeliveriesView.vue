<!--
  Deliveries: orders taken at the till that have to leave the building.

  A delivery is an ordinary sale until the food is ready; after that it needs
  three things nobody else tracks - is it cooked, who took it, and did it
  arrive. That is all this board does.
-->
<template>
  <AppShell>
    <h1>Deliveries</h1>
    <p class="lead">
      Orders marked as a delivery at the till. Mark the food ready, say who is taking it,
      and tick it off when it arrives.
    </p>

    <div class="stat-row">
      <div class="stat"><span class="value">{{ cookingCount }}</span><span class="label">Being cooked</span></div>
      <div class="stat" :class="{ warn: readyCount > 0 }">
        <span class="value">{{ readyCount }}</span>
        <span class="label">Ready to go out</span>
      </div>
      <div class="stat"><span class="value">{{ deliveryCount }}</span><span class="label">Out with a rider</span></div>
      <div class="stat"><span class="value">{{ kwacha(outValue) }}</span><span class="label">Value out there</span></div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <div class="tabs">
      <button :class="{ on: showing === 'live' }" @click="switchTo('live')">Still out</button>
      <button :class="{ on: showing === 'all' }" @click="switchTo('all')">Everything today</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="!orders.length" class="empty">
      No deliveries. An order marked "Delivery" at the till appears here once it is paid for.
    </div>

    <div v-for="order in orders" :key="order.id" class="panel" style="margin-bottom: 0.8rem">
      <div class="spread">
        <div style="min-width: 0">
          <strong style="font-size: 1.05rem">{{ order.customer_name }}</strong>
          <span class="tag" :class="tagFor(order.track_status)" style="margin-left: 0.5rem">
            {{ label(order.track_status) }}
          </span>
          <span v-if="order.fulfilment === 'delivery'" class="tag info" style="margin-left: 0.3rem">
            {{ order.zone_name || 'Delivery' }}
          </span>
          <div class="muted">
            {{ order.number }} · {{ at(order.placed_at) }} ·
            <a :href="`tel:${order.customer_phone}`">{{ order.customer_phone }}</a>
          </div>
        </div>
        <strong style="font-size: 1.1rem">{{ kwacha(order.total_ngwee) }}</strong>
      </div>

      <ul style="margin: 0.7rem 0 0; padding-left: 1.1rem">
        <li v-for="(line, index) in order.lines" :key="index">{{ line }}</li>
      </ul>
      <p v-if="order.note" class="muted">Note: {{ order.note }}</p>
      <p v-if="order.address" class="muted">
        {{ order.address }}<span v-if="order.directions"> — {{ order.directions }}</span>
      </p>
      <p v-if="order.rider_name" class="muted">With {{ order.rider_name }}</p>

      <div class="row" style="margin-top: 0.8rem">
        <template v-if="order.track_status === 'cooking' || order.track_status === 'placed' || !order.track_status">
          <button class="btn-primary" :disabled="busy === order.id" @click="markReady(order)">
            Food is ready
          </button>
        </template>
        <template v-else-if="order.track_status === 'ready'">
          <button class="btn-primary" :disabled="busy === order.id" @click="startRider(order)">
            Send with a rider
          </button>
        </template>
        <template v-else-if="order.track_status === 'on_the_way'">
          <button class="btn-primary" :disabled="busy === order.id" @click="complete(order)">
            Delivered
          </button>
        </template>
        <span v-if="order.status === 'paid'" class="tag" style="margin-left: auto">Paid</span>
        <router-link v-else class="muted" :to="`/till`" style="margin-left: auto; align-self: center">
          Not paid yet
        </router-link>
      </div>
    </div>

    <!-- sending a rider -->
    <div v-if="dispatching" class="sheet-back" @click.self="dispatching = null">
      <div class="sheet">
        <h2>Who is taking {{ dispatching.number }}?</h2>
        <p class="muted">{{ dispatching.address }}</p>
        <div class="grid-2" style="margin-top: 0.8rem">
          <label class="field">
            Rider
            <input v-model="riderName" type="text" maxlength="80" />
          </label>
          <label class="field">
            Their phone
            <input v-model="riderPhone" type="tel" maxlength="24" />
          </label>
        </div>
        <div class="row end" style="margin-top: 1rem">
          <button class="btn-quiet" @click="dispatching = null">Cancel</button>
          <button class="btn-primary" @click="confirmRider">Send it out</button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api } from '../services/api'
import { kwacha } from '../services/money'

interface OnlineOrder {
  id: string
  number: string
  status: string
  track_status: string
  fulfilment: string
  customer_name: string
  customer_phone: string
  address: string
  directions: string
  zone_name: string
  delivery_fee_ngwee: number
  total_ngwee: number
  note: string
  rider_name: string
  placed_at: string
  reject_reason: string
  lines: string[]
}

const orders = ref<OnlineOrder[]>([])
const loading = ref(true)
const error = ref('')
const note = ref('')
const busy = ref('')
const showing = ref<'live' | 'all'>('live')

const dispatching = ref<OnlineOrder | null>(null)
const riderName = ref('')
const riderPhone = ref('')

let timer: number | undefined

const cookingCount = computed(
  () => orders.value.filter((o) => !o.track_status || ['placed', 'cooking'].includes(o.track_status)).length,
)
const readyCount = computed(() => orders.value.filter((o) => o.track_status === 'ready').length)
const deliveryCount = computed(() => orders.value.filter((o) => o.track_status === 'on_the_way').length)
const outValue = computed(() =>
  orders.value
    .filter((o) => o.track_status === 'on_the_way')
    .reduce((sum, o) => sum + o.total_ngwee, 0),
)

function label(state: string) {
  return (
    {
      '': 'Cooking',
      placed: 'Cooking',
      accepted: 'Cooking',
      cooking: 'Cooking',
      ready: 'Ready',
      on_the_way: 'On the way',
      completed: 'Done',
      rejected: 'Refused',
    } as Record<string, string>
  )[state] ?? state
}

function tagFor(state: string) {
  if (state === 'ready') return 'warn'
  if (state === 'rejected') return 'bad'
  if (state === 'completed') return 'off'
  return ''
}

function at(when: string) {
  if (!when) return ''
  return new Date(when).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

async function load() {
  try {
    orders.value = await api.get<OnlineOrder[]>(
      `/customers/deliveries?waiting=${showing.value === 'live'}`,
    )
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load the deliveries.'
  } finally {
    loading.value = false
  }
}

function switchTo(which: 'live' | 'all') {
  showing.value = which
  loading.value = true
  load()
}

async function act(order: OnlineOrder, path: string, body?: unknown, said = '') {
  busy.value = order.id
  note.value = ''
  try {
    await api.post(`/customers/deliveries/${order.id}/${path}`, body ?? {})
    if (said) note.value = said
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'That did not work.'
  } finally {
    busy.value = ''
  }
}

const markReady = (order: OnlineOrder) => act(order, 'ready', {}, `${order.number} is ready.`)
const complete = (order: OnlineOrder) => act(order, 'delivered', {}, `${order.number} delivered.`)

function startRider(order: OnlineOrder) {
  dispatching.value = order
  riderName.value = ''
  riderPhone.value = ''
}

async function confirmRider() {
  const order = dispatching.value
  if (!order) return
  dispatching.value = null
  await act(
    order,
    'rider',
    { rider_name: riderName.value, rider_phone: riderPhone.value },
    `${order.number} is on the way.`,
  )
}

onMounted(() => {
  load()
  // Often enough that a rider coming back is noticed, light enough that it
  // costs the till nothing.
  timer = window.setInterval(load, 15000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>
