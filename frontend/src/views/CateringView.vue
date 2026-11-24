<!--
  Functions: quoted, confirmed with a deposit, delivered, then settled.

  The money rule this screen exists to enforce is that a deposit is not a
  sale. It is money held for a job not yet done, and it only becomes income
  on the day the food is delivered. The buttons here follow that order and
  will not let anyone skip it.
-->
<template>
  <AppShell>
    <h1>Functions and catering</h1>
    <p class="lead">
      A quote, then a deposit to confirm it, then the food, then the balance.
      Deposits are held in the books until the day of the function.
    </p>

    <div class="stat-row">
      <div class="stat"><span class="value">{{ counts.confirmed }}</span><span class="label">Confirmed</span></div>
      <div class="stat"><span class="value">{{ counts.quoted }}</span><span class="label">Waiting on a deposit</span></div>
      <div class="stat good"><span class="value">{{ kwacha(held) }}</span><span class="label">Deposits held</span></div>
      <div class="stat warn"><span class="value">{{ kwacha(owed) }}</span><span class="label">Owed after delivery</span></div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <div class="row" style="margin-bottom: 1rem">
      <button class="btn-primary" @click="startNew">Take a booking</button>
      <div class="tabs" style="margin: 0 0 0 auto">
        <button :class="{ on: filter === '' }" @click="setFilter('')">All</button>
        <button :class="{ on: filter === 'quoted' }" @click="setFilter('quoted')">Quoted</button>
        <button :class="{ on: filter === 'confirmed' }" @click="setFilter('confirmed')">Confirmed</button>
        <button :class="{ on: filter === 'delivered' }" @click="setFilter('delivered')">Delivered</button>
      </div>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="!bookings.length" class="empty">No functions booked yet.</div>

    <div v-for="booking in bookings" :key="booking.id" class="panel" style="margin-bottom: 0.8rem">
      <div class="spread">
        <div style="min-width: 0">
          <strong style="font-size: 1.05rem">{{ booking.customer_name }}</strong>
          <span class="tag" :class="tagFor(booking.status)" style="margin-left: 0.5rem">
            {{ booking.status }}
          </span>
          <div class="muted">
            {{ booking.number }}
            <template v-if="booking.event_date"> · {{ day(booking.event_date) }}</template>
            <template v-if="booking.guests"> · {{ booking.guests }} guests</template>
            <template v-if="booking.venue"> · {{ booking.venue }}</template>
          </div>
        </div>
        <div style="text-align: right">
          <strong style="font-size: 1.1rem">{{ kwacha(booking.quote_ngwee) }}</strong>
          <div class="muted">
            paid {{ kwacha(booking.deposit_paid_ngwee + booking.settled_ngwee) }}
            <template v-if="booking.balance_ngwee > 0">· {{ kwacha(booking.balance_ngwee) }} left</template>
          </div>
        </div>
      </div>
      <p v-if="booking.details" class="muted" style="margin: 0.5rem 0 0">{{ booking.details }}</p>

      <div class="row" style="margin-top: 0.8rem">
        <button
          v-if="booking.status === 'quoted' || booking.status === 'enquiry' || booking.status === 'confirmed'"
          class="btn-primary btn-small"
          @click="startDeposit(booking)"
        >
          Take a deposit
        </button>
        <button
          v-if="booking.status === 'confirmed'"
          class="btn-quiet btn-small"
          @click="deliver(booking)"
        >
          The function happened
        </button>
        <button
          v-if="booking.status === 'delivered' && booking.balance_ngwee > 0"
          class="btn-primary btn-small"
          @click="startSettle(booking)"
        >
          Take the balance
        </button>
        <span v-if="booking.status === 'delivered' && booking.balance_ngwee === 0" class="tag">Settled</span>
      </div>
    </div>

    <!-- a new booking -->
    <div v-if="making" class="sheet-back" @click.self="making = false">
      <div class="sheet">
        <div class="sheet-head">
          <h2>Take a booking</h2>
          <button class="btn-quiet btn-small" @click="making = false">Close</button>
        </div>
        <div class="grid-2">
          <label class="field">Who is it for<input v-model="form.customer_name" type="text" maxlength="80" /></label>
          <label class="field">Phone<input v-model="form.customer_phone" type="tel" maxlength="24" /></label>
          <label class="field">Date<input v-model="form.event_date" type="datetime-local" /></label>
          <label class="field">Guests<input v-model.number="form.guests" type="number" min="0" /></label>
        </div>
        <label class="field" style="margin-top: 0.7rem">
          Where
          <input v-model="form.venue" type="text" maxlength="200" />
        </label>
        <label class="field" style="margin-top: 0.7rem">
          What they want
          <textarea v-model="form.details" maxlength="4000" placeholder="Buffet for fifty: rice, chicken, two salads…" />
        </label>
        <div class="grid-2" style="margin-top: 0.7rem">
          <label class="field">
            Quote (kwacha)
            <input v-model="quoteKwacha" type="number" min="0" step="0.01" />
          </label>
          <label class="field">
            Deposit to confirm (kwacha)
            <input v-model="depositKwacha" type="number" min="0" step="0.01" />
          </label>
        </div>
        <p class="muted">Leave the deposit blank and half the quote is asked for.</p>
        <div class="row end" style="margin-top: 1rem">
          <button class="btn-quiet" @click="making = false">Cancel</button>
          <button class="btn-primary" @click="saveBooking">Save the booking</button>
        </div>
      </div>
    </div>

    <!-- taking money -->
    <div v-if="paying" class="sheet-back" @click.self="paying = null">
      <div class="sheet">
        <h2>{{ payingMode === 'deposit' ? 'Deposit' : 'Balance' }} for {{ paying.number }}</h2>
        <p class="muted">
          {{ paying.customer_name }} ·
          {{ payingMode === 'deposit' ? `asked for ${kwacha(paying.deposit_due_ngwee)}` : `${kwacha(paying.balance_ngwee)} owing` }}
        </p>
        <div class="grid-2" style="margin-top: 0.8rem">
          <label class="field">
            Amount (kwacha)
            <input v-model="payKwacha" type="number" min="0" step="0.01" />
          </label>
          <label class="field">
            How they paid
            <select v-model="payMethod">
              <option value="cash">Cash</option>
              <option value="airtel">Airtel Money</option>
              <option value="mtn">MTN MoMo</option>
              <option value="zamtel">Zamtel Kwacha</option>
              <option value="card">Card</option>
            </select>
          </label>
        </div>
        <div class="row end" style="margin-top: 1rem">
          <button class="btn-quiet" @click="paying = null">Cancel</button>
          <button class="btn-primary" @click="takeMoney">Record it</button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api } from '../services/api'
