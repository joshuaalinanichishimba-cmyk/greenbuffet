<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type BookAccount, type JournalEntry, type LedgerRow } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'

const entries = ref<JournalEntry[]>([])
const accounts = ref<BookAccount[]>([])
const ledger = ref<{ account: BookAccount; rows: LedgerRow[] } | null>(null)
const tab = ref<'journal' | 'accounts'>('journal')
const sourceFilter = ref('')
const loading = ref(true)
const error = ref('')
const busyId = ref('')

const mayWrite = computed(() => session.canAny('journal.post', 'books.edit'))
const mayApprove = computed(() => session.can('journal.approve'))

const draft = reactive({
  open: false,
  memo: '',
  reference: '',
  lines: [] as { account_code: string; debit: string; credit: string; memo: string }[],
  saving: false,
})

const sources = [
  { id: '', label: 'Everything' },
  { id: 'sale', label: 'Sales' },
  { id: 'refund', label: 'Refunds' },
  { id: 'purchase', label: 'Deliveries' },
  { id: 'stock', label: 'Stock' },
  { id: 'shift', label: 'Till counts' },
  { id: 'manual', label: 'Written by hand' },
]

const draftDebit = computed(() =>
  draft.lines.reduce((t, l) => t + (toNgwee(l.debit || '0') ?? 0), 0),
)
const draftCredit = computed(() =>
  draft.lines.reduce((t, l) => t + (toNgwee(l.credit || '0') ?? 0), 0),
)
const draftBalanced = computed(() => draftDebit.value > 0 && draftDebit.value === draftCredit.value)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [e, a] = await Promise.all([
      api.journal(sourceFilter.value || undefined),
      api.bookAccounts(),
    ])
    entries.value = e
    accounts.value = a
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Could not load the journal.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

function startDraft() {
  draft.open = true
  draft.memo = ''
  draft.reference = ''
  draft.lines = [
    { account_code: accounts.value[0]?.code ?? '', debit: '', credit: '', memo: '' },
    { account_code: accounts.value[0]?.code ?? '', debit: '', credit: '', memo: '' },
  ]
}

async function saveDraft() {
  error.value = ''
  if (draft.memo.trim().length < 3) {
    error.value = 'Say what the entry is for.'
    return
  }
  if (!draftBalanced.value) {
    error.value = 'Debits and credits must match before this can be written.'
    return
  }
  draft.saving = true
  try {
    await api.createJournalEntry({
      memo: draft.memo.trim(),
      reference: draft.reference.trim(),
      lines: draft.lines
        .filter((l) => (toNgwee(l.debit || '0') ?? 0) || (toNgwee(l.credit || '0') ?? 0))
        .map((l) => ({
          account_code: l.account_code,
          debit_ngwee: toNgwee(l.debit || '0') ?? 0,
          credit_ngwee: toNgwee(l.credit || '0') ?? 0,
          memo: l.memo.trim(),
        })),
    })
    draft.open = false
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not write the entry.'
  } finally {
    draft.saving = false
  }
}

async function approve(entry: JournalEntry) {
  busyId.value = entry.id
  error.value = ''
  try {
    await api.approveJournalEntry(entry.id)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not approve that entry.'
  } finally {
    busyId.value = ''
  }
}

async function reverse(entry: JournalEntry) {
  const reason = window.prompt(`Why is ${entry.number} being reversed?`)
  if (!reason || reason.trim().length < 3) return
  busyId.value = entry.id
  error.value = ''
  try {
    await api.reverseJournalEntry(entry.id, reason.trim())
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not reverse that entry.'
  } finally {
    busyId.value = ''
  }
}

async function openLedger(account: BookAccount) {
  error.value = ''
  try {
    ledger.value = { account, rows: await api.ledger(account.code) }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not open that ledger.'
  }
}
</script>

