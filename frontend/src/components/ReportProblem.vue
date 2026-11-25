<!--
  "Report a problem": open to everyone, from the account menu.

  The person only describes what went wrong. The page they were on, the
  version and the reference of the last error the server gave are added for
  them; the device is read by the server. The report goes to IT, and the
  reply appears on the person's profile under Problem reports.
-->
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { APP_VERSION, ApiError, api, lastError } from '../services/api'

const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const description = ref('')
const module = ref('')
const priority = ref('normal')
const busy = ref(false)
const error = ref('')
const sent = ref('')
const recent = Date.now() - lastError.at < 30 * 60_000

const MODULES = [['', 'Not sure'], ['till', 'Till'], ['kitchen', 'Kitchen display'], ['orders', 'Orders'],
  ['payments', 'Payments'], ['stock', 'Stock'], ['books', 'Books'], ['payroll', 'Payroll'], ['printer', 'Printer'],
  ['network', 'Internet or network'], ['sign-in', 'Signing in'], ['other', 'Something else']]

async function send() {
  busy.value = true
  error.value = ''
  try {
    const t = await api.post<{ number: string }>('/tickets', {
      description: description.value, module: module.value, priority: priority.value,
      page: route.fullPath, app_version: APP_VERSION, error_reference: recent ? lastError.reference : '',
    })
    sent.value = t.number
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'The report could not be sent. Tell a manager instead.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="scrim" role="dialog" aria-modal="true" aria-label="Report a problem" @click.self="emit('close')">
    <form v-if="!sent" class="card box" @submit.prevent="send">
      <h2>Report a problem</h2>
      <p class="muted small">Say what you were doing and what went wrong. The page, the version
        <template v-if="recent && lastError.reference">and error reference {{ lastError.reference }}</template> are added for you.</p>
      <label class="field">What happened
        <textarea v-model="description" class="input" rows="4" minlength="5" required
                  placeholder="e.g. I pressed Take payment and nothing happened. The customer paid by MTN." />
      </label>
      <div class="row">
        <label class="field">Which part
          <select v-model="module" class="input"><option v-for="[v, l] in MODULES" :key="v" :value="v">{{ l }}</option></select>
        </label>
        <label class="field">How urgent
          <select v-model="priority" class="input">
            <option value="low">Can wait</option><option value="normal">Normal</option>
            <option value="high">Slowing us down</option><option value="urgent">We cannot sell</option>
          </select>
        </label>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="row end">
        <button type="button" class="btn-ghost btn-sm" @click="emit('close')">Cancel</button>
        <button class="btn-primary btn-sm" :disabled="busy || description.trim().length < 5">{{ busy ? 'Sending…' : 'Send to IT' }}</button>
      </div>
    </form>
    <div v-else class="card box">
      <h2>Sent: {{ sent }}</h2>
      <p>IT has it. You will see their reply on your profile, under Problem reports.</p>
      <p class="muted small">If you cannot sell at all, tell the manager on duty now as well.</p>
      <div class="row end"><button class="btn-primary btn-sm" @click="emit('close')">Done</button></div>
    </div>
  </div>
</template>

<style scoped>
.scrim { position: fixed; inset: 0; z-index: 150; display: grid; place-items: center; padding: 16px; background: #0007; }
.box { width: min(520px, 100%); display: grid; gap: .75rem; }
.field { display: grid; gap: .25rem; font-weight: 600; font-size: .9rem; flex: 1 1 12rem; }
.row { display: flex; gap: .6rem; flex-wrap: wrap; align-items: flex-end; }
.row.end { justify-content: flex-end; }
.error { color: var(--danger); font-weight: 600; }
</style>
