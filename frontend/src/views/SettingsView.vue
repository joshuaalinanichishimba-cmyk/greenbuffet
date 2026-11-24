<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import SubNav from '../components/SubNav.vue'
import { ApiError, api, getToken, type BackupFile, type StoredFile } from '../services/api'
import { fileUrl, forgetFile } from '../services/files'
import { session } from '../stores/session'

const tab = ref<'business' | 'files' | 'backups'>('business')
const values = reactive<Record<string, string>>({})
const documents = ref<StoredFile[]>([])
const thumbs = ref<Record<string, string>>({})
const backups = ref<BackupFile[]>([])
const error = ref('')
const notice = ref('')
const saving = ref(false)
const working = ref(false)

const mayEdit = computed(() => session.can('settings.edit'))

// The demo's Settings screen, section by section.
const businessFields = [
  { key: 'business_name', label: 'Business name', hint: 'Shown on receipts and reports' },
  { key: 'business.social', label: 'Social handle', hint: '' },
  { key: 'business_phone', label: 'Phone numbers', hint: '' },
  { key: 'business_address', label: 'Location', hint: '' },
  { key: 'business_email', label: 'Email', hint: '' },
  { key: 'business_tpin', label: 'TPIN', hint: 'Printed on receipts' },
  { key: 'business_vat_number', label: 'VAT number', hint: '' },
  { key: 'vat_rate', label: 'VAT rate %', hint: 'Included in prices, not added at the till. Used only while VAT-registered (below).' },
  { key: 'receipt_footer', label: 'Receipt footer', hint: 'The last line on every receipt' },
  { key: 'service_note', label: 'Note on the till', hint: 'Shown to cashiers, for example today’s special' },
]

const days = [
  { key: 'hours.sun', label: 'Sunday' },
  { key: 'hours.mon', label: 'Monday' },
  { key: 'hours.tue', label: 'Tuesday' },
  { key: 'hours.wed', label: 'Wednesday' },
  { key: 'hours.thu', label: 'Thursday' },
  { key: 'hours.fri', label: 'Friday' },
  { key: 'hours.sat', label: 'Saturday' },
]

// The topping charge is stored in ngwee and edited in kwacha.
const toppingKwacha = computed({
  get: () => ((Number(values['menu.topping_charge_ngwee'] || 0)) / 100).toString(),
  set: (v: string) => (values['menu.topping_charge_ngwee'] = String(Math.round(Number(v || 0) * 100))),
})

// None of these is connected. Each says what connecting it takes, so the
// owner knows it is an application to a company, not a setting.
const integrations = [
  { name: 'Airtel Money', status: 'Not connected', what: 'Needs an Airtel merchant account. Until then, enter the Airtel reference at the till.' },
  { name: 'MTN MoMo', status: 'Not connected', what: 'Needs an MTN MoMo merchant account. Until then, enter the MTN reference at the till.' },
  { name: 'Zamtel Kwacha', status: 'Not connected', what: 'Needs a Zamtel merchant account.' },
]

async function load() {
  error.value = ''
  try {
    const s = await api.settings()
    Object.assign(values, s.values)
    documents.value = await api.storedFiles()
    await loadThumbs()
    if (mayEdit.value) backups.value = await api.backups()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load settings.'
  }
}
async function loadThumbs() {
  for (const doc of documents.value) {
    if (!doc.thumb_url || thumbs.value[doc.id]) continue
    try {
      thumbs.value = { ...thumbs.value, [doc.id]: await fileUrl(doc.id, true) }
    } catch {
      /* the picture is a nicety; the row still works without it */
    }
  }
}

onMounted(load)

async function save() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const s = await api.saveSettings({ ...values })
    Object.assign(values, s.values)
    notice.value = 'Saved. Receipts and reports use these from now on.'
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save.'
  } finally {
    saving.value = false
  }
}

async function addFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  working.value = true
  error.value = ''
  try {
    await api.uploadFile(file, { kind: 'other', attached_to: 'business' })
    documents.value = await api.storedFiles()
    await loadThumbs()
    notice.value = `${file.name} stored.`
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not store that file.'
  } finally {
    working.value = false
    input.value = ''
  }
}

