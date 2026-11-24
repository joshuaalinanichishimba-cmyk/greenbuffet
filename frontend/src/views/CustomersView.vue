<!--
  Everyone who has ever given a phone number, and how full their stamp card is.

  A customer record here is thin on purpose: a number, a name, where they
  live, what they have spent. A restaurant does not need more than that, and
  every extra field is one more thing to keep accurate.
-->
<template>
  <AppShell>
    <h1>Customers & stamps</h1>
    <p class="lead">
      Found by phone number, the same number the kitchen rings and the stamp card is held against.
    </p>

    <div class="panel" style="margin-bottom: 1rem">
      <label class="field">
        Search by name or number
        <input
          v-model="search"
          type="search"
          maxlength="60"
          placeholder="0976… or Mwila"
          @input="debouncedLoad"
        />
      </label>
      <p class="muted" style="margin-top: 0.5rem">{{ rules }}</p>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="!customers.length" class="empty">
      No customers yet. They appear here as soon as somebody orders with a phone number.
    </div>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Customer</th>
            <th class="hide-small">Area</th>
            <th class="money hide-small">Orders</th>
            <th class="money">Spent</th>
            <th class="money">Stamps</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="person in customers" :key="person.id">
            <td>
              <strong>{{ person.name || 'No name given' }}</strong>
              <div class="muted">{{ person.phone }}</div>
            </td>
            <td class="hide-small">{{ person.area || '—' }}</td>
            <td class="money hide-small">{{ person.orders_count }}</td>
            <td class="money">{{ kwacha(person.spent_ngwee) }}</td>
            <td class="money">
              <strong>{{ person.stamps }} / {{ person.stamps_needed }}</strong>
              <div v-if="person.free_ready" class="muted"><span class="pill">Next one free</span></div>
            </td>
            <td>
              <button class="btn-quiet btn-small" @click="open(person)">Open</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="chosen" class="sheet-back" @click.self="chosen = null">
      <div class="sheet">
        <div class="sheet-head">
          <div>
            <h2>{{ chosen.name || chosen.phone }}</h2>
            <p class="muted">{{ chosen.phone }} · {{ chosen.orders_count }} orders · {{ kwacha(chosen.spent_ngwee) }}</p>
          </div>
          <button class="btn-quiet btn-small" @click="chosen = null">Close</button>
        </div>

        <div class="grid-2">
          <label class="field">Name<input v-model="editName" type="text" maxlength="80" /></label>
          <label class="field">Area<input v-model="editArea" type="text" maxlength="80" /></label>
        </div>
        <label class="field" style="margin-top: 0.7rem">
          Address
          <input v-model="editAddress" type="text" maxlength="200" />
        </label>
        <label class="field" style="margin-top: 0.7rem">
          Note for staff
          <input v-model="editNote" type="text" maxlength="300" placeholder="Always wants extra sauce" />
        </label>
        <div class="row" style="margin-top: 0.8rem">
          <button class="btn-primary" @click="saveDetails">Save</button>
        </div>

        <h2 style="font-size: 1rem; margin-top: 1.6rem">Stamp card</h2>
        <div class="card-stamps" :aria-label="`${chosen.stamps} of ${chosen.stamps_needed} stamps`">
          <span v-for="n in chosen.stamps_needed" :key="n" class="stamp" :class="{ on: n <= chosen.stamps }">
            {{ n <= chosen.stamps ? '✓' : n }}
          </span>
          <span class="stamp free" :class="{ on: chosen.free_ready }">Free</span>
        </div>
        <p class="muted" style="margin-top: .4rem">
          {{ chosen.free_ready ? 'The next bowl or burrito is free; the till takes it off by itself.' : `${chosen.stamps_needed - chosen.stamps} more paid bowls or burritos until a free one.` }}
        </p>
        <div class="row">
          <label class="field" style="flex: 1">
            Change by
            <input v-model.number="adjustBy" type="number" step="1" />
          </label>
          <label class="field" style="flex: 2">
            Why
            <input v-model="adjustReason" type="text" maxlength="120" placeholder="Paper card brought in with 3 stamps" />
          </label>
        </div>
        <button class="btn-quiet btn-small" style="margin-top: 0.6rem" @click="adjust">
          Apply the change
        </button>

        <div v-if="history.length" class="table-wrap" style="margin-top: 1rem">
          <table>
            <thead>
              <tr><th>When</th><th>Why</th><th class="money">Stamps</th><th class="money">Card</th></tr>
            </thead>
            <tbody>
              <tr v-for="(entry, index) in history" :key="index">
                <td class="muted">{{ at(entry.at) }}</td>
                <td>{{ entry.reason }}</td>
                <td class="money">{{ entry.points > 0 ? '+' : '' }}{{ entry.points }}</td>
                <td class="money">{{ entry.balance_after }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api } from '../services/api'
