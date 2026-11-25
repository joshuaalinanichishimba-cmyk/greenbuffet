<!--
  The IT workspace. One page with sections, not a dozen dashboards:

    Health      what is working, measured just now, and the full diagnostics
    Repairs     integrity checks and the fixed list of repairs, with history
    Controls    emergency switches: cash only, stop orders, read-only
    Incidents   faults being worked on, from first report to root cause
    Tickets     problems reported by the staff
    Errors      what the server could not handle, grouped
    Security    sign-in failures, refusals, lockouts, rate limits
    Audit       technical and security actions, unchangeable
    Resources   database size, memory, files

  Every status shown comes from a check the server ran. What cannot be
  checked from here says so.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import Icon from '../components/Icon.vue'
import { ApiError, api } from '../services/api'
import { ago, clock } from '../services/presence'
import { session } from '../stores/session'

type Status = 'operational' | 'degraded' | 'critical' | 'offline' | 'unknown' | 'not_configured'
interface Check { key: string; label: string; status: Status; detail: string; measured_at: string; repair?: string | null }
interface Control { key: string; label: string; meaning: string; enabled: boolean; default: boolean; changed_by: string; reason: string; changed_at: string | null }

const route = useRoute()
const router = useRouter()
const section = computed(() => (route.params.section as string) || 'health')
const caseId = computed(() => (route.params.id as string) || '')

const SECTIONS = [
  ['health', 'Health'], ['repairs', 'Repairs'], ['controls', 'Controls'], ['incidents', 'Incidents'],
  ['tickets', 'Tickets'], ['errors', 'Errors'], ['security', 'Security'], ['audit', 'Audit'], ['resources', 'Resources'],
] as const

const STATUS_LABEL: Record<Status, string> = {
  operational: 'Operational', degraded: 'Degraded', critical: 'Critical', offline: 'Offline',
  unknown: 'Unknown', not_configured: 'Not configured',
}
const pillFor = (s: string) => (s === 'operational' ? '' : s === 'degraded' || s === 'unknown' ? 'warn'
  : s === 'not_configured' ? 'neutral' : 'danger')

const error = ref('')
const notice = ref('')
const busy = ref(false)
const data = ref<Record<string, any>>({})
let timer: number | undefined

function fail(e: unknown, fallback: string) {
  error.value = e instanceof ApiError ? e.message : fallback
}

async function load() {
  error.value = ''
  try {
    const s = section.value
    if (s === 'health') data.value.overview = await api.get('/it/overview')
    if (s === 'repairs') {
      const [checks, repairs] = await Promise.all([api.get('/it/integrity'), api.get('/it/repairs')])
      data.value.integrity = checks
      data.value.repairs = repairs
    }
    if (s === 'controls') data.value.controls = await api.get('/it/controls')
    if (s === 'incidents') {
      data.value.incidents = await api.get('/it/incidents')
      data.value.incident = caseId.value ? await api.get(`/it/incidents/${caseId.value}`) : null
    }
    if (s === 'tickets') {
      data.value.tickets = await api.get('/it/tickets')
      data.value.ticket = caseId.value ? await api.get(`/it/tickets/${caseId.value}`) : null
    }
    if (s === 'errors') data.value.errors = await api.get(`/it/errors?show=${errorFilter.value}`)
    if (s === 'security') data.value.security = await api.get(`/it/security?show=${securityFilter.value}`)
    if (s === 'audit') data.value.audit = await api.get('/it/audit')
    if (s === 'resources') data.value.resources = await api.get('/it/resources')
  } catch (e) {
    fail(e, 'Could not load this section.')
  }
}

// ---- health ----
const diagnostics = ref<{ ran_at: string; seconds: number; results: Check[] } | null>(null)
async function runDiagnostics() {
  busy.value = true
  try {
    diagnostics.value = await api.post('/it/diagnostics')
  } catch (e) {
    fail(e, 'Diagnostics did not run.')
  } finally {
    busy.value = false
  }
}
const needsAttention = computed(() => (diagnostics.value?.results ?? []).filter((r) => r.status !== 'operational'))

