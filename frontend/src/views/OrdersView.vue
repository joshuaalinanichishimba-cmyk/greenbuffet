<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type DayTotals, type Order, type Receipt } from '../services/api'
import { kwacha } from '../services/money'
import { session } from '../stores/session'

const orders = ref<Order[]>([])
const totals = ref<DayTotals | null>(null)
const receipt = ref<Receipt | null>(null)
const statusFilter = ref('')
const loading = ref(true)
const error = ref('')
const busyId = ref('')

const mayCancel = computed(() => session.can('orders.cancel'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [o, t] = await Promise.all([
      api.orders({ status: statusFilter.value || undefined }),
      api.todayTotals(),
    ])
    orders.value = o
    totals.value = t
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load today’s orders.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

function when(iso: string) {
  return new Date(iso).toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lusaka',
  })
}

async function show(order: Order) {
  error.value = ''
  try {
    receipt.value = await api.receipt(order.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not open the receipt.'
  }
}

async function cancel(order: Order) {
  const reason = window.prompt(`Why is ${order.number} being cancelled?`)
  if (!reason || reason.trim().length < 3) return
  busyId.value = order.id
  error.value = ''
  try {
    await api.cancelOrder(order.id, reason.trim())
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not cancel that order.'
  } finally {
    busyId.value = ''
  }
}

async function refund(order: Order) {
  const typed = window.prompt(
    `How much is being given back on ${order.number}? Up to ${kwacha(order.paid_ngwee)}`,
    (order.paid_ngwee / 100).toFixed(2),
  )
  if (typed === null) return
  const reason = window.prompt('Why?')
  if (!reason || reason.trim().length < 3) return
  const amount = Math.round(Number(typed.replace(/[^\d.]/g, '')) * 100)
  if (!Number.isFinite(amount) || amount <= 0) {
    error.value = 'That is not an amount.'
    return
  }
  busyId.value = order.id
  error.value = ''
  try {
    await api.refundOrder(order.id, { method: 'cash', amount_ngwee: amount, reason: reason.trim() })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not record that refund.'
  } finally {
    busyId.value = ''
  }
}
</script>

<template>
  <AppShell>
    <h1>Today's orders</h1>
    <p class="lead">
      Everything the till has taken today, newest first. An order that was paid cannot be edited;
      give a refund and the money shows against the same order.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="totals" class="cards">
      <article class="card">
        <b>{{ totals.orders }}</b>
        <span>Orders paid</span>
      </article>
      <article class="card">
        <b>{{ kwacha(totals.sales_ngwee) }}</b>
        <span>Taken today</span>
      </article>
      <article class="card">
        <b>{{ kwacha(totals.vat_ngwee) }}</b>
        <span>VAT inside that</span>
      </article>
      <article v-if="totals.refunds_ngwee" class="card warn">
        <b>{{ kwacha(totals.refunds_ngwee) }}</b>
        <span>Refunded</span>
      </article>
    </section>

    <p v-if="totals?.by_method.length" class="muted methods">
      {{ totals.by_method.map((m) => `${m.label} ${kwacha(m.amount_ngwee)}`).join(' · ') }}
    </p>

    <label class="field filter">
      Show
      <select v-model="statusFilter" @change="load">
        <option value="">Everything</option>
        <option value="paid">Paid</option>
        <option value="open">Not yet paid</option>
        <option value="cancelled">Cancelled</option>
      </select>
    </label>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!orders.length" class="muted">Nothing yet today.</p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Order</th>
            <th>Time</th>
            <th>Items</th>
            <th>Total</th>
            <th>Paid by</th>
            <th>State</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <td>
              <b>{{ o.number }}</b>
              <small v-if="o.customer_name" class="muted">{{ o.customer_name }}</small>
            </td>
            <td>{{ when(o.created_at) }}</td>
            <td class="items">
              {{ o.lines.map((l) => `${l.quantity}× ${l.product_name}`).join(', ') }}
            </td>
            <td class="num">{{ kwacha(o.total_ngwee) }}</td>
            <td>
              <template v-if="o.payments.length">
                {{ o.payments.filter((p) => !p.is_refund).map((p) => p.label).join(' + ') }}
              </template>
              <small v-else class="muted">not paid</small>
            </td>
            <td>
              <span v-if="o.status === 'paid'" class="tag">Paid</span>
              <span v-else-if="o.status === 'cancelled'" class="tag off">Cancelled</span>
              <span v-else class="tag off">{{ kwacha(o.outstanding_ngwee) }} owing</span>
            </td>
            <td class="actions">
              <button class="btn-quiet btn-small" @click="show(o)">Receipt</button>
              <button
                v-if="mayCancel && o.status === 'paid'"
                class="btn-quiet btn-small"
                :disabled="busyId === o.id"
                @click="refund(o)"
              >
                Refund
              </button>
              <button
                v-if="mayCancel && o.status === 'open'"
                class="btn-quiet btn-small"
                :disabled="busyId === o.id"
                @click="cancel(o)"
              >
                Cancel
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="receipt" class="backdrop" @click.self="receipt = null">
      <section class="panel slip">
        <header>
          <b>{{ receipt.number }}</b>
          <button class="btn-quiet btn-small" @click="receipt = null">Close</button>
        </header>
        <p class="muted">{{ receipt.at }} · {{ receipt.order_type }} · served by {{ receipt.served_by }}</p>
        <ul class="slip-lines">
          <li v-for="(line, i) in receipt.lines" :key="i">
            <span>{{ line.quantity }} × {{ line.name }}
              <small v-if="line.options.length">{{ line.options.join(', ') }}</small>
            </span>
            <b>{{ kwacha(line.total_ngwee) }}</b>
          </li>
        </ul>
        <dl class="totals">
          <div v-if="receipt.discount_ngwee"><dt>Discount</dt><dd>−{{ kwacha(receipt.discount_ngwee) }}</dd></div>
          <div class="grand"><dt>Total</dt><dd>{{ kwacha(receipt.total_ngwee) }}</dd></div>
          <div v-for="(p, i) in receipt.payments" :key="i">
            <dt>{{ p.is_refund ? 'Refund' : p.label }}<small v-if="p.reference"> {{ p.reference }}</small></dt>
            <dd>{{ kwacha(p.amount_ngwee) }}</dd>
          </div>
          <div v-if="receipt.change_ngwee"><dt>Change</dt><dd>{{ kwacha(receipt.change_ngwee) }}</dd></div>
          <div><dt>VAT included</dt><dd>{{ kwacha(receipt.vat_ngwee) }}</dd></div>
        </dl>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.8rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 0.8rem 1rem; display: grid; gap: 0.1rem; }
