<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import AppShell from '../components/AppShell.vue'
import SubNav from '../components/SubNav.vue'
import { session } from '../stores/session'
import { ApiError, api, type AuditEntry } from '../services/api'

const entries = ref<AuditEntry[]>([])
const area = ref('')
const loading = ref(true)
const error = ref('')

const areas = ['security', 'sales', 'money', 'stock', 'people']

async function load() {
  loading.value = true
  error.value = ''
  try {
    entries.value = await api.audit(area.value || undefined)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the activity log.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(area, load)

function when(iso: string) {
  const at = new Date(iso)
  return at.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Africa/Lusaka',
  })
}
</script>

<template>
  <AppShell>
    <h1>Settings</h1>
    <p class="lead">
      Every sign-in, account change and, from later stages, every sale and journal entry is written
      here once and never edited. It is the record to check when figures or access are questioned.
    </p>
    <SubNav :links="[{ to: '/settings', label: 'Settings' }, { to: '/activity', label: 'Activity log', show: session.can('audit.view') }]" />

    <label class="field filter">
      Show
      <select v-model="area">
        <option value="">Everything</option>
        <option v-for="a in areas" :key="a" :value="a">{{ a }}</option>
      </select>
    </label>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!entries.length" class="muted">Nothing recorded in this area yet.</p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>Area</th>
            <th>What happened</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in entries" :key="e.id">
            <td class="when">{{ when(e.at) }}</td>
            <td>{{ e.actor }}</td>
            <td><span class="tag">{{ e.area }}</span></td>
            <td><b>{{ e.action }}</b></td>
            <td>
              {{ e.detail }}
              <span v-if="e.reference" class="muted">· {{ e.reference }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppShell>
</template>

<style scoped>
.filter { max-width: 220px; margin-bottom: 1rem; }
.when { white-space: nowrap; }
</style>