<template>
  <AppShell>
    <h1>Journal</h1>
    <p class="lead">
      Every entry in the books, newest first. Sales, deliveries and till counts write themselves;
      anything else is written here and approved by someone else before it counts.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="tabs">
      <button :class="{ on: tab === 'journal' }" @click="tab = 'journal'">Entries</button>
      <button :class="{ on: tab === 'accounts' }" @click="tab = 'accounts'">Chart of accounts</button>
      <span class="spacer" />
      <button v-if="mayWrite && tab === 'journal'" class="btn-primary btn-small" @click="startDraft">
        Write an entry
      </button>
    </div>

    <section v-if="draft.open" class="panel draft">
      <header>
        <b>New entry</b>
        <button class="btn-quiet btn-small" @click="draft.open = false">Close</button>
      </header>
      <div class="head-grid">
        <label class="field">
          What is it for
          <input v-model="draft.memo" type="text" placeholder="November rent" />
        </label>
        <label class="field">
          Reference
          <input v-model="draft.reference" type="text" placeholder="optional" />
        </label>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Account</th><th>Debit</th><th>Credit</th><th>Note</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(line, index) in draft.lines" :key="index">
              <td>
                <select v-model="line.account_code">
                  <option v-for="a in accounts" :key="a.id" :value="a.code">
                    {{ a.code }} · {{ a.name }}
                  </option>
                </select>
              </td>
              <td><input v-model="line.debit" type="text" inputmode="decimal" class="money" /></td>
              <td><input v-model="line.credit" type="text" inputmode="decimal" class="money" /></td>
              <td><input v-model="line.memo" type="text" /></td>
              <td><button class="btn-quiet btn-small" @click="draft.lines.splice(index, 1)">Remove</button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td><b>Totals</b></td>
              <td class="num"><b>{{ kwacha(draftDebit) }}</b></td>
              <td class="num"><b>{{ kwacha(draftCredit) }}</b></td>
              <td colspan="2" :class="draftBalanced ? 'ok' : 'off'">
                {{ draftBalanced ? 'Balanced' : `Out by ${kwacha(Math.abs(draftDebit - draftCredit))}` }}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div class="row">
        <button class="btn-quiet btn-small" @click="draft.lines.push({ account_code: accounts[0]?.code ?? '', debit: '', credit: '', memo: '' })">
          Add a line
        </button>
        <button class="btn-primary" :disabled="draft.saving || !draftBalanced" @click="saveDraft">
          Write it
        </button>
      </div>
      <p class="muted">
        It is saved as a draft. Someone else approves it before it reaches the books.
      </p>
    </section>

    <template v-if="tab === 'journal'">
      <label class="field filter">
        Show
        <select v-model="sourceFilter" @change="load">
          <option v-for="s in sources" :key="s.id" :value="s.id">{{ s.label }}</option>
        </select>
      </label>

      <p v-if="loading" class="muted">Loading…</p>
      <p v-else-if="!entries.length" class="muted">Nothing in the journal yet.</p>

      <ul v-else class="entries">
        <li v-for="e in entries" :key="e.id" class="panel entry" :class="{ draft: e.status === 'draft', undone: e.reversed_by_id }">
          <header>
            <div>
              <b>{{ e.number }}</b>
              <span class="muted">{{ e.entry_date }} · {{ e.memo }}</span>
            </div>
            <div class="state">
              <span v-if="e.status === 'draft'" class="tag off">Waiting for approval</span>
              <span v-else-if="e.reversed_by_id" class="tag off">Reversed</span>
              <span v-else-if="e.reverses_id" class="tag off">Reversal</span>
              <span v-else class="tag">Posted</span>
              <b class="amount">{{ kwacha(e.total_ngwee) }}</b>
            </div>
          </header>
          <table class="lines">
            <tbody>
              <tr v-for="(line, i) in e.lines" :key="i">
                <td class="muted code">{{ line.account_code }}</td>
                <td>{{ line.account_name }}<small v-if="line.memo" class="muted">{{ line.memo }}</small></td>
                <td class="num">{{ line.debit_ngwee ? kwacha(line.debit_ngwee) : '' }}</td>
                <td class="num">{{ line.credit_ngwee ? kwacha(line.credit_ngwee) : '' }}</td>
              </tr>
            </tbody>
          </table>
          <footer>
            <span class="muted">
              {{ e.reference ? `from ${e.reference}` : 'written by hand' }}
              <template v-if="e.created_by"> · {{ e.created_by }}</template>
              <template v-if="e.approved_by"> · approved by {{ e.approved_by }}</template>
            </span>
            <span class="actions">
              <button
                v-if="mayApprove && e.status === 'draft'"
                class="btn-primary btn-small"
                :disabled="busyId === e.id"
                @click="approve(e)"
              >
                Approve
              </button>
              <button
                v-if="mayApprove && e.status === 'posted' && !e.reversed_by_id && !e.reverses_id"
                class="btn-quiet btn-small"
                :disabled="busyId === e.id"
                @click="reverse(e)"
              >
                Reverse
              </button>
            </span>
          </footer>
        </li>
      </ul>
    </template>

    <template v-else>
      <p v-if="loading" class="muted">Loading…</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>Code</th><th>Account</th><th>Kind</th><th>Balance</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in accounts" :key="a.id">
              <td class="num muted">{{ a.code }}</td>
              <td>
                <b>{{ a.name }}</b>
                <small v-if="a.description" class="muted">{{ a.description }}</small>
              </td>
              <td>{{ a.type_label }}</td>
              <td class="num">{{ kwacha(a.balance_ngwee) }}</td>
              <td><button class="btn-quiet btn-small" @click="openLedger(a)">Ledger</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <div v-if="ledger" class="backdrop" @click.self="ledger = null">
      <section class="panel slip">
        <header>
          <b>{{ ledger.account.code }} · {{ ledger.account.name }}</b>
          <button class="btn-quiet btn-small" @click="ledger = null">Close</button>
        </header>
        <p v-if="!ledger.rows.length" class="muted">Nothing posted to this account yet.</p>
        <div v-else class="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Entry</th><th>What</th><th>Debit</th><th>Credit</th><th>Balance</th></tr></thead>
            <tbody>
              <tr v-for="row in ledger.rows" :key="row.entry_number + row.memo">
                <td class="num">{{ row.at }}</td>
                <td class="num muted">{{ row.entry_number }}</td>
                <td>{{ row.memo }}<small v-if="row.reference" class="muted">{{ row.reference }}</small></td>
                <td class="num">{{ row.debit_ngwee ? kwacha(row.debit_ngwee) : '' }}</td>
                <td class="num">{{ row.credit_ngwee ? kwacha(row.credit_ngwee) : '' }}</td>
                <td class="num"><b>{{ kwacha(row.balance_ngwee) }}</b></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.spacer { flex: 1; }