import { kwacha } from '../services/money'

interface Customer {
  id: string
  phone: string
  name: string
  email: string
  area: string
  address: string
  note: string
  stamps: number
  stamps_needed: number
  free_ready: boolean
  orders_count: number
  spent_ngwee: number
  last_order_at: string
}

interface Entry {
  points: number
  balance_after: number
  reason: string
  at: string
  by: string
}

const customers = ref<Customer[]>([])
const history = ref<Entry[]>([])
const chosen = ref<Customer | null>(null)
const loading = ref(true)
const error = ref('')
const note = ref('')
const search = ref('')
const rules = ref('')

const editName = ref('')
const editArea = ref('')
const editAddress = ref('')
const editNote = ref('')
const adjustBy = ref(0)
const adjustReason = ref('')

let typing: number | undefined

function at(when: string) {
  return when ? new Date(when).toLocaleString() : ''
}

async function load() {
  try {
    customers.value = await api.get<Customer[]>(
      `/customers?search=${encodeURIComponent(search.value)}`,
    )
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load customers.'
  } finally {
    loading.value = false
  }
}

function debouncedLoad() {
  window.clearTimeout(typing)
  typing = window.setTimeout(load, 250)
}

async function open(person: Customer) {
  chosen.value = person
  editName.value = person.name
  editArea.value = person.area
  editAddress.value = person.address
  editNote.value = person.note
  adjustBy.value = 0
  adjustReason.value = ''
  history.value = []
  try {
    history.value = await api.get<Entry[]>(`/customers/${person.id}/stamps`)
  } catch {
    /* a missing history is not worth an error on this screen */
  }
}

async function saveDetails() {
  if (!chosen.value) return
  try {
    const updated = await api.patch<Customer>(`/customers/${chosen.value.id}`, {
      name: editName.value,
      area: editArea.value,
      address: editAddress.value,
      note: editNote.value,
    })
    chosen.value = updated
    note.value = 'Saved.'
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not save.'
  }
}


async function adjust() {
  if (!chosen.value) return
  try {
    const updated = await api.post<Customer>(`/customers/${chosen.value.id}/stamps`, {
      points: adjustBy.value,
      reason: adjustReason.value,
    })
    chosen.value = updated
    history.value = await api.get<Entry[]>(`/customers/${updated.id}/stamps`)
    adjustBy.value = 0
    adjustReason.value = ''
    note.value = 'Stamp card changed.'
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not change the card.'
  }
}

onMounted(async () => {
  await load()
  try {
    rules.value = (await api.get<{ summary: string }>('/customers/stamps/rules')).summary
  } catch {
    /* the rules line is a nicety */
  }
})
</script>

<style scoped>
.card-stamps { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .3rem; }
.stamp { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; border: 2px dashed var(--line); color: var(--muted); font-weight: 800; font-size: .82rem; }
.stamp.on { border-style: solid; border-color: var(--green); background: var(--leaf-soft); color: var(--green-deep); }
.stamp.free { width: auto; padding: 0 .8rem; border-radius: 999px; }
.stamp.free.on { background: var(--green); color: var(--green-ink); }
</style>
