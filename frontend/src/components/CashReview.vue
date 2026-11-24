<!--
  For whoever approves cash (cash.approve): drops and petty cash waiting to be
  confirmed, and till counts out by more than the limit waiting for a review.
  A review records what was found; it never changes the figures.
-->
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api, ApiError, type Shift } from '../services/api'
import { kwacha } from '../services/money'
import { session } from '../stores/session'

interface Move { id: string; cashier: string; label: string; amount_ngwee: number; reason: string; status: string; recorded_by: string | null; at: string }
const moves = ref<Move[]>([])
const tills = ref<Shift[]>([])
const notes = reactive<Record<string, string>>({})
const error = ref('')
const me = session.user.value?.name

async function load() {
  if (!session.can('cash.approve')) return
  try {
    const [m, t] = await Promise.all([
      api.get<Move[]>('/sales/cash?pending=true'),
      api.get<Shift[]>('/sales/shifts?needs_review=true&limit=50'),
    ])
    moves.value = m
    tills.value = t
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load cash to review.'
  }
}

async function decide(m: Move, ok: boolean) {
  try {
    await api.post(`/sales/cash/${m.id}/decide`, { ok })
    moves.value = moves.value.filter((x) => x.id !== m.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save that.'
  }
}

async function review(t: Shift) {
  const note = (notes[t.id] ?? '').trim()
  if (note.length < 3) {
    error.value = 'Write what you found before marking it reviewed.'
    return
  }
  try {
    await api.post(`/sales/shifts/${t.id}/review`, { note })
    tills.value = tills.value.filter((x) => x.id !== t.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save the review.'
  }
}

function when(iso: string | null) {
  return iso ? new Date(iso).toLocaleString('en-ZM', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
}

onMounted(load)
</script>

<template>
  <p v-if="error" class="error">{{ error }}</p>

  <section v-if="tills.length" class="card review">
    <div class="card-head">
      <div>
        <h3>Till counts to review</h3>
        <p class="muted small">Out by more than the limit in Settings. A difference is something to look into, not proof of anything.</p>
      </div>
    </div>
    <ul class="home-list">
      <li v-for="t in tills" :key="t.id" class="till">
        <div>
          <b>{{ t.opened_by }}</b> <span class="muted">· closed {{ when(t.closed_at) }}</span>
          <p class="sub">
            Expected {{ kwacha(t.expected_ngwee ?? 0) }}, counted {{ kwacha(t.counted_ngwee ?? 0) }}
            <template v-if="t.first_count_ngwee !== null && t.first_count_ngwee !== t.counted_ngwee">
              (first count {{ kwacha(t.first_count_ngwee ?? 0) }})</template>.
            <template v-if="t.note">Cashier's note: “{{ t.note }}”</template>
          </p>
          <div class="row">
            <input v-model="notes[t.id]" type="text" maxlength="300" placeholder="What you found" />
            <button class="btn-primary btn-small" @click="review(t)">Mark reviewed</button>
          </div>
        </div>
        <b class="num" :class="(t.variance_ngwee ?? 0) < 0 ? 'bad' : ''">
          {{ (t.variance_ngwee ?? 0) > 0 ? '+' : '−' }}{{ kwacha(Math.abs(t.variance_ngwee ?? 0)) }}
        </b>
      </li>
    </ul>
  </section>

  <section v-if="moves.length" class="card review">
    <div class="card-head"><h3>Cash moves to confirm</h3></div>
    <ul class="home-list">
      <li v-for="m in moves" :key="m.id">
        <div>
          <b>{{ m.label }}</b> <span class="muted">· {{ m.cashier }}'s till · {{ when(m.at) }}</span>
          <p class="sub">{{ m.reason }}</p>
          <div v-if="m.recorded_by !== me" class="row">
            <button class="btn-primary btn-small" @click="decide(m, true)">Confirm</button>
            <button class="btn-quiet btn-small" @click="decide(m, false)">It did not happen</button>
          </div>
          <p v-else class="sub">You recorded this one, so someone else confirms it.</p>
        </div>
        <b class="num">{{ kwacha(m.amount_ngwee) }}</b>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.review { margin-bottom: 1rem; }
.row { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .4rem; }
.row input { flex: 1 1 200px; min-width: 0; }
.till { align-items: start; }
</style>
