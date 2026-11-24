<!--
  The kitchen display, laid out as the demo's: a full-screen forest-green
  board with no sidebar, because it lives on a screen on the kitchen wall and
  is read from across the room.

  On the left, "To make now" adds up everything not yet made, so the cook
  sees eleven toppings of tomato rather than eleven tickets. On the right the
  three columns, New, Preparing and Ready for pickup, each ticket with a
  timer that turns red after fifteen minutes and the one button that moves
  it on.

  Live over a WebSocket, with a poll underneath it. A kitchen screen that
  silently stops updating is worse than one a few seconds behind.
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ApiError, api, getToken, type KitchenTicket } from '../services/api'
import { session } from '../stores/session'
import { homeFor } from '../services/home'

// For an account whose home IS this board, "/" leads straight back here, so
// its way out goes to the next most useful screen instead of in a circle.
const away = computed(() => {
  if (homeFor(session.user.value?.role_id, session.permissions.value) !== 'kitchen') return { to: '/', label: 'Dashboard' }
  if (session.canAny('inventory.view', 'inventory.adjust')) return { to: '/store-room', label: 'Store room' }
  return { to: '/orders', label: 'Orders' }
})

const tickets = ref<KitchenTicket[]>([])
const station = ref('')
const error = ref('')
const live = ref(false)
const loading = ref(true)
const busyId = ref('')
const now = ref(Date.now())
const showPrep = ref(true)
const prep = ref<{ prep_minutes: number; wait_minutes: number } | null>(null)

const mayWork = computed(() => session.canAny('kitchen.view', 'orders.update', 'pos.use'))
const maySetPrep = computed(() => session.canAny('service.control', 'settings.edit'))

const stations = [
  { id: '', label: 'Everything' },
  { id: 'kitchen', label: 'Kitchen' },
  { id: 'cold', label: 'Cold station' },
  { id: 'bar', label: 'Juice bar' },
]

const columns = [
  { status: 'waiting', label: 'New', next: 'preparing', action: 'Start' },
  { status: 'preparing', label: 'Preparing', next: 'ready', action: 'Ready' },
  { status: 'ready', label: 'Ready for pickup', next: 'served', action: 'Collected' },
]

function inColumn(status: string) {
  return tickets.value.filter((t) => t.status === status)
}

// ---- reading a ticket --------------------------------------------------------
/** "Base: Brown rice | Toppings: A, B" into rows; older tickets have no groups. */
function groups(choices: string) {
  if (!choices) return []
  if (!choices.includes(': ')) return [{ group: '', items: choices }]
  return choices.split(' | ').map((part) => {
    const at = part.indexOf(': ')
    return at < 0 ? { group: '', items: part } : { group: part.slice(0, at), items: part.slice(at + 2) }
  })
}

function isExtra(group: string) {
  const g = group.toLowerCase()
  return g.includes('extra') || g.includes('dip') || g.includes('add')
}

function shortName(name: string) {
  const parts = (name || '').split(/\s+/).filter(Boolean)
  if (!parts.length) return 'Walk-in'
  return `Customer ${parts.map((p) => p[0]!.toUpperCase()).join('.')}.`
}

