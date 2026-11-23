<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, getToken, type KitchenTicket } from '../services/api'
import { session } from '../stores/session'

const tickets = ref<KitchenTicket[]>([])
const station = ref('')
const error = ref('')
const live = ref(false)
const loading = ref(true)
const busyId = ref('')
const now = ref(Date.now())

const mayWork = computed(() => session.canAny('kitchen.view', 'orders.update'))

const stations = [
  { id: '', label: 'Everything' },
  { id: 'kitchen', label: 'Kitchen' },
  { id: 'cold', label: 'Cold station' },
  { id: 'bar', label: 'Juice bar' },
]

const columns = [
  { status: 'waiting', label: 'New', next: 'preparing', action: 'Start' },
  { status: 'preparing', label: 'Being made', next: 'ready', action: 'Ready' },
  { status: 'ready', label: 'Ready to hand over', next: 'served', action: 'Handed over' },
]

function inColumn(status: string) {
  return tickets.value.filter((t) => t.status === status)
}

/** Minutes since the order was paid, counted in the browser so it keeps moving. */
function minutes(ticket: KitchenTicket) {
  return Math.max(0, Math.floor((now.value - new Date(ticket.placed_at).getTime()) / 60000))
}

function urgency(ticket: KitchenTicket) {
  const waited = minutes(ticket)
  if (waited >= 15) return 'late'
  if (waited >= 8) return 'slow'
  return ''
}

async function load() {
  try {
    tickets.value = await api.kitchenTickets(station.value || undefined)
    error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the board.'
  } finally {
    loading.value = false
  }
}

async function advance(ticket: KitchenTicket, status: string) {
  busyId.value = ticket.order_id
  try {
    tickets.value = await api.setTicketStatus(ticket.order_id, status)
    error.value = ''
    if (station.value) await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not move that ticket.'
    await load()
  } finally {
    busyId.value = ''
  }
}

// Live over a WebSocket, with a slow poll underneath it. A kitchen screen that
// silently stops updating is worse than one that is a few seconds behind, so
// the poll runs either way — every 10 seconds when live, every 5 when not.
let socket: WebSocket | null = null
let poll: number | undefined
let clock: number | undefined
let lastPoll = 0

function connect() {
  if (import.meta.env.VITE_KITCHEN_POLLING_ONLY === 'true') return
  const token = getToken()
  if (!token) return
  const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1')
    .replace(/^http/, 'ws')
  try {
    socket = new WebSocket(`${base}/kitchen/ws?token=${encodeURIComponent(token)}`)
  } catch {
    return
  }
  socket.onopen = () => (live.value = true)
  socket.onmessage = (message) => {
    try {
      const data = JSON.parse(message.data)
      if (data.event && data.event !== 'ready') load()
    } catch {
      /* ignore anything that is not ours */
    }
  }
  socket.onclose = () => {
    live.value = false
    socket = null
  }
  socket.onerror = () => (live.value = false)
}

onMounted(() => {
  load()
  connect()
  poll = window.setInterval(() => {
    const gap = live.value ? 10000 : 5000
    if (Date.now() - lastPoll >= gap) {
      lastPoll = Date.now()
      load()
      if (!socket) connect()
    }
  }, 2500)
  clock = window.setInterval(() => (now.value = Date.now()), 15000)
})

onUnmounted(() => {
  window.clearInterval(poll)
  window.clearInterval(clock)
  socket?.close()
})
</script>

<template>
  <AppShell>
    <div class="head">
      <div>
        <h1>Kitchen</h1>
        <p class="muted">
          Orders arrive here the moment they are paid, oldest first.
          <span :class="live ? 'live' : 'dim'">{{ live ? 'Live' : 'Checking every few seconds' }}</span>
        </p>
      </div>
      <div class="stations">
        <button
          v-for="s in stations"
          :key="s.id"
          class="station"
          :class="{ on: station === s.id }"
          @click="station = s.id; load()"
        >
          {{ s.label }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">Loading…</p>

    <div v-else class="board">
      <section v-for="col in columns" :key="col.status" class="column">
        <header>
          <b>{{ col.label }}</b>
          <span class="count">{{ inColumn(col.status).length }}</span>
        </header>

        <p v-if="!inColumn(col.status).length" class="muted empty">Nothing here.</p>

        <article
          v-for="t in inColumn(col.status)"
          :key="t.order_id"
          class="ticket"
          :class="urgency(t)"
        >
          <div class="ticket-head">
            <b>{{ t.order_number }}</b>
            <span class="waited">{{ minutes(t) }} min</span>
          </div>
          <p class="who">
            {{ { takeaway: 'Takeaway', eat_in: 'Eat in', delivery: 'Delivery' }[t.order_type] }}
            <template v-if="t.customer_name"> · {{ t.customer_name }}</template>
          </p>
          <ul class="items">
            <li v-for="i in t.items" :key="i.id" :class="i.status">
              <b>{{ i.quantity }} × {{ i.product_name }}</b>
              <small v-if="i.choices">{{ i.choices }}</small>
              <small v-if="i.note" class="note">{{ i.note }}</small>
              <small v-if="i.status !== t.status" class="done-tag">{{ i.status }}</small>
            </li>
          </ul>
          <button
            v-if="mayWork"
            class="btn-primary advance"
            :disabled="busyId === t.order_id"
            @click="advance(t, col.next)"
          >
            {{ col.action }}
          </button>
        </article>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
.head h1 { margin-bottom: 0.2rem; }
.head p { margin: 0 0 1rem; }
.live { color: var(--green-mid); font-weight: 700; }
.dim { color: var(--muted); }
.stations { display: flex; gap: 0.4rem; flex-wrap: wrap; }
.station { background: #fff; border: 1px solid #cfd6cb; }
.station.on { background: var(--green); color: #fff; border-color: var(--green); }

.board { display: grid; gap: 0.9rem; grid-template-columns: 1fr; align-items: start; }
.column { background: #eceee7; border-radius: 16px; padding: 0.7rem; }
.column > header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
.count { background: #fff; border-radius: 999px; padding: 0.1rem 0.6rem; font-weight: 700; font-size: 0.85rem; }
.empty { margin: 0.3rem 0 0; }

.ticket { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 0.7rem 0.8rem; margin-bottom: 0.6rem; }
.ticket.slow { border-color: #e0b400; box-shadow: inset 4px 0 0 #e0b400; }
.ticket.late { border-color: var(--danger); box-shadow: inset 4px 0 0 var(--danger); }
.ticket-head { display: flex; justify-content: space-between; align-items: baseline; }
.ticket-head b { font-size: 1.05rem; }
.waited { font-weight: 700; font-size: 0.85rem; color: var(--muted); }
.ticket.slow .waited { color: #8a6d00; }
.ticket.late .waited { color: var(--danger); }
.who { margin: 0.1rem 0 0.5rem; font-size: 0.82rem; color: var(--muted); }
.items { list-style: none; margin: 0 0 0.7rem; padding: 0; display: grid; gap: 0.45rem; }
.items li { border-top: 1px solid var(--line); padding-top: 0.4rem; }
.items li:first-child { border-top: 0; padding-top: 0; }
.items b { font-size: 0.95rem; }
.items small { display: block; font-size: 0.8rem; color: var(--muted); }
.items .note { color: #8a6d00; font-weight: 600; }
.items .done-tag { color: var(--green-mid); font-weight: 700; text-transform: capitalize; }
.items li.ready b { text-decoration: line-through; opacity: 0.6; }
.advance { width: 100%; min-height: 44px; }

@media (min-width: 900px) {
  .board { grid-template-columns: repeat(3, 1fr); }
}
</style>
