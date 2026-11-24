<!--
  Orders, as the demo's Orders screen lists them.

  The tabs follow an order's life: Active is everything not yet in a
  customer's hands, then what was collected, what was cancelled, and the
  last fourteen days. Each row carries the one next step for that order, the
  same step the kitchen display would take, so the counter can move an order
  along without walking to the kitchen screen.

  A paid order is never edited. Money goes back as a refund, recorded against
  the same order, and the books follow.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import { ApiError, api, type Receipt } from '../services/api'
import { kwacha, kwachaShort, toNgwee } from '../services/money'
import { session } from '../stores/session'
import ManagerApproval from '../components/ManagerApproval.vue'

interface Row {
  id: string; number: string; placed: string; customer: string; phone: string
  items: string; total_ngwee: number; payment: string; paid: boolean
  state: string; state_label: string; order_type: string
}

const route = useRoute()
const router = useRouter()

const tabs = [
  { v: 'active', label: 'Active' },
  { v: 'today', label: 'All today' },
  { v: 'collected', label: 'Collected' },
  { v: 'cancelled', label: 'Cancelled' },
  { v: 'days14', label: 'Last 14 days' },
]

const view = ref('active')
const search = ref(String(route.query.q ?? ''))
const rows = ref<Row[]>([])
const loading = ref(true)
const error = ref('')
const note = ref('')
const busy = ref('')
const receipt = ref<Receipt | null>(null)

const mayCancel = computed(() => session.can('orders.cancel'))
// A cashier can ask for a refund; a manager approves it on the spot.
const mayAskRefund = computed(() => session.canAny('orders.cancel', 'refunds.request'))
const approving = reactive<{ open: boolean; error: string; what: string }>({ open: false, error: '', what: '' })
const mayMove = computed(() => session.canAny('kitchen.view', 'orders.update', 'pos.use'))

const total = computed(() => rows.value.filter((r) => r.paid).reduce((s, r) => s + r.total_ngwee, 0))

async function load() {
  error.value = ''
  try {
    const q = search.value.trim()
    rows.value = await api.get<Row[]>(
      `/dashboard/orders?view=${view.value}${q ? `&q=${encodeURIComponent(q)}` : ''}`,
    )
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the orders.'
  } finally {
    loading.value = false
  }
}

function pick(v: string) {
  view.value = v
  if (search.value) {
    search.value = ''
    router.replace({ path: '/orders' })
  }
  loading.value = true
  load()
}

// A search from the top bar lands here with ?q=.
watch(
  () => route.query.q,
  (q) => {
    search.value = String(q ?? '')
    load()
  },
)

const NEXT: Record<string, { status: string; label: string } | undefined> = {
  received: { status: 'preparing', label: 'Start preparing' },
  preparing: { status: 'ready', label: 'Mark ready' },
  ready: { status: 'served', label: 'Mark collected' },
}

async function advance(row: Row) {
  const step = NEXT[row.state]
  if (!step) return
  busy.value = row.id
  try {
    await api.post(`/kitchen/tickets/${row.id}/status`, { status: step.status })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not move that order on.'
  } finally {
    busy.value = ''
  }
}

