<!--
  The areas the restaurant delivers to, what it charges and how long it takes.

  These fees were seeded with plausible Kitwe numbers so the website works on
  day one, but they are guesses. The note on each one says so until somebody
  has checked it against what a rider actually costs.
-->
<template>
  <AppShell>
    <h1>Delivery areas</h1>
    <p class="lead">
      What a customer is charged, and the smallest order worth sending that far.
      An area switched off disappears from the website.
    </p>

    <div class="warn-note">
      These fees came with the system as a starting point. Check them against what a rider
      actually costs you before relying on them.
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <button class="btn-primary" style="margin-bottom: 1rem" @click="startNew">Add an area</button>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Area</th>
            <th class="money">Fee</th>
            <th class="money">Minimum order</th>
            <th class="money">Minutes</th>
            <th>On the website</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="zone in zones" :key="zone.id">
            <td><strong>{{ zone.name }}</strong></td>
            <td class="money">{{ kwacha(zone.fee_ngwee) }}</td>
            <td class="money">{{ zone.minimum_ngwee ? kwacha(zone.minimum_ngwee) : '—' }}</td>
            <td class="money">{{ zone.minutes }}</td>
            <td>
              <span class="tag" :class="{ off: !zone.is_active }">
                {{ zone.is_active ? 'Showing' : 'Hidden' }}
              </span>
            </td>
            <td><button class="btn-quiet btn-small" @click="edit(zone)">Change</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="editing" class="sheet-back" @click.self="editing = null">
      <div class="sheet">
        <div class="sheet-head">
          <h2>{{ editing.id ? 'Change this area' : 'Add an area' }}</h2>
          <button class="btn-quiet btn-small" @click="editing = null">Close</button>
        </div>
        <label class="field">Name<input v-model="editing.name" type="text" maxlength="60" /></label>
        <div class="grid-3" style="margin-top: 0.7rem">
          <label class="field">
            Fee (kwacha)
            <input v-model="feeKwacha" type="number" min="0" step="0.01" />
          </label>
          <label class="field">
            Smallest order (kwacha)
            <input v-model="minimumKwacha" type="number" min="0" step="0.01" />
          </label>
          <label class="field">
            Usual minutes
            <input v-model.number="editing.minutes" type="number" min="0" max="600" />
          </label>
        </div>
        <label class="field" style="margin-top: 0.7rem">
          Note for staff
          <input v-model="editing.note" type="text" maxlength="200" />
        </label>
        <label class="row" style="margin-top: 0.8rem; gap: 0.5rem">
          <input v-model="editing.is_active" type="checkbox" style="width: auto" />
          <span>Show this area on the website</span>
        </label>
        <div class="row end" style="margin-top: 1rem">
          <button class="btn-quiet" @click="editing = null">Cancel</button>
          <button class="btn-primary" @click="save">Save</button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api } from '../services/api'
import { kwacha, toNgwee } from '../services/money'

interface Zone {
  id: string
  name: string
  fee_ngwee: number
  minutes: number
  minimum_ngwee: number
  is_active: boolean
  sort: number
  note: string
}

const zones = ref<Zone[]>([])
const loading = ref(true)
const error = ref('')
const note = ref('')
const editing = ref<Zone | null>(null)
const feeKwacha = ref('')
const minimumKwacha = ref('')

async function load() {
  try {
    zones.value = await api.get<Zone[]>('/customers/zones')
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load the areas.'
  } finally {
    loading.value = false
  }
}

function startNew() {
  editing.value = {
    id: '', name: '', fee_ngwee: 0, minutes: 30, minimum_ngwee: 0,
    is_active: true, sort: zones.value.length * 10 + 10, note: '',
  }
  feeKwacha.value = ''
  minimumKwacha.value = ''
}

function edit(zone: Zone) {
  editing.value = { ...zone }
  feeKwacha.value = String(zone.fee_ngwee / 100)
  minimumKwacha.value = String(zone.minimum_ngwee / 100)
}

async function save() {
  const zone = editing.value
  if (!zone) return
  const body = {
    name: zone.name,
    fee_ngwee: toNgwee(feeKwacha.value || '0'),
    minimum_ngwee: toNgwee(minimumKwacha.value || '0'),
    minutes: zone.minutes,
    is_active: zone.is_active,
    sort: zone.sort,
    note: zone.note,
  }
  try {
    if (zone.id) await api.patch(`/customers/zones/${zone.id}`, body)
    else await api.post('/customers/zones', body)
    editing.value = null
    note.value = 'Saved.'
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not save that area.'
  }
}

onMounted(load)
</script>
