<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
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

const fields = [
  { key: 'business_name', label: 'Business name', hint: 'Shown on receipts and reports' },
  { key: 'business_address', label: 'Address', hint: '' },
  { key: 'business_phone', label: 'Phone', hint: '' },
  { key: 'business_email', label: 'Email', hint: '' },
  { key: 'business_tpin', label: 'TPIN', hint: 'Printed on receipts' },
  { key: 'business_vat_number', label: 'VAT number', hint: '' },
  { key: 'vat_rate', label: 'VAT rate %', hint: 'Included in prices, not added at the till' },
  { key: 'receipt_footer', label: 'Receipt footer', hint: 'The last line on every receipt' },
  { key: 'service_note', label: 'Note on the till', hint: 'Shown to cashiers, for example today’s special' },
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

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <div class="tabs">
      <button class="tab" :class="{ on: tab === 'business' }" @click="tab = 'business'">The business</button>
      <button class="tab" :class="{ on: tab === 'files' }" @click="tab = 'files'">Files</button>
      <button v-if="mayEdit" class="tab" :class="{ on: tab === 'backups' }" @click="tab = 'backups'">Backups</button>
    </div>

    <section v-if="tab === 'business'" class="panel form">
      <label v-for="f in fields" :key="f.key" class="field">
        {{ f.label }}
        <input v-model="values[f.key]" type="text" :disabled="!mayEdit" />
        <small v-if="f.hint" class="muted">{{ f.hint }}</small>
      </label>
      <div v-if="mayEdit" class="row">
        <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      </div>
      <p v-else class="muted">Your role can see these but not change them.</p>
    </section>

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
.tabs { display: flex; gap: 0.4rem; margin: 1rem 0; flex-wrap: wrap; }
.tab { background: #fff; border: 1px solid #cfd6cb; }
.tab.on { background: var(--green); color: #fff; border-color: var(--green); }
.form { display: grid; gap: 0.8rem; grid-template-columns: 1fr; max-width: 760px; }
.field small { font-weight: 400; }
.row { display: flex; gap: 0.5rem; }
.toolbar { display: flex; gap: 0.8rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.8rem; }
.upload { position: relative; overflow: hidden; display: inline-flex; align-items: center; cursor: pointer; }
.upload input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.files { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; }
.file { display: flex; align-items: center; gap: 0.8rem; padding: 0.6rem 0.8rem; }
.thumb { width: 56px; height: 56px; object-fit: cover; border-radius: 10px; flex: none; }
.thumb.doc { display: grid; place-items: center; background: #eef2ea; color: var(--muted); font-size: 0.72rem; font-weight: 700; }
.about { flex: 1; min-width: 0; display: grid; }
.about b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.about small { font-size: 0.78rem; }
.num { white-space: nowrap; }
.small { font-size: 0.85rem; }
code { background: #eef2ea; padding: 0.1rem 0.3rem; border-radius: 5px; }
@media (min-width: 720px) { .form { grid-template-columns: 1fr 1fr; } }
</style>