async function show(row: Row) {
  try {
    // Opening a receipt here is a reprint, and is recorded as one.
    receipt.value = await api.get<Receipt>(`/sales/orders/${row.id}/receipt?reprint=true`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not open the receipt.'
  }
}

// ---- cancelling and refunding, in the page rather than a browser prompt --
const acting = ref<{ row: Row; kind: 'cancel' | 'refund' } | null>(null)
const reason = ref('')
const amount = ref('')

function startCancel(row: Row) {
  acting.value = { row, kind: 'cancel' }
  reason.value = ''
}

function startRefund(row: Row) {
  acting.value = { row, kind: 'refund' }
  reason.value = ''
  amount.value = (row.total_ngwee / 100).toFixed(2)
}

async function confirm(approval?: { email: string; password: string }) {
  const a = acting.value
  if (!a) return
  if (reason.value.trim().length < 3) {
    error.value = 'Say why, in a few words.'
    return
  }
  busy.value = a.row.id
  try {
    if (a.kind === 'cancel') {
      await api.cancelOrder(a.row.id, reason.value.trim())
      note.value = `${a.row.number} cancelled.`
    } else {
      const ngwee = toNgwee(amount.value)
      if (!ngwee) {
        error.value = 'That is not an amount.'
        return
      }
      await api.refundOrder(a.row.id, {
        method: 'cash', amount_ngwee: ngwee, reason: reason.value.trim(), approval: approval ?? null,
      })
      approving.open = false
      note.value = `${kwacha(ngwee)} refunded on ${a.row.number}.`
    }
    acting.value = null
    await load()
  } catch (e) {
    if (e instanceof ApiError && e.status === 403 && /approv/i.test(e.message)) {
      if (approval) approving.error = e.message
      else Object.assign(approving, { open: true, error: '', what: e.message })
    } else {
      error.value = e instanceof ApiError ? e.message : 'That did not go through.'
    }
  } finally {
    busy.value = ''
  }
}

let timer: number | undefined
onMounted(() => {
  load()
  timer = window.setInterval(() => {
    if (!search.value) load()
  }, 20000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <PageHead
      title="Orders"
      :lead="search ? `Orders matching “${search}”.` : 'Every order from the till, newest first. Move one along here or on the kitchen display.'"
    >
      <RouterLink v-if="session.can('pos.use')" to="/till" class="btn-primary">New order</RouterLink>
    </PageHead>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <div class="bar-row">
      <div class="tabs" style="margin: 0">
        <button v-for="t in tabs" :key="t.v" :class="{ on: view === t.v && !search }" @click="pick(t.v)">{{ t.label }}</button>
      </div>
      <span class="muted">{{ rows.length }} orders · {{ kwachaShort(total) }} paid</span>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="!rows.length" class="empty">
      {{ search ? 'No order matches that.' : view === 'active' ? 'Nothing waiting. Every order has been handed over.' : 'No orders here.' }}
    </div>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Order</th>
            <th>Placed</th>
            <th>Customer</th>
            <th class="hide-small">Items</th>
            <th class="num">Total</th>
            <th class="hide-small">Payment</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td><b>{{ r.number }}</b></td>
            <td class="muted tnum">{{ r.placed }}</td>
            <td>{{ r.customer }}</td>
            <td class="hide-small items">{{ r.items }}</td>
            <td class="num"><b>{{ kwacha(r.total_ngwee) }}</b></td>
            <td class="hide-small">{{ r.payment }}</td>
            <td><span class="status" :class="r.state">{{ r.state_label }}</span></td>
            <td class="acts">
              <button
                v-if="mayMove && NEXT[r.state]"
                class="btn-primary btn-small"
                :disabled="busy === r.id"
                @click="advance(r)"
              >{{ NEXT[r.state]!.label }}</button>
              <RouterLink v-else-if="r.state === 'awaiting_payment' && session.can('pos.use')" to="/till" class="btn-outline btn-small">Take payment</RouterLink>
              <button class="btn-quiet btn-small" @click="show(r)">Receipt</button>
              <button v-if="mayAskRefund && r.paid" class="btn-quiet btn-small" :disabled="busy === r.id" @click="startRefund(r)">Refund</button>
              <button v-if="mayCancel && r.state === 'awaiting_payment'" class="btn-quiet btn-small" :disabled="busy === r.id" @click="startCancel(r)">Cancel</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- the receipt -->
    <div v-if="receipt" class="sheet-back" @click.self="receipt = null">
      <section class="sheet slip">
        <div class="sheet-head">
          <div>
            <h2>{{ receipt.number }}</h2>
            <p class="muted">{{ receipt.at }} · {{ receipt.order_type }} · served by {{ receipt.served_by }}</p>
          </div>
          <button class="btn-quiet btn-small" @click="receipt = null">Close</button>
        </div>
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
          <div v-if="receipt.vat_ngwee"><dt>VAT included</dt><dd>{{ kwacha(receipt.vat_ngwee) }}</dd></div>
        </dl>
      </section>
    </div>

    <!-- cancel or refund -->
    <div v-if="acting" class="sheet-back" @click.self="acting = null">
      <section class="sheet">
        <h2>{{ acting.kind === 'cancel' ? `Cancel ${acting.row.number}?` : `Refund on ${acting.row.number}` }}</h2>
        <p class="muted">{{ acting.row.customer }} · {{ acting.row.items }}</p>
        <label v-if="acting.kind === 'refund'" class="field" style="margin-top: .9rem">
          Amount to give back (up to {{ kwacha(acting.row.total_ngwee) }})
          <input v-model="amount" type="text" inputmode="decimal" />
        </label>
        <label class="field" style="margin-top: .9rem">
          Why
          <input v-model="reason" type="text" maxlength="200" placeholder="Customer changed their mind" />
        </label>
        <div class="row end" style="margin-top: 1rem">
          <button class="btn-quiet" @click="acting = null">Go back</button>
          <button class="btn-danger" :disabled="busy === acting.row.id" @click="confirm()">
            {{ acting.kind === 'cancel' ? 'Cancel the order' : 'Give the money back' }}
          </button>
        </div>
      </section>
    </div>
    <ManagerApproval
      v-if="approving.open"
      :what="approving.what"
      :error="approving.error"
      @approve="(a) => confirm(a)"
      @cancel="approving.open = false"
    />
  </AppShell>
</template>

<style scoped>
.bar-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.items { max-width: 22rem; font-size: .9rem; color: var(--muted); }
.acts { display: flex; gap: .35rem; flex-wrap: wrap; justify-content: flex-end; }
.slip-lines { list-style: none; margin: .8rem 0; padding: 0; display: grid; gap: .4rem; }
.slip-lines li { display: flex; justify-content: space-between; gap: .8rem; border-bottom: 1px solid var(--line); padding-bottom: .35rem; }
.slip-lines small { display: block; color: var(--muted); font-size: .8rem; }
.totals { margin: 0; display: grid; gap: .2rem; }
.totals > div { display: flex; justify-content: space-between; }
.totals dt, .totals dd { margin: 0; font-size: .92rem; }
.totals .grand dt, .totals .grand dd { font-family: var(--display); font-weight: 900; font-size: 1.05rem; }
</style>