.card b { font-size: 1.3rem; }
.card span { font-size: 0.8rem; color: var(--muted); }
.card.warn b { color: #9a6700; }
.methods { margin: 0.6rem 0 0; }
.filter { max-width: 220px; margin: 1rem 0; }
.num { white-space: nowrap; }
.items { max-width: 22rem; font-size: 0.86rem; }
td small { display: block; font-size: 0.76rem; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }
.backdrop { position: fixed; inset: 0; background: rgba(12, 30, 16, 0.45); display: grid; place-items: center; padding: 1rem; z-index: 20; }
.slip { max-width: 420px; width: 100%; max-height: 86vh; overflow-y: auto; }
.slip header { display: flex; justify-content: space-between; align-items: center; }
.slip-lines { list-style: none; margin: 0.8rem 0; padding: 0; display: grid; gap: 0.4rem; }
.slip-lines li { display: flex; justify-content: space-between; gap: 0.8rem; border-bottom: 1px solid var(--line); padding-bottom: 0.35rem; }
.slip-lines small { display: block; color: var(--muted); font-size: 0.78rem; }
.totals { margin: 0; display: grid; gap: 0.2rem; }
.totals > div { display: flex; justify-content: space-between; }
.totals dt, .totals dd { margin: 0; font-size: 0.9rem; }
.totals .grand dt, .totals .grand dd { font-weight: 800; font-size: 1.05rem; }
</style>