// ---- repairs ----
const chosen = ref<any>(null)
const preview = ref<{ affected: number; items: { ref: string; detail: string }[] } | null>(null)
const repairForm = ref({ reason: '', email: '', password: '' })
async function choose(r: any) {
  chosen.value = r
  preview.value = null
  repairForm.value = { reason: '', email: '', password: '' }
  if (!r.needs_email) await previewRepair()
}
async function previewRepair() {
  if (!chosen.value) return
  try {
    preview.value = await api.post(`/it/repairs/${chosen.value.key}/preview`, { reason: 'preview', email: repairForm.value.email || null })
  } catch (e) {
    fail(e, 'Could not preview.')
  }
}
async function runRepair() {
  busy.value = true
  error.value = ''
  try {
    const r = await api.post<{ status: string; result: string; verification: string }>(`/it/repairs/${chosen.value.key}/run`, {
      reason: repairForm.value.reason, email: repairForm.value.email || null, password: repairForm.value.password || null,
    })
    notice.value = `${chosen.value.label}: ${r.status}. ${r.result} ${r.verification}`
    chosen.value = null
    await load()
  } catch (e) {
    fail(e, 'The repair did not run.')
  } finally {
    busy.value = false
  }
}

// ---- controls ----
const switching = ref<Control | null>(null)
const controlForm = ref({ reason: '', password: '' })
async function setControl() {
  if (!switching.value) return
  busy.value = true
  try {
    data.value.controls = await api.post(`/it/controls/${switching.value.key}`, {
      enabled: !switching.value.enabled, reason: controlForm.value.reason, password: controlForm.value.password,
    })
    notice.value = `${switching.value.label} is now ${!switching.value.enabled ? 'on' : 'off'}. The owners have been told.`
    switching.value = null
    controlForm.value = { reason: '', password: '' }
  } catch (e) {
    fail(e, 'The control was not changed.')
  } finally {
    busy.value = false
  }
}

// ---- incidents and tickets ----
const newIncident = ref({ open: false, title: '', service: '', severity: 'medium', impact: '' })
async function openIncident() {
  busy.value = true
  try {
    const i = await api.post<{ id: string }>('/it/incidents', newIncident.value)
    newIncident.value = { open: false, title: '', service: '', severity: 'medium', impact: '' }
    router.push(`/it/incidents/${i.id}`)
  } catch (e) {
    fail(e, 'Could not open the incident.')
  } finally {
    busy.value = false
  }
}
const edit = ref<Record<string, string>>({})
watch(() => [data.value.incident?.id, data.value.ticket?.id], () => {
  const c = data.value.incident ?? data.value.ticket
  edit.value = c ? { status: c.status, severity: c.severity ?? '', priority: c.priority ?? '', assigned_to: c.assigned_to,
    root_cause: c.root_cause ?? '', resolution: c.resolution ?? '', prevention: c.prevention ?? '', note: '',
    incident_id: c.incident_id ?? '' } : {}
})
async function saveCase(kind: 'incidents' | 'tickets') {
  const c = kind === 'incidents' ? data.value.incident : data.value.ticket
  busy.value = true
  try {
    const body: Record<string, string | null> = { ...edit.value }
    if (kind === 'incidents') { delete body.priority; delete body.incident_id } else {
      delete body.severity; delete body.root_cause; delete body.prevention
      if (!body.incident_id) body.incident_id = null
    }
    const updated = await api.patch(`/it/${kind}/${c.id}`, body)
    if (kind === 'incidents') data.value.incident = updated
    else data.value.ticket = updated
    edit.value.note = ''
    notice.value = 'Saved.'
    data.value[kind] = await api.get(`/it/${kind}`)
  } catch (e) {
    fail(e, 'Could not save.')
  } finally {
    busy.value = false
  }
}

// ---- errors and security ----
const errorFilter = ref('new')
const securityFilter = ref('open')
async function resolveError(id: string) {
  await api.post(`/it/errors/${id}/resolve`)
  await load()
}
const reviewing = ref<string>('')
const reviewNote = ref('')
async function review(id: string) {
  try {
    await api.post(`/it/security/${id}/review`, { note: reviewNote.value })
    reviewing.value = ''
    reviewNote.value = ''
    await load()
  } catch (e) {
    fail(e, 'Could not save the review.')
  }
}

const SEVERITY_CLASS: Record<string, string> = { info: 'neutral', low: 'neutral', medium: 'warn', high: 'danger', critical: 'danger' }