async function removeFile(doc: StoredFile) {
  if (!window.confirm(`Remove ${doc.name}? This cannot be undone.`)) return
  try {
    await api.deleteFile(doc.id)
    forgetFile(doc.id)
    documents.value = documents.value.filter((d) => d.id !== doc.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not remove it.'
  }
}

function openFile(doc: StoredFile) {
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
  fetch(`${base}/settings/files/${doc.id}`, { headers: { Authorization: `Bearer ${getToken()}` } })
    .then((r) => r.blob())
    .then((blob) => window.open(URL.createObjectURL(blob), '_blank'))
    .catch(() => (error.value = 'Could not open that file.'))
}

async function takeBackup() {
  working.value = true
  error.value = ''
  notice.value = ''
  try {
    const made = await api.makeBackup()
    backups.value = await api.backups()
    notice.value = `${made.name} written, ${Math.round(made.size_bytes / 1024)} KB.`
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'The backup did not run.'
  } finally {
    working.value = false
  }
}

function size(bytes: number) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`
}

function when(iso: string) {
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lusaka',
  })
}
</script>

<template>
  <AppShell>
    <h1>Settings</h1>
    <p class="lead">The details that appear on receipts and reports, the files you keep, and backups.</p>
    <SubNav :links="[{ to: '/settings', label: 'Settings' }, { to: '/activity', label: 'Activity log', show: session.can('audit.view') }]" />

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <div class="tabs">
      <button :class="{ on: tab === 'business' }" @click="tab = 'business'">The business</button>
      <button :class="{ on: tab === 'files' }" @click="tab = 'files'">Files</button>
      <button v-if="mayEdit" :class="{ on: tab === 'backups' }" @click="tab = 'backups'">Backups</button>
    </div>

    <template v-if="tab === 'business'">
      <section class="card set">
        <h2>Business details</h2>
        <div class="grid-2">
          <label v-for="f in businessFields" :key="f.key" class="field">
            {{ f.label }}
            <input v-model="values[f.key]" type="text" :disabled="!mayEdit" />
            <small v-if="f.hint" class="muted">{{ f.hint }}</small>
          </label>
          <label class="field">
            Charge per bowl topping over five (K)
            <input v-model="toppingKwacha" type="number" min="0" step="0.5" :disabled="!mayEdit" />
          </label>
        </div>
      </section>

      <section class="card set">
        <h2>Service and loyalty</h2>
        <div class="grid-2">
          <label class="field">
            Base preparation time (minutes)
            <input v-model="values['service.prep_minutes']" type="number" min="1" max="120" :disabled="!mayEdit" />
            <small class="muted">The counter quotes this plus two minutes for every order in the kitchen.</small>
          </label>
          <label class="field">
            Stamps for a free bowl or burrito
            <input v-model="values['loyalty.stamps_needed']" type="number" min="1" max="50" :disabled="!mayEdit" />
            <small class="muted">“Collect {{ values['loyalty.stamps_needed'] || 8 }} and the next one is free.” Which sections earn stamps is set on the Menu screen.</small>
          </label>
        </div>
        <label class="switch" style="margin-top: .8rem">
          <input
            type="checkbox"
            :checked="values['loyalty.enabled'] !== 'false'"
            :disabled="!mayEdit"
            @change="values['loyalty.enabled'] = ($event.target as HTMLInputElement).checked ? 'true' : 'false'"
          />
          Give stamps and the free bowl
        </label>
      </section>

      <section class="card set">
        <h2>Cash controls at the till</h2>
        <div class="limits">
          <label class="field">
            A till out by more than (K)
            <input
              :value="((Number(values['till.variance_limit_ngwee'] ?? 2000)) / 100).toString()"
              type="text" inputmode="decimal" :disabled="!mayEdit"
              @change="values['till.variance_limit_ngwee'] = String(Math.round(Number(($event.target as HTMLInputElement).value || 0) * 100))"
            />
            <small class="muted">needs the cashier's reason and a manager's review.</small>
          </label>
          <label class="field">
            A cashier's discount over (%)
            <input v-model="values['till.discount_limit_percent']" type="text" inputmode="numeric" :disabled="!mayEdit" />
            <small class="muted">needs a manager to approve it on the till. Promotion codes are not affected.</small>
          </label>
        </div>
      </section>

      <section class="card set">
        <h2>Tax</h2>
        <label class="switch">
          <input
            type="checkbox"
            :checked="values['tax.vat_registered'] !== 'false'"
            :disabled="!mayEdit"
            @change="values['tax.vat_registered'] = ($event.target as HTMLInputElement).checked ? 'true' : 'false'"
          />
          The business is registered for VAT
        </label>
        <small class="muted">
          On: VAT at the rate above is inside every price and printed on receipts. Off: no VAT on new sales or
          receipts. Past sales keep the VAT they were sold with. Items marked 0% on the Menu stay exempt either way.
        </small>
      </section>

      <section class="card set">
        <h2>Sign-in screen</h2>
        <label class="switch">
          <input
            type="checkbox"
            :checked="values['signin.show_accounts'] !== 'false'"
            :disabled="!mayEdit"
            @change="values['signin.show_accounts'] = ($event.target as HTMLInputElement).checked ? 'true' : 'false'"
          />
          Show each person under their kind of account, so one tap fills in their email
        </label>
        <small class="muted">Passwords are always typed. Switch this off to make everyone type their email as well.</small>
      </section>

      <section class="card set">
        <h2>Opening hours</h2>
        <div class="hours">
          <label v-for="d in days" :key="d.key" class="field">
            {{ d.label }}
            <input v-model="values[d.key]" type="text" placeholder="08:30-19:30 or closed" :disabled="!mayEdit" />
          </label>
        </div>
      </section>

      <div v-if="mayEdit" class="row" style="margin-bottom: 1.4rem">
        <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save settings' }}</button>
      </div>
      <p v-else class="muted">Your role can see these but not change them.</p>

      <section class="card set">
        <h2>Integrations</h2>
        <div class="integrations">
          <article v-for="i in integrations" :key="i.name" class="integration">
            <div class="spread">
              <b>{{ i.name }}</b>
              <span class="pill" :class="i.status === 'By hand' ? 'warn' : 'neutral'">{{ i.status }}</span>
            </div>
            <p class="muted">{{ i.what }}</p>
          </article>
        </div>
      </section>
    </template>

    <section v-else-if="tab === 'files'">
      <div class="toolbar">
        <label v-if="mayEdit" class="btn-quiet btn-small upload">
          {{ working ? 'Storing…' : 'Store a file' }}
          <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" @change="addFile" />
        </label>
        <span class="muted">Images and PDFs, up to 8 MB. Dish photographs are added on the Menu screen.</span>
      </div>
      <p v-if="!documents.length" class="muted">Nothing stored yet.</p>
      <ul v-else class="files">
        <li v-for="d in documents" :key="d.id" class="panel file">
          <img v-if="thumbs[d.id]" :src="thumbs[d.id]" alt="" class="thumb" />
          <span v-else class="thumb doc">{{ d.media_type.includes('pdf') ? 'PDF' : 'FILE' }}</span>
          <span class="about">
            <b>{{ d.name }}</b>
            <small class="muted">{{ d.kind }} · {{ size(d.size_bytes) }} · {{ when(d.at) }}<template v-if="d.by"> · {{ d.by }}</template></small>
          </span>
          <span class="row">
            <button class="btn-quiet btn-small" @click="openFile(d)">Open</button>
            <button v-if="mayEdit" class="btn-quiet btn-small" @click="removeFile(d)">Remove</button>
          </span>
        </li>
      </ul>
    </section>

    <section v-else class="panel">
      <b>Backups</b>
      <p class="muted">
        A backup is a complete copy of the database. Keep one off this computer — a disk that fails
        takes its own backups with it.
      </p>
      <div class="row">
        <button class="btn-primary" :disabled="working" @click="takeBackup">
          {{ working ? 'Running…' : 'Back up now' }}
        </button>
      </div>
      <p class="muted small">
        For a nightly one, run <code>.\scripts\schedule-backup.ps1</code> once as Administrator. It
        asks Windows to run the backup every night and keeps 30 days.
      </p>
      <table v-if="backups.length">
        <thead><tr><th>File</th><th>Size</th><th>Taken</th></tr></thead>
        <tbody>
          <tr v-for="b in backups" :key="b.name">
            <td>{{ b.name }}</td><td class="num">{{ size(b.size_bytes) }}</td><td class="num">{{ when(b.at) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">No backups yet.</p>
    </section>
  </AppShell>
</template>

<style scoped>

.limits { display: grid; gap: .8rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }
/* A long switch label wraps instead of pushing the page sideways on a phone. */
.set .switch { white-space: normal; align-items: flex-start; }
.set .switch input { flex: none; margin-top: .1rem; }
.form { display: grid; gap: 0.8rem; grid-template-columns: 1fr; max-width: 760px; }
.field small { font-weight: 400; }
.row { display: flex; gap: 0.5rem; }
.toolbar { display: flex; gap: 0.8rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.8rem; }
.upload { position: relative; overflow: hidden; display: inline-flex; align-items: center; cursor: pointer; }
.upload input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.files { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; }
.file { display: flex; align-items: center; gap: 0.8rem; padding: 0.6rem 0.8rem; }
.thumb { width: 56px; height: 56px; object-fit: cover; border-radius: 10px; flex: none; }
.thumb.doc { display: grid; place-items: center; background: var(--leaf-soft); color: var(--muted); font-size: 0.72rem; font-weight: 700; }
.about { flex: 1; min-width: 0; display: grid; }
.about b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.about small { font-size: 0.78rem; }
.num { white-space: nowrap; }
.small { font-size: 0.85rem; }
code { background: var(--leaf-soft); padding: 0.1rem 0.3rem; border-radius: 5px; }
@media (min-width: 720px) { .form { grid-template-columns: 1fr 1fr; } }
.set { margin-bottom: 1.2rem; }
.set h2 { margin: 0 0 1rem; font-size: 1.1rem; }
.hours { display: grid; gap: .8rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); }
.integrations { display: grid; gap: .8rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }
.integration { border: 1px solid var(--line); border-radius: 14px; padding: .8rem .9rem; }
.integration p { margin: .4rem 0 0; font-size: .88rem; }
</style>