function placedAt(t: KitchenTicket) {
  return new Date(t.placed_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lusaka' })
}

/** Time since the order was paid, as m:ss, counted in the browser so it keeps moving. */
function elapsed(t: KitchenTicket) {
  const s = Math.max(0, Math.floor((now.value - new Date(t.placed_at).getTime()) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function late(t: KitchenTicket) {
  return t.status !== 'ready' && now.value - new Date(t.placed_at).getTime() >= 15 * 60000
}

// ---- the prep list -------------------------------------------------------------
const prepList = computed(() => {
  const items = new Map<string, number>()
  const byGroup = new Map<string, Map<string, number>>()
  for (const t of tickets.value) {
    if (t.status === 'ready') continue
    for (const i of t.items) {
      if (i.status === 'ready' || i.status === 'served') continue
      items.set(i.product_name, (items.get(i.product_name) ?? 0) + i.quantity)
      for (const g of groups(i.choices)) {
        if (!g.group) continue
        const label = g.group
        const bucket = byGroup.get(label) ?? new Map<string, number>()
        for (const name of g.items.split(', ')) {
          if (!name) continue
          bucket.set(name, (bucket.get(name) ?? 0) + i.quantity)
        }
        byGroup.set(label, bucket)
      }
    }
  }
  const sorted = (m: Map<string, number>) => [...m.entries()].sort((a, b) => b[1] - a[1])
  return [
    { title: 'Items', rows: sorted(items) },
    ...[...byGroup.entries()].map(([title, m]) => ({ title, rows: sorted(m) })),
  ].filter((s) => s.rows.length)
})

// ---- talking to the server ---------------------------------------------------------
async function load() {
  try {
    tickets.value = await api.kitchenTickets(station.value || undefined)
    noticeNew(tickets.value)
    error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the board.'
  } finally {
    loading.value = false
  }
}

async function loadPrep() {
  try {
    prep.value = await api.get('/dashboard/service')
  } catch {
    prep.value = null
  }
}

async function nudgePrep(by: number) {
  if (!prep.value) return
  try {
    prep.value = await api.post('/dashboard/service/prep', {
      minutes: Math.min(120, Math.max(1, prep.value.prep_minutes + by)),
    })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change the time.'
  }
}

// ---- undo ------------------------------------------------------------------
// The last tap can be taken back for eight seconds. This matters most for
// "Collected", which takes the ticket off the wall: without it, a ticket
// tapped by mistake would be gone with no button left to press.
const undo = ref<{ orderId: string; number: string; label: string } | null>(null)
let undoTimer: number | undefined

const STEP_WORDS: Record<string, string> = { preparing: 'started', ready: 'marked ready', served: 'collected' }

async function advance(ticket: KitchenTicket, status: string) {
  busyId.value = ticket.order_id
  try {
    tickets.value = await api.setTicketStatus(ticket.order_id, status)
    error.value = ''
    if (station.value) await load()
    loadPrep()
    window.clearTimeout(undoTimer)
    undo.value = {
      orderId: ticket.order_id,
      number: ticket.order_number.split('-').pop() ?? ticket.order_number,
      label: STEP_WORDS[status] ?? status,
    }
    undoTimer = window.setTimeout(() => (undo.value = null), 8000)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not move that ticket.'
    await load()
  } finally {
    busyId.value = ''
  }
}

async function stepBack(orderId: string) {
  busyId.value = orderId
  try {
    tickets.value = await api.post<KitchenTicket[]>(`/kitchen/tickets/${orderId}/back`)
    error.value = ''
    undo.value = null
    if (station.value) await load()
    loadPrep()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not move that ticket back.'
  } finally {
    busyId.value = ''
  }
}

// ---- the chime ---------------------------------------------------------------
// A browser will only make a sound after someone has tapped the page, so the
// sound is switched on with a button, and the choice is remembered on this
// screen. Drawn with the Web Audio API: there is no sound file to go missing.
const soundOn = ref(false)
let audio: AudioContext | null = null
const seen = new Set<string>()
let firstLoad = true

try {
  soundOn.value = localStorage.getItem('gb-kitchen-sound') === 'on'
} catch {
  /* private window: the switch just starts off */
}

function chime() {
  if (!soundOn.value) return
  try {
    audio = audio ?? new AudioContext()
    if (audio.state === 'suspended') audio.resume()
    const start = audio.currentTime
    // Two notes, a fourth apart: noticeable over a fryer, not alarming.
    for (const [freq, at] of [[880, 0], [1175, 0.16]] as const) {
      const osc = audio.createOscillator()
      const gain = audio.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      gain.gain.setValueAtTime(0.0001, start + at)
      gain.gain.exponentialRampToValueAtTime(0.35, start + at + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + at + 0.45)
      osc.connect(gain).connect(audio.destination)
      osc.start(start + at)
      osc.stop(start + at + 0.5)
    }
  } catch {
    /* no audio on this device; the board still works */
  }
}

function toggleSound() {
  soundOn.value = !soundOn.value
  try {
    localStorage.setItem('gb-kitchen-sound', soundOn.value ? 'on' : 'off')
  } catch {
    /* fine */
  }
  if (soundOn.value) chime() // the tap that switches it on is also the test
}

/** Rings once when tickets appear that this screen has not seen before. */
function noticeNew(list: KitchenTicket[]) {
  let fresh = false
  for (const t of list) {
    if (!seen.has(t.order_id)) {
      seen.add(t.order_id)
      if (!firstLoad && t.status === 'waiting') fresh = true
    }
  }
  firstLoad = false
  if (fresh) chime()
}

let socket: WebSocket | null = null
let poll: number | undefined
let clock: number | undefined
let lastPoll = 0

function connect() {
  const token = getToken()
  if (!token) return
  const base = (import.meta.env.VITE_API_BASE_URL ?? `${location.origin}/api/v1`).replace(/^http/, 'ws')
  try {
    socket = new WebSocket(`${base}/kitchen/ws?token=${encodeURIComponent(token)}`)
  } catch {
    return
  }
  socket.onopen = () => (live.value = true)
  socket.onmessage = (message) => {
    try {
      const data = JSON.parse(message.data)
      if (data.event && data.event !== 'ready') {
        load()
        loadPrep()
      }
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

const clockText = computed(() =>
  new Date(now.value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lusaka' }),
)

onMounted(() => {
  document.body.classList.add('kds-body')
  load()
  loadPrep()
  connect()
  poll = window.setInterval(() => {
    const gap = live.value ? 10000 : 5000
    if (Date.now() - lastPoll >= gap) {
      lastPoll = Date.now()
      load()
      loadPrep()
      if (!socket) connect()
    }
  }, 2500)
  clock = window.setInterval(() => (now.value = Date.now()), 1000)
})

onUnmounted(() => {
  document.body.classList.remove('kds-body')
  window.clearTimeout(undoTimer)
  audio?.close()
  window.clearInterval(poll)
  window.clearInterval(clock)
  socket?.close()
})
</script>

<template>
  <div class="kds">
    <header class="kds-top">
      <h1>Kitchen</h1>
      <span class="state" :class="{ off: !live }">{{ live ? 'Live' : 'Checking every few seconds' }}</span>
      <div class="kds-actions">
        <div class="stations">
          <button
            v-for="s in stations"
            :key="s.id"
            :class="{ on: station === s.id }"
            @click="station = s.id; load()"
          >{{ s.label }}</button>
        </div>
        <button class="plain sound" :class="{ on: soundOn }" :aria-pressed="soundOn" @click="toggleSound">
          {{ soundOn ? 'Sound on' : 'Sound off' }}
        </button>
        <button class="plain" @click="showPrep = !showPrep">{{ showPrep ? 'Hide prep list' : 'Show prep list' }}</button>
        <span class="clock">{{ clockText }}</span>
        <RouterLink :to="away.to" class="plain">{{ away.label }}</RouterLink>
      </div>
    </header>

    <section v-if="prep" class="service">
      <span class="dot" />
      <div class="service-text">
        <b>Kitchen open</b>
        <span>Customers at the counter are told “ready in about {{ prep.wait_minutes }} min”</span>
      </div>
      <div class="prep-time">
        <span>Base prep time</span>
        <div class="stepper">
          <button :disabled="!maySetPrep" aria-label="Less time" @click="nudgePrep(-1)">−</button>
          <b>{{ prep.prep_minutes }} min</b>
          <button :disabled="!maySetPrep" aria-label="More time" @click="nudgePrep(1)">+</button>
        </div>
      </div>
    </section>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="loading">Loading…</p>

    <div v-if="undo" class="undo" role="status">
      <span>#{{ undo.number }} {{ undo.label }}.</span>
      <button :disabled="busyId === undo.orderId" @click="stepBack(undo.orderId)">Undo</button>
    </div>

    <div v-else class="board" :class="{ noprep: !showPrep }">
      <aside v-if="showPrep" class="preplist">
        <h2>To make now</h2>
        <p v-if="!prepList.length" class="quiet">Nothing waiting.</p>
        <section v-for="s in prepList" :key="s.title">
          <h3>{{ s.title }}</h3>
          <div v-for="[name, n] in s.rows" :key="name" class="prow">
            <span>{{ name }}</span><b>{{ n }}</b>
          </div>
        </section>
      </aside>

      <section v-for="col in columns" :key="col.status" class="column">
        <header>
          <h2>{{ col.label }}</h2>
          <span class="count">{{ inColumn(col.status).length }}</span>
        </header>

        <article
          v-for="t in inColumn(col.status)"
          :key="t.order_id"
          class="ticket"
          :class="{ late: late(t) }"
        >
          <div class="ticket-head">
            <b class="num">#{{ t.order_number.split('-').pop() }}</b>
            <span class="timer">{{ elapsed(t) }}</span>
          </div>
          <p class="who">
            {{ shortName(t.customer_name) }}, placed {{ placedAt(t) }}
            <template v-if="t.order_type !== 'takeaway'"> · {{ { eat_in: 'Eat in', delivery: 'Delivery' }[t.order_type] ?? t.order_type }}</template>
          </p>
          <div v-for="i in t.items" :key="i.id" class="item" :class="i.status">
            <p class="item-name"><span class="qty">{{ i.quantity }}×</span> {{ i.product_name }}</p>
            <dl v-if="i.choices">
              <template v-for="g in groups(i.choices)" :key="g.group + g.items">
                <dt>{{ g.group.toLowerCase() }}</dt>
                <dd :class="{ extra: isExtra(g.group) }">{{ g.items }}</dd>
              </template>
            </dl>
            <p v-if="i.note" class="note">{{ i.note }}</p>
          </div>
          <div v-if="mayWork" class="ticket-acts">
            <button
              v-if="col.status !== 'waiting'"
              class="back"
              :disabled="busyId === t.order_id"
              :aria-label="`Move ${t.order_number} back a step`"
              title="Back a step"
              @click="stepBack(t.order_id)"
            >↶</button>
            <button
              class="go"
              :disabled="busyId === t.order_id"
              @click="advance(t, col.next)"
            >{{ col.action }}</button>
          </div>
        </article>
      </section>
    </div>
  </div>
</template>

<style>
/* The board fills the whole screen in the kitchen's own colour. */
body.kds-body { background: var(--forest); }
</style>

<style scoped>
.kds { min-height: 100vh; background: var(--forest); color: #f6f3ec; padding: 1rem max(1.5rem, env(safe-area-inset-left, 0px)) 2rem; }
.kds-top { display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; padding: .4rem 0 1rem; }
.kds-top h1 { color: #f6f3ec; font-weight: 900; font-size: 2rem; margin: 0; }
.state { padding: .2rem .65rem; border-radius: 999px; background: var(--sprout); color: #0f2a14; font-weight: 800; font-size: .8rem; }
.state.off { background: rgba(246, 243, 236, .2); color: #f6f3ec; }
.kds-actions { margin-left: auto; display: flex; align-items: center; gap: 1.2rem; flex-wrap: wrap; }
.stations { display: flex; gap: .3rem; flex-wrap: wrap; }
.stations button { background: transparent; border: 1.5px solid rgba(246, 243, 236, .3); color: #f6f3ec; padding: .3rem .8rem; border-radius: 999px; font-weight: 700; font-size: .85rem; }
.stations button.on { background: var(--sprout); color: #0f2a14; border-color: var(--sprout); }
.plain { background: none; border: 0; color: #f6f3ec; font-weight: 700; text-decoration: none; padding: .2rem; }
.clock { font-family: var(--display); font-weight: 800; font-size: 1.6rem; font-variant-numeric: tabular-nums; }

.service { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; background: rgba(255, 255, 255, .06); border: 1px solid rgba(255, 255, 255, .1); border-radius: 18px; padding: .9rem 1.2rem; margin-bottom: 1rem; }
.dot { width: 12px; height: 12px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 4px rgba(63, 191, 90, .25); flex: none; }
.service-text { display: grid; flex: 1 1 260px; min-width: 0; }
.service-text span { color: rgba(246, 243, 236, .75); font-size: .92rem; }
.prep-time { display: grid; gap: .25rem; color: rgba(246, 243, 236, .75); font-size: .88rem; }
.stepper { display: flex; align-items: center; gap: .6rem; }
.stepper b { color: #fff; font-size: 1rem; min-width: 4.2ch; text-align: center; }
.stepper button { width: 32px; height: 32px; border-radius: 50%; border: 0; background: #fff; color: #0f2a14; font-weight: 900; font-size: 1.1rem; padding: 0; }

.error { background: var(--danger-soft); color: var(--danger); padding: .7rem 1rem; border-radius: 12px; }
.loading { color: rgba(246, 243, 236, .75); }

.board { display: grid; grid-template-columns: 240px repeat(3, minmax(0, 1fr)); gap: 1rem; align-items: start; }
.board.noprep { grid-template-columns: repeat(3, minmax(0, 1fr)); }

.preplist { background: var(--paper); color: var(--ink); border-radius: 18px; padding: 1rem 1rem .6rem; position: sticky; top: 1rem; }
.preplist h2 { color: var(--brown); font-size: 1.1rem; margin: 0 0 .5rem; padding-bottom: .5rem; border-bottom: 1px solid var(--line); }
.preplist h3 { color: var(--green-deep); font-family: var(--body); font-weight: 800; font-size: .82rem; margin: .7rem 0 .25rem; }
.preplist section { padding-bottom: .5rem; border-bottom: 1px solid var(--line); }
.preplist section:last-child { border-bottom: 0; }
.prow { display: flex; justify-content: space-between; gap: .6rem; font-size: .93rem; padding: .08rem 0; }
.prow b { font-variant-numeric: tabular-nums; }
.quiet { color: var(--muted); }

.column { background: rgba(255, 255, 255, .06); border-radius: 18px; padding: .9rem; min-height: 260px; }
.column > header { display: flex; align-items: center; gap: .5rem; margin-bottom: .8rem; }
.column h2 { color: #f6f3ec; font-size: 1.15rem; margin: 0; }
.count { background: var(--sprout); color: #0f2a14; border-radius: 999px; padding: 0 .5rem; font-weight: 800; font-size: .85rem; }

.ticket, .undo {
  /* Tickets are light cards on the board's dark green in both themes, so they
     carry the light theme's colours rather than the screen's. */
  --ink: #18201A; --muted: #5D665E; --line: #E1E5DC; --green: #1F8A3B; --green-deep: #136B2C; --green-ink: #FFFFFF;
  --brown: #5C4038; --paper: #FFFFFF; --danger: #B3261E; --warn: #8A5A00; --kraft-ink: #74552F;
}
.ticket { background: #fbf9f3; color: var(--ink); border-radius: 14px; padding: 1rem 1rem .9rem; margin-bottom: .9rem; border-top: 8px solid var(--green); }
.ticket.late { border-top-color: var(--danger); }
.ticket-head { display: flex; justify-content: space-between; align-items: baseline; }
.ticket-head .num { font-family: var(--display); font-weight: 900; font-size: 1.6rem; color: var(--brown); }
.timer { font-family: var(--display); font-weight: 800; font-size: 1.2rem; font-variant-numeric: tabular-nums; }
.ticket.late .timer { color: var(--danger); }
.who { color: var(--muted); margin: .4rem 0 .6rem; padding-bottom: .6rem; border-bottom: 1px solid var(--line); font-size: .93rem; }
.item { padding: .5rem 0; border-bottom: 1px solid var(--line); }
.item:last-of-type { border-bottom: 0; }
.item.ready .item-name, .item.served .item-name { text-decoration: line-through; opacity: .55; }
.item-name { margin: 0 0 .3rem; font-weight: 800; font-size: 1.05rem; }
.qty { color: var(--green-deep); }
dl { display: grid; grid-template-columns: auto 1fr; gap: .15rem .9rem; margin: 0; font-size: .95rem; }
dt { color: var(--muted); font-weight: 700; font-size: .82rem; padding-top: .15rem; }
dd { margin: 0; }
dd.extra { color: #A35A00; font-weight: 700; }
.note { margin: .3rem 0 0; color: #A35A00; font-weight: 700; }
.ticket-acts { display: flex; gap: .5rem; margin-top: .7rem; }
.go { flex: 1; min-height: 52px; border-radius: 999px; border: 0; background: var(--green); color: var(--green-ink); font-weight: 800; font-size: 1.05rem; }
.back { width: 52px; min-height: 52px; flex: none; border-radius: 999px; border: 2px solid var(--line); background: transparent; color: var(--muted); font-size: 1.3rem; font-weight: 800; }
.back:hover:not([disabled]) { border-color: var(--muted); color: var(--ink); }
.sound { border: 1.5px solid rgba(246, 243, 236, .3) !important; border-radius: 999px; padding: .3rem .8rem !important; }
.sound.on { background: var(--sprout); color: #0f2a14; border-color: var(--sprout) !important; }
.undo {
  position: fixed; left: 50%; bottom: max(1.2rem, env(safe-area-inset-bottom, 0px)); transform: translateX(-50%);
  z-index: 30; display: flex; align-items: center; gap: 1rem;
  background: #fbf9f3; color: var(--ink); border-radius: 999px; padding: .55rem .6rem .55rem 1.2rem;
  box-shadow: 0 12px 30px rgba(0, 0, 0, .35); font-weight: 700;
}
.undo button { border: 0; border-radius: 999px; background: var(--forest); color: #fff; font-weight: 800; padding: .5rem 1.1rem; }
.go:hover:not([disabled]) { background: var(--green-deep); }

@media (max-width: 1100px) {
  .board, .board.noprep { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .preplist { position: static; }
}
@media (max-width: 680px) {
  .board, .board.noprep { grid-template-columns: minmax(0, 1fr); }
  .kds-actions { margin-left: 0; }
}
</style>