watch(() => route.fullPath, () => {
  notice.value = ''
  load()
}, { immediate: true })
onMounted(() => {
  timer = window.setInterval(() => {
    if (section.value === 'health') load()
  }, 60000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <div class="home-head">
      <div>
        <h1>IT workspace</h1>
        <p class="lead">Keeping the system running. No money, pay or prices here.</p>
      </div>
      <div class="actions">
        <button class="btn-primary" :disabled="busy" @click="router.push('/it'); runDiagnostics()">
          <Icon name="settings" :size="18" /> {{ busy ? 'Checking…' : 'Run diagnostics' }}
        </button>
      </div>
    </div>

    <nav class="itnav" aria-label="IT workspace">
      <RouterLink v-for="[key, label] in SECTIONS" :key="key" :to="key === 'health' ? '/it' : `/it/${key}`" :class="{ on: section === key }">{{ label }}</RouterLink>
    </nav>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="ok">{{ notice }}</p>

    <!-- ================= health ================= -->
    <template v-if="section === 'health' && data.overview">
      <section class="card home-banner" :class="data.overview.overall === 'operational' ? 'good' : 'warn'">
        <span class="home-dot" :class="{ warn: data.overview.overall !== 'operational' }" />
        <div class="text">
          <b>{{ data.overview.overall === 'operational' ? 'Everything checked is working' : data.overview.overall === 'critical' ? 'Something needs fixing now' : 'Working, with things to look at' }}</b>
          <span>Version {{ data.overview.version }} · {{ data.overview.environment }} · up {{ data.overview.uptime_minutes }} min · checked {{ clock(data.overview.server_time) }}</span>
        </div>
      </section>

      <div class="kpis">
        <RouterLink to="/it/errors" class="kpi"><span class="kpi-label">Errors, last 24 h</span><span class="kpi-value">{{ data.overview.counts.errors_24h }}</span><span class="kpi-sub">{{ data.overview.counts.error_groups_open }} kinds not resolved</span></RouterLink>
        <RouterLink to="/it/security" class="kpi"><span class="kpi-label">Security events open</span><span class="kpi-value" :class="{ bad: data.overview.counts.security_high }">{{ data.overview.counts.security_open }}</span><span class="kpi-sub">{{ data.overview.counts.security_high }} high or critical</span></RouterLink>
        <RouterLink to="/it/incidents" class="kpi"><span class="kpi-label">Incidents open</span><span class="kpi-value">{{ data.overview.counts.incidents_open }}</span><span class="kpi-sub">{{ data.overview.counts.tickets_open }} tickets open</span></RouterLink>
        <div class="kpi"><span class="kpi-label">Signed in now</span><span class="kpi-value">{{ data.overview.counts.sessions_open }}</span><span class="kpi-sub">devices with an open session</span></div>
      </div>

      <section class="card">
        <div class="card-head"><h3>Services</h3><span class="muted small">Each measured just now</span></div>
        <ul class="checks">
          <li v-for="c in data.overview.checks" :key="c.key">
            <span class="pill" :class="pillFor(c.status)">{{ STATUS_LABEL[c.status as Status] }}</span>
            <div><b>{{ c.label }}</b><p class="sub">{{ c.detail }}</p></div>
          </li>
        </ul>
      </section>

      <section v-if="data.overview.controls.some((c: Control) => c.enabled !== c.default)" class="card home-banner warn">
        <Icon name="alert" :size="22" />
        <div class="text">
          <b>An emergency control is in use</b>
          <span v-for="c in data.overview.controls.filter((c: Control) => c.enabled !== c.default)" :key="c.key">{{ c.label }}: {{ c.enabled ? 'on' : 'off' }}, by {{ c.changed_by }} ({{ c.reason }})</span>
        </div>
        <RouterLink to="/it/controls" class="btn-outline">Controls</RouterLink>
      </section>

      <section v-if="diagnostics" class="card">
        <div class="card-head">
          <h3>Diagnostics</h3>
          <span class="muted small">{{ diagnostics.results.length }} checks in {{ diagnostics.seconds }} s · {{ clock(diagnostics.ran_at) }}</span>
        </div>
        <p v-if="!needsAttention.length" class="home-empty">Every check passed.</p>
        <ul class="checks">
          <li v-for="c in needsAttention" :key="c.key">
            <span class="pill" :class="pillFor(c.status)">{{ STATUS_LABEL[c.status] }}</span>
            <div><b>{{ c.label }}</b><p class="sub">{{ c.detail }}</p></div>
            <RouterLink v-if="c.repair" to="/it/repairs" class="small">Repair</RouterLink>
          </li>
        </ul>
        <details class="passed"><summary>{{ diagnostics.results.length - needsAttention.length }} passed</summary>
          <ul class="checks"><li v-for="c in diagnostics.results.filter((r) => r.status === 'operational')" :key="c.key">
            <span class="pill">Operational</span><div><b>{{ c.label }}</b><p class="sub">{{ c.detail }}</p></div></li></ul>
        </details>
      </section>
    </template>

    <!-- ================= repairs ================= -->
    <template v-if="section === 'repairs' && data.repairs">
      <section class="card">
        <div class="card-head"><h3>Integrity checks</h3><span class="muted small">Read only. Nothing changes until you run a repair.</span></div>
        <ul class="checks">
          <li v-for="c in data.integrity" :key="c.key">
            <span class="pill" :class="pillFor(c.status)">{{ c.count ? `${c.count}${c.more ? '+' : ''} found` : 'None' }}</span>
            <div>
              <b>{{ c.label }}</b>
              <p class="sub">{{ c.meaning }}</p>
              <p v-if="c.examples.length" class="sub mono">{{ c.examples.map((e: any) => e.ref).join(', ') }}</p>
            </div>
          </li>
        </ul>
      </section>

      <section class="card">
        <div class="card-head"><h3>Repairs</h3><span class="muted small">A fixed list. Each is checked afterwards and recorded.</span></div>
        <ul class="repairs">
          <li v-for="r in data.repairs.repairs" :key="r.key">
            <div>
              <b>{{ r.label }}</b> <span class="pill" :class="r.risk === 'low' ? 'neutral' : 'warn'">{{ r.risk }} risk</span>
              <p class="sub">{{ r.does }} Touches: {{ r.touches }}.</p>
            </div>
            <button class="btn-outline btn-sm" :disabled="r.pending === 0" @click="choose(r)">
              {{ r.pending === null ? 'Prepare' : r.pending === 0 ? 'Nothing to do' : `Prepare (${r.pending})` }}
            </button>
          </li>
        </ul>
        <div class="unavailable">
          <b>Not available from here</b>
          <p v-for="n in data.repairs.not_available" :key="n.label" class="sub">{{ n.label }}: {{ n.why }}</p>
        </div>
      </section>

      <form v-if="chosen" class="card ask" @submit.prevent="runRepair">
        <b>{{ chosen.label }}</b>
        <p class="sub">{{ chosen.does }}</p>
        <label v-if="chosen.needs_email" class="field">Account email
          <span class="row"><input v-model="repairForm.email" class="input" type="email" required /><button type="button" class="btn-ghost btn-sm" @click="previewRepair">Check</button></span>
        </label>
        <div v-if="preview" class="preview">
          <b>Will touch {{ preview.affected }} record{{ preview.affected === 1 ? '' : 's' }}</b>
          <ul><li v-for="(i, n) in preview.items.slice(0, 12)" :key="n">{{ i.ref }} <span class="muted">· {{ i.detail }}</span></li></ul>
          <p v-if="preview.affected > 12" class="muted small">…and {{ preview.affected - 12 }} more</p>
        </div>
        <label class="field">Why (kept in the record)
          <input v-model="repairForm.reason" class="input" minlength="5" maxlength="300" required placeholder="e.g. Ticket TKT0003: sales missing from the books" />
        </label>
        <label v-if="chosen.needs_password" class="field">Your password
          <input v-model="repairForm.password" class="input" type="password" required />
        </label>
        <div class="row">
          <button class="btn-primary btn-sm" :disabled="busy || repairForm.reason.trim().length < 5 || (chosen.needs_email && !preview)">{{ busy ? 'Running…' : 'Run repair' }}</button>
          <button type="button" class="btn-ghost btn-sm" @click="chosen = null">Cancel</button>
        </div>
      </form>

      <section class="card">
        <div class="card-head"><h3>Repair history</h3></div>
        <p v-if="!data.repairs.history.length" class="home-empty">No repairs run yet.</p>
        <ul class="home-list">
          <li v-for="h in data.repairs.history" :key="h.id">
            <div><b>{{ h.label }}</b> <span class="muted">· {{ h.by }}, {{ clock(h.at) }}</span>
              <p class="sub">{{ h.reason }}. {{ h.result }} {{ h.verification }}</p></div>
            <span class="pill" :class="h.status === 'succeeded' ? '' : h.status === 'partial' ? 'warn' : 'danger'">{{ h.status }}</span>
          </li>
        </ul>
      </section>
    </template>

    <!-- ================= controls ================= -->
    <template v-if="section === 'controls' && data.controls">
      <p class="info-note">These change what everyone at the restaurant can do. Each needs your password and a reason, and both owners are told.
        Payments already taken can always be matched, and nothing already saved is thrown away.</p>
      <section v-for="c in data.controls" :key="c.key" class="card control" :class="{ changed: c.enabled !== c.default }">
        <div>
          <b>{{ c.label }}</b> <span class="pill" :class="c.enabled !== c.default ? 'danger' : ''">{{ c.enabled ? 'On' : 'Off' }}</span>
          <p class="sub">{{ c.meaning }}</p>
          <p v-if="c.changed_by" class="sub">Last changed by {{ c.changed_by }}, {{ clock(c.changed_at) }}: {{ c.reason }}</p>
        </div>
        <button v-if="session.can('it.control')" class="btn-sm" :class="c.enabled !== c.default ? 'btn-primary' : 'btn-danger'"
                @click="switching = c; controlForm = { reason: '', password: '' }">
          {{ c.enabled ? 'Switch off' : 'Switch on' }}
        </button>
      </section>
      <form v-if="switching" class="card ask" @submit.prevent="setControl">
        <b>{{ switching.label }}: switch {{ switching.enabled ? 'off' : 'on' }}</b>
        <label class="field">Why <input v-model="controlForm.reason" class="input" minlength="5" required placeholder="e.g. MTN network down since 12:10" /></label>
        <label class="field">Your password <input v-model="controlForm.password" class="input" type="password" required /></label>
        <div class="row">
          <button class="btn-primary btn-sm" :disabled="busy">Confirm</button>
          <button type="button" class="btn-ghost btn-sm" @click="switching = null">Cancel</button>
        </div>
      </form>
    </template>

    <!-- ================= incidents ================= -->
    <template v-if="section === 'incidents' && data.incidents">
      <div class="split">
        <div class="col">
          <section class="card">
            <div class="card-head"><h3>Incidents</h3><button class="btn-outline btn-sm" @click="newIncident.open = !newIncident.open">Open an incident</button></div>
            <form v-if="newIncident.open" class="ask" @submit.prevent="openIncident">
              <input v-model="newIncident.title" class="input" placeholder="What is wrong" minlength="4" required />
              <div class="row">
                <input v-model="newIncident.service" class="input" placeholder="Service, e.g. Till" />
                <select v-model="newIncident.severity" class="input"><option v-for="s in ['info', 'low', 'medium', 'high', 'critical']" :key="s">{{ s }}</option></select>
              </div>
              <input v-model="newIncident.impact" class="input" placeholder="Effect on the restaurant" />
              <button class="btn-primary btn-sm" :disabled="busy">Open</button>
            </form>
            <p v-if="!data.incidents.length" class="home-empty">No incidents recorded.</p>
            <ul class="home-list">
              <li v-for="i in data.incidents" :key="i.id" :class="{ sel: i.id === caseId }">
                <RouterLink :to="`/it/incidents/${i.id}`" class="rowlink">
                  <div><b>{{ i.number }}</b> {{ i.title }}<p class="sub">{{ i.service || 'No service' }} · {{ clock(i.detected_at) }}</p></div>
                  <span class="right-col"><span class="pill" :class="SEVERITY_CLASS[i.severity]">{{ i.severity }}</span><span class="small muted">{{ i.status }}</span></span>
                </RouterLink>
              </li>
            </ul>
          </section>
        </div>
        <div v-if="data.incident" class="col">
          <section class="card case">
            <div class="card-head"><h3>{{ data.incident.number }} · {{ data.incident.title }}</h3></div>
            <p class="sub">Opened by {{ data.incident.reported_by }}, {{ clock(data.incident.detected_at) }}. {{ data.incident.impact }}</p>
            <div class="row">
              <label class="field">Status <select v-model="edit.status" class="input"><option v-for="s in ['open', 'investigating', 'repairing', 'monitoring', 'resolved', 'closed']" :key="s">{{ s }}</option></select></label>
              <label class="field">Severity <select v-model="edit.severity" class="input"><option v-for="s in ['info', 'low', 'medium', 'high', 'critical']" :key="s">{{ s }}</option></select></label>
              <label class="field">Assigned to <input v-model="edit.assigned_to" class="input" /></label>
            </div>
            <label class="field">Root cause <textarea v-model="edit.root_cause" class="input" rows="2" /></label>
            <label class="field">What fixed it <textarea v-model="edit.resolution" class="input" rows="2" /></label>
            <label class="field">How to stop it happening again <textarea v-model="edit.prevention" class="input" rows="2" /></label>
            <label class="field">Add a note <textarea v-model="edit.note" class="input" rows="2" placeholder="Diagnostics, what you tried, what you saw" /></label>
            <button class="btn-primary btn-sm" :disabled="busy" @click="saveCase('incidents')">Save</button>
            <ul class="timeline"><li v-for="(n, k) in data.incident.notes" :key="k"><b>{{ n.by }}</b> <span class="muted small">{{ clock(n.at) }}</span><p>{{ n.note }}</p></li></ul>
          </section>
        </div>
      </div>
    </template>

    <!-- ================= tickets ================= -->
    <template v-if="section === 'tickets' && data.tickets">
      <div class="split">
        <div class="col">
          <section class="card">
            <div class="card-head"><h3>Problems reported</h3></div>
            <p v-if="!data.tickets.length" class="home-empty">Nobody has reported a problem.</p>
            <ul class="home-list">
              <li v-for="t in data.tickets" :key="t.id" :class="{ sel: t.id === caseId }">
                <RouterLink :to="`/it/tickets/${t.id}`" class="rowlink">
                  <div><b>{{ t.number }}</b> {{ t.description.slice(0, 70) }}<p class="sub">{{ t.reporter }} · {{ t.module || 'general' }} · {{ ago(t.created_at) }}</p></div>
                  <span class="right-col"><span class="pill" :class="t.priority === 'urgent' || t.priority === 'high' ? 'danger' : 'neutral'">{{ t.priority }}</span><span class="small muted">{{ t.status }}</span></span>
                </RouterLink>
              </li>
            </ul>
          </section>
        </div>
        <div v-if="data.ticket" class="col">
          <section class="card case">
            <div class="card-head"><h3>{{ data.ticket.number }}</h3></div>
            <p>{{ data.ticket.description }}</p>
            <p class="sub">{{ data.ticket.reporter }} · {{ data.ticket.device }} · version {{ data.ticket.app_version }}<template v-if="data.ticket.page"> · on {{ data.ticket.page }}</template><template v-if="data.ticket.error_reference"> · error ref {{ data.ticket.error_reference }}</template></p>
            <div class="row">
              <label class="field">Status <select v-model="edit.status" class="input"><option v-for="s in ['new', 'investigating', 'waiting', 'resolved', 'closed']" :key="s">{{ s }}</option></select></label>
              <label class="field">Priority <select v-model="edit.priority" class="input"><option v-for="s in ['low', 'normal', 'high', 'urgent']" :key="s">{{ s }}</option></select></label>
              <label class="field">Assigned to <input v-model="edit.assigned_to" class="input" /></label>
            </div>
            <label class="field">Part of incident
              <select v-model="edit.incident_id" class="input"><option value="">None</option><option v-for="i in (data.incidents ?? [])" :key="i.id" :value="i.id">{{ i.number }} {{ i.title }}</option></select>
            </label>
            <label class="field">What was done <textarea v-model="edit.resolution" class="input" rows="2" /></label>
            <label class="field">Message to {{ data.ticket.reporter }} <textarea v-model="edit.note" class="input" rows="2" placeholder="They see this on their profile" /></label>
            <button class="btn-primary btn-sm" :disabled="busy" @click="saveCase('tickets')">Save</button>
            <ul class="timeline"><li v-for="(n, k) in data.ticket.notes" :key="k"><b>{{ n.by }}</b> <span class="muted small">{{ clock(n.at) }}</span><p>{{ n.note }}</p></li></ul>
          </section>
        </div>
      </div>
    </template>

    <!-- ================= errors ================= -->
    <template v-if="section === 'errors' && data.errors">
      <div class="row filters">
        <button v-for="f in ['new', 'resolved', 'all']" :key="f" class="chip" :aria-pressed="errorFilter === f" @click="errorFilter = f; load()">{{ f === 'new' ? 'Not resolved' : f === 'all' ? 'All' : 'Resolved' }}</button>
      </div>
      <section class="card">
        <p v-if="!data.errors.length" class="home-empty">No errors here.</p>
        <ul class="home-list">
          <li v-for="e in data.errors" :key="e.id">
            <div>
              <b>{{ e.kind }}</b> <span class="muted">· {{ e.method }} {{ e.path }} · {{ e.count }}×</span>
              <p class="sub mono">{{ e.message }}</p>
              <p class="sub">{{ e.where }} · first {{ clock(e.first_seen) }}, last {{ ago(e.last_seen).toLowerCase() }} · reference {{ e.reference }} · version {{ e.version }}</p>
            </div>
            <button v-if="e.status === 'new'" class="btn-ghost btn-sm" @click="resolveError(e.id)">Mark resolved</button>
            <span v-else class="pill">Resolved</span>
          </li>
        </ul>
        <p class="muted small note">Messages are cleaned of passwords, tokens and addresses before they are kept. The full trace is in logs\server.log on the server.</p>
      </section>
    </template>

    <!-- ================= security ================= -->
    <template v-if="section === 'security' && data.security">
      <p class="info-note">An event is something to look at, not proof that anyone did wrong. Most refusals are a wrong click.</p>
      <div class="row filters">
        <button v-for="f in ['open', 'reviewed', 'all']" :key="f" class="chip" :aria-pressed="securityFilter === f" @click="securityFilter = f; load()">{{ f === 'open' ? 'To review' : f === 'all' ? 'All' : 'Reviewed' }}</button>
      </div>
      <section class="card">
        <p v-if="!data.security.length" class="home-empty">Nothing to review.</p>
        <ul class="home-list">
          <li v-for="s in data.security" :key="s.id">
            <div>
              <b>{{ s.kind.replaceAll('_', ' ') }}</b> <span class="pill" :class="SEVERITY_CLASS[s.severity]">{{ s.severity }}</span>
              <p class="sub">{{ s.detail }}<template v-if="s.account"> · {{ s.account }}</template><template v-if="s.ip"> · {{ s.ip }}</template><template v-if="s.path"> · {{ s.path }}</template> · {{ clock(s.at) }}</p>
              <p v-if="s.note" class="sub">Reviewed by {{ s.reviewed_by }}: {{ s.note }}</p>
              <form v-if="reviewing === s.id" class="row" @submit.prevent="review(s.id)">
                <input v-model="reviewNote" class="input" placeholder="What you found" minlength="3" required />
                <button class="btn-primary btn-sm">Save</button>
              </form>
            </div>
            <button v-if="s.status === 'open' && reviewing !== s.id" class="btn-ghost btn-sm" @click="reviewing = s.id; reviewNote = ''">Review</button>
          </li>
        </ul>
      </section>
    </template>

    <!-- ================= audit ================= -->
    <section v-if="section === 'audit' && data.audit" class="card">
      <div class="card-head"><h3>Technical and security record</h3><span class="muted small">Cannot be changed or deleted, by anyone</span></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr></thead>
          <tbody><tr v-for="(a, k) in data.audit" :key="k"><td class="nowrap">{{ clock(a.at) }}</td><td>{{ a.actor }}</td><td>{{ a.action }}</td><td>{{ a.detail }}</td></tr></tbody>
        </table>
      </div>
    </section>

    <!-- ================= resources ================= -->
    <template v-if="section === 'resources' && data.resources">
      <div class="kpis">
        <div class="kpi"><span class="kpi-label">Database</span><span class="kpi-value">{{ data.resources.database_mb }} MB</span><span class="kpi-sub">{{ data.resources.connections }} connections</span></div>
        <div class="kpi"><span class="kpi-label">Photos and files</span><span class="kpi-value">{{ data.resources.uploads_mb }} MB</span></div>
        <div class="kpi"><span class="kpi-label">Server memory (peak)</span><span class="kpi-value">{{ data.resources.server_memory_mb ?? '—' }} MB</span><span class="kpi-sub">up {{ data.resources.uptime_minutes }} min</span></div>
      </div>
      <section class="card">
        <div class="card-head"><h3>Largest tables</h3></div>
        <ul class="home-list"><li v-for="t in data.resources.largest_tables" :key="t.table"><span class="mono">{{ t.table }}</span><b class="num">{{ t.rows.toLocaleString() }}</b></li></ul>
        <p class="muted small note">Python {{ data.resources.python }} on {{ data.resources.platform }} · version {{ data.resources.version }}. Hosting costs: {{ data.resources.hosting_costs }}</p>
      </section>
    </template>
  </AppShell>
</template>

<style scoped>
.itnav { display: flex; gap: .25rem; margin: 0 0 1rem; border-bottom: 1px solid var(--line); overflow-x: auto; scrollbar-width: thin; }
.itnav a { padding: .6rem .85rem; text-decoration: none; color: var(--muted); font-weight: 700; white-space: nowrap; border-bottom: 3px solid transparent; margin-bottom: -1px; }
.itnav a.on { color: var(--green-deep); border-bottom-color: var(--green); }
.ok { color: var(--green-deep); font-weight: 700; }
.kpi { text-decoration: none; color: inherit; }
.kpi-value.bad { color: var(--danger); }
.checks { list-style: none; margin: 0; padding: 0; display: grid; gap: .1rem; }
.checks li { display: grid; grid-template-columns: 9.5rem minmax(0, 1fr) auto; gap: .75rem; align-items: start; padding: .6rem 0; border-bottom: 1px solid var(--line); }
.checks li:last-child { border-bottom: 0; }
.checks .pill { justify-self: start; }
.sub { color: var(--muted); font-size: .88rem; margin: .1rem 0 0; overflow-wrap: anywhere; }
.mono { font-family: ui-monospace, Consolas, monospace; font-size: .82rem; }
.passed { margin-top: .75rem; }
.passed summary { cursor: pointer; color: var(--muted); font-weight: 700; }
.repairs { list-style: none; margin: 0; padding: 0; }
.repairs li { display: flex; justify-content: space-between; gap: 1rem; align-items: center; padding: .7rem 0; border-bottom: 1px solid var(--line); }
.unavailable { margin-top: 1rem; padding: .8rem 1rem; border-radius: 12px; background: var(--leaf-soft); }
.ask { display: grid; gap: .6rem; margin: .85rem 0; }
.field { display: grid; gap: .25rem; font-weight: 600; font-size: .9rem; flex: 1 1 10rem; }
.row { display: flex; gap: .6rem; align-items: flex-end; flex-wrap: wrap; }
.preview { background: var(--leaf-soft); border-radius: 12px; padding: .75rem 1rem; }
.preview ul { margin: .4rem 0 0; padding-left: 1.1rem; font-size: .88rem; }
.control { display: flex; justify-content: space-between; gap: 1rem; align-items: center; margin-bottom: .75rem; }
.control.changed { border: 1.5px solid var(--danger); }
.rowlink { display: flex; justify-content: space-between; gap: .75rem; width: 100%; text-decoration: none; color: inherit; }
li.sel { background: var(--leaf-soft); border-radius: 10px; }
.right-col { display: grid; justify-items: end; gap: .25rem; }
.case { display: grid; gap: .6rem; }
.case textarea { min-height: 3.2rem; }
.timeline { list-style: none; padding: 0; margin: .5rem 0 0; display: grid; gap: .6rem; }
.timeline li { border-left: 3px solid var(--leaf); padding-left: .75rem; }
.timeline p { margin: .15rem 0 0; }
.filters { margin-bottom: .8rem; }
.note { margin-top: .8rem; }
.nowrap { white-space: nowrap; }
.table-wrap { overflow-x: auto; }
@media (max-width: 640px) {
  .checks li { grid-template-columns: 1fr; gap: .3rem; }
  .repairs li, .control { flex-direction: column; align-items: flex-start; }
}
</style>