import { kwacha, toNgwee } from '../services/money'

interface Booking {
  id: string
  number: string
  status: string
  customer_name: string
  customer_phone: string
  event_date: string
  guests: number
  venue: string
  details: string
  quote_ngwee: number
  deposit_due_ngwee: number
  deposit_paid_ngwee: number
  settled_ngwee: number
  balance_ngwee: number
  created_by: string
  created_at: string
}

const bookings = ref<Booking[]>([])
const loading = ref(true)
const error = ref('')
const note = ref('')
const filter = ref('')

const making = ref(false)
const form = reactive({
  customer_name: '',
  customer_phone: '',
  event_date: '',
  guests: 0,
  venue: '',
  details: '',
})
const quoteKwacha = ref('')
const depositKwacha = ref('')

const paying = ref<Booking | null>(null)
const payingMode = ref<'deposit' | 'settle'>('deposit')
const payKwacha = ref('')
const payMethod = ref('cash')

const counts = computed(() => ({
  quoted: bookings.value.filter((b) => b.status === 'quoted' || b.status === 'enquiry').length,
  confirmed: bookings.value.filter((b) => b.status === 'confirmed').length,
}))
const held = computed(() =>
  bookings.value
    .filter((b) => b.status === 'confirmed')
    .reduce((sum, b) => sum + b.deposit_paid_ngwee, 0),
)
const owed = computed(() =>
  bookings.value.filter((b) => b.status === 'delivered').reduce((sum, b) => sum + b.balance_ngwee, 0),
)

function tagFor(state: string) {
  if (state === 'confirmed') return ''
  if (state === 'delivered') return 'info'
  if (state === 'cancelled') return 'bad'
  return 'warn'
}

function day(when: string) {
  return when ? new Date(when).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : ''
}

async function load() {
  try {
    bookings.value = await api.get<Booking[]>(`/customers/bookings?state=${filter.value}`)
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load bookings.'
  } finally {
    loading.value = false
  }
}

function setFilter(value: string) {
  filter.value = value
  loading.value = true
  load()
}

function startNew() {
  making.value = true
  form.customer_name = ''
  form.customer_phone = ''
  form.event_date = ''
  form.guests = 0
  form.venue = ''
  form.details = ''
  quoteKwacha.value = ''
  depositKwacha.value = ''
}

async function saveBooking() {
  try {
    await api.post('/customers/bookings', {
      ...form,
      event_date: form.event_date ? new Date(form.event_date).toISOString() : null,
      quote_ngwee: toNgwee(quoteKwacha.value || '0'),
      deposit_due_ngwee: toNgwee(depositKwacha.value || '0'),
    })
    making.value = false
    note.value = 'Booking saved.'
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not save the booking.'
  }
}

function startDeposit(booking: Booking) {
  paying.value = booking
  payingMode.value = 'deposit'
  payKwacha.value = String((booking.deposit_due_ngwee - booking.deposit_paid_ngwee) / 100)
  payMethod.value = 'cash'
}

function startSettle(booking: Booking) {
  paying.value = booking
  payingMode.value = 'settle'
  payKwacha.value = String(booking.balance_ngwee / 100)
  payMethod.value = 'cash'
}

async function takeMoney() {
  const booking = paying.value
  if (!booking) return
  const path = payingMode.value === 'deposit' ? 'deposit' : 'settle'
  try {
    await api.post(`/customers/bookings/${booking.id}/${path}`, {
      amount_ngwee: toNgwee(payKwacha.value || '0'),
      method: payMethod.value,
    })
    paying.value = null
    note.value = payingMode.value === 'deposit' ? 'Deposit recorded and held in the books.' : 'Balance recorded.'
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not record that.'
  }
}

async function deliver(booking: Booking) {
  try {
    await api.post(`/customers/bookings/${booking.id}/delivered`, {})
    note.value = 'The deposit has become a catering sale and the rest is owed.'
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not mark it delivered.'
  }
}

onMounted(load)
</script>