.filter { max-width: 220px; margin-bottom: 1rem; }
.draft { margin-bottom: 1rem; }
.draft > header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.7rem; }
.head-grid { display: grid; gap: 0.7rem; grid-template-columns: 1fr; margin-bottom: 0.8rem; }
.money { width: 7rem; }
.row { display: flex; gap: 0.8rem; align-items: center; margin-top: 0.8rem; }
.ok { color: var(--green-mid); font-weight: 700; }
.off { color: var(--danger); font-weight: 700; }

.entries { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.6rem; }
.entry { padding: 0.8rem 0.9rem; }
.entry.draft { border-color: var(--warn); }
.entry.undone { opacity: 0.65; }
.entry > header { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; align-items: baseline; }
.entry > header span { display: block; font-size: 0.84rem; }
.state { display: flex; gap: 0.6rem; align-items: baseline; }
.amount { font-size: 1.05rem; }
.lines { margin: 0.6rem 0; border: 0; background: none; }
.lines td { border: 0; padding: 0.18rem 0.5rem 0.18rem 0; font-size: 0.9rem; }
.lines .code { width: 3.5rem; }
.lines small { display: block; font-size: 0.76rem; }
.entry > footer { display: flex; justify-content: space-between; gap: 0.8rem; align-items: center; flex-wrap: wrap; border-top: 1px solid var(--line); padding-top: 0.5rem; }
.entry > footer .muted { font-size: 0.82rem; }
.actions { display: flex; gap: 0.4rem; }
.num { text-align: right; white-space: nowrap; }
td small { display: block; font-size: 0.76rem; }
.backdrop { position: fixed; inset: 0; background: rgba(12, 30, 16, 0.45); display: grid; place-items: center; padding: 1rem; z-index: 20; }
.slip { max-width: 720px; width: 100%; max-height: 86vh; overflow-y: auto; }
.slip header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.7rem; }

@media (min-width: 760px) {
  .head-grid { grid-template-columns: 2fr 1fr; }
}
</style>
