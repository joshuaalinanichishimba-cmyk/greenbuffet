<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type PayRates, type PayrollRun, type Payslip } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'

const runs = ref<PayrollRun[]>([])
const rates = ref<PayRates | null>(null)
const open = ref<PayrollRun | null>(null)
const slip = ref<{ run: PayrollRun; p: Payslip } | null>(null)
const period = ref(new Date().toISOString().slice(0, 7))
const error = ref('')
const busy = ref(false)
const editingRates = ref(false)
const bandsText = ref('')

const mayPrepare = computed(() => session.can('payroll.manage'))
const mayApprove = computed(() => session.can('payroll.approve'))
const mayPay = computed(() => session.can('payroll.pay'))

async function load() {
  error.value = ''
  try {
    const [r, x] = await Promise.all([api.payrollRuns(), api.payRates()])
    runs.value = r
    rates.value = x
    if (open.value) open.value = r.find((run) => run.id === open.value!.id) ?? null
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load payroll.'
  }
}
onMounted(load)

async function act(action: () => Promise<PayrollRun>) {
  busy.value = true
  error.value = ''
  try {
    open.value = await action()
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not do that.'
  } finally {
    busy.value = false
  }
}

function startRates() {
  if (!rates.value) return
  bandsText.value = rates.value.paye_bands
    .map(([upper, rate]) => `${upper === null ? 'above' : (upper / 100).toFixed(2)} ${rate}`)
    .join('\n')
  editingRates.value = true
}

function printSlip() {
  window.print()
}

async function saveRates() {
  if (!rates.value) return
  const bands: (number | null)[][] = []
  for (const line of bandsText.value.split('\n').map((l) => l.trim()).filter(Boolean)) {
    const [upper, rate] = line.split(/\s+/)
    const top = upper.toLowerCase() === 'above' ? null : toNgwee(upper)
    if ((top === null && upper.toLowerCase() !== 'above') || !Number.isFinite(Number(rate))) {
      error.value = `Could not read "${line}". Write each band as: upper-limit rate, and the last as: above rate.`
      return
    }
    bands.push([top, Number(rate)])
  }
  try {
    rates.value = await api.savePayRates({ ...rates.value, paye_bands: bands })
    editingRates.value = false
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save the rates.'
  }
}
</script>

<template>
  <AppShell>
    <div class="screen-only">
      <h1>Payroll</h1>
      <p class="lead">
        Prepare the month, have someone else approve it, then record it as paid. Approval puts it in
        the books; payslips keep the figures they were calculated with.
      </p>

      <p v-if="error" class="error">{{ error }}</p>

      <p v-if="rates && !rates.checked" class="notice warn">
        The tax and contribution rates have not been confirmed yet. {{ rates.note }}
        <button v-if="mayPrepare" class="btn-quiet btn-small" @click="startRates">Check the rates</button>
      </p>

      <section v-if="editingRates && rates" class="panel">
        <b>Rates, per month</b>
        <div class="grid">
          <label class="field span2">PAYE bands — one per line: upper limit in kwacha, then the rate
            <textarea v-model="bandsText" rows="5"></textarea>
          </label>
          <label class="field">NAPSA %<input v-model.number="rates.napsa_percent" type="text" /></label>
          <label class="field">NAPSA ceiling (ngwee)<input v-model.number="rates.napsa_ceiling_ngwee" type="text" /></label>
          <label class="field">NHIMA % of basic<input v-model.number="rates.nhima_percent" type="text" /></label>
          <label class="field">Working days a month<input v-model.number="rates.working_days" type="text" /></label>
        </div>
        <label class="check"><input v-model="rates.checked" type="checkbox" /> I have confirmed these with ZRA, NAPSA and NHIMA</label>
        <div class="row">
          <button class="btn-primary" @click="saveRates">Save the rates</button>
          <button class="btn-quiet" @click="editingRates = false">Cancel</button>
        </div>
      </section>

      <div v-if="mayPrepare" class="toolbar">
        <label class="field">Month<input v-model="period" type="month" /></label>
        <button class="btn-primary" :disabled="busy" @click="act(() => api.preparePayroll(period))">Prepare payroll</button>
        <button v-if="rates?.checked" class="btn-quiet btn-small" @click="startRates">Rates</button>
      </div>

      <div class="table-wrap">
        <table>
          <thead><tr><th>Month</th><th>Gross</th><th>Net to staff</th><th>PAYE</th><th>NAPSA</th><th>NHIMA</th><th>State</th><th></th></tr></thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id" :class="{ chosen: open?.id === r.id }">
              <td><b>{{ r.period }}</b></td>
              <td class="num">{{ kwacha(r.gross_ngwee) }}</td>
              <td class="num">{{ kwacha(r.net_ngwee) }}</td>
              <td class="num">{{ kwacha(r.paye_ngwee) }}</td>
              <td class="num">{{ kwacha(r.napsa_ngwee) }}</td>
              <td class="num">{{ kwacha(r.nhima_ngwee) }}</td>
              <td><span class="tag" :class="{ off: r.status === 'draft' }">{{ r.status }}</span></td>
              <td><button class="btn-quiet btn-small" @click="open = r">Open</button></td>
            </tr>
            <tr v-if="!runs.length"><td colspan="8" class="muted">No payroll yet.</td></tr>
          </tbody>
        </table>
      </div>

      <section v-if="open" class="panel run">
        <header>
          <div>
            <b>{{ open.period }}</b>
            <span class="muted">
              prepared by {{ open.created_by }}<template v-if="open.approved_by"> · approved by {{ open.approved_by }}</template>
              <template v-if="open.paid_by"> · paid by {{ open.paid_by }}</template>
              · costs the business {{ kwacha(open.employer_cost_ngwee) }}
            </span>
          </div>
          <div class="row">
            <button v-if="mayPrepare && open.status === 'draft'" class="btn-quiet btn-small" :disabled="busy"
                    @click="act(() => api.preparePayroll(open!.period))">Recalculate</button>
            <button v-if="mayApprove && open.status === 'draft'" class="btn-primary btn-small" :disabled="busy"
                    @click="act(() => api.approvePayroll(open!.id))">Approve</button>
            <button v-if="mayPay && open.status === 'approved'" class="btn-primary btn-small" :disabled="busy"
                    @click="act(() => api.payPayroll(open!.id))">Record as paid</button>
          </div>
        </header>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Employee</th><th>Gross</th><th>PAYE</th><th>NAPSA</th><th>NHIMA</th><th>Net</th><th></th></tr></thead>
            <tbody>
              <tr v-for="p in open.payslips" :key="p.id">
                <td><b>{{ p.employee_name }}</b><small class="muted">{{ p.job_title }} · {{ p.days_worked }} days clocked</small></td>
                <td class="num">{{ kwacha(p.gross_ngwee) }}</td>
                <td class="num">{{ kwacha(p.paye_ngwee) }}</td>
                <td class="num">{{ kwacha(p.napsa_employee_ngwee) }}</td>
                <td class="num">{{ kwacha(p.nhima_employee_ngwee) }}</td>
                <td class="num"><b>{{ kwacha(p.net_ngwee) }}</b></td>
                <td><button class="btn-quiet btn-small" @click="slip = { run: open!, p }">Payslip</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <div v-if="slip" class="backdrop screen-only" @click.self="slip = null">
      <section class="panel slip-view">
        <header><b>Payslip</b>
          <span class="row"><button class="btn-primary btn-small" @click="printSlip">Print</button>
          <button class="btn-quiet btn-small" @click="slip = null">Close</button></span></header>
        <p class="muted">The printed copy is laid out for A5 or A4.</p>
      </section>
    </div>

    <article v-if="slip" class="payslip print-area">
      <h2>The Green Buffet</h2>
      <p>Liberty Mall, Kitwe · Payslip for {{ slip.run.period }}</p>
      <table class="who"><tbody>
        <tr><td>Employee</td><td>{{ slip.p.employee_name }} ({{ slip.p.employee_number }})</td></tr>
        <tr><td>Job</td><td>{{ slip.p.job_title }}</td></tr>
        <tr><td>NAPSA</td><td>{{ slip.p.napsa_number || '—' }}</td></tr>
        <tr><td>TPIN</td><td>{{ slip.p.tpin || '—' }}</td></tr>
      </tbody></table>
      <table class="figures"><tbody>
        <tr><td>Basic pay</td><td>{{ kwacha(slip.p.basic_ngwee) }}</td></tr>
        <tr v-if="slip.p.allowances_ngwee"><td>Allowances</td><td>{{ kwacha(slip.p.allowances_ngwee) }}</td></tr>
        <tr v-if="slip.p.unpaid_deduction_ngwee"><td>Unpaid leave, {{ slip.p.unpaid_days }} days</td><td>−{{ kwacha(slip.p.unpaid_deduction_ngwee) }}</td></tr>
        <tr class="sum"><td>Gross pay</td><td>{{ kwacha(slip.p.gross_ngwee) }}</td></tr>
        <tr><td>PAYE</td><td>−{{ kwacha(slip.p.paye_ngwee) }}</td></tr>
        <tr><td>NAPSA</td><td>−{{ kwacha(slip.p.napsa_employee_ngwee) }}</td></tr>
        <tr><td>NHIMA</td><td>−{{ kwacha(slip.p.nhima_employee_ngwee) }}</td></tr>
        <tr class="sum net"><td>Net pay</td><td>{{ kwacha(slip.p.net_ngwee) }}</td></tr>
      </tbody></table>
      <p class="small">
        Paid by the employer on top: NAPSA {{ kwacha(slip.p.napsa_employer_ngwee) }},
        NHIMA {{ kwacha(slip.p.nhima_employer_ngwee) }}.
      </p>
    </article>
  </AppShell>
</template>

<style scoped>
.warn { background: var(--warn-soft); color: var(--warn); display: flex; gap: 0.7rem; align-items: center; flex-wrap: wrap; }
.toolbar { display: flex; gap: 0.7rem; align-items: end; flex-wrap: wrap; margin: 1rem 0; }
.grid { display: grid; gap: 0.7rem; grid-template-columns: 1fr; margin-top: 0.7rem; }
textarea { font: inherit; padding: 0.5rem; border: 1.5px solid var(--line); border-radius: 10px; background: var(--paper); color: var(--ink); }
.row { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
.check { display: flex; gap: 0.4rem; align-items: center; margin: 0.7rem 0; font-size: 0.9rem; }
.num { white-space: nowrap; }
td small { display: block; font-size: 0.76rem; }
tr.chosen td { background: var(--leaf-soft); }
.run { margin-top: 1rem; }
.run > header { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.8rem; }
.run > header span.muted { display: block; font-size: 0.84rem; }
.backdrop { position: fixed; inset: 0; background: rgba(12, 30, 16, 0.45); display: grid; place-items: center; z-index: 20; padding: 1rem; }
.slip-view { max-width: 360px; width: 100%; }
.slip-view header { display: flex; justify-content: space-between; align-items: center; }
.payslip { display: none; }
@media (min-width: 760px) { .grid { grid-template-columns: repeat(4, 1fr); } .span2 { grid-column: span 2; grid-row: span 2; } }
@media print {
  .screen-only, :global(header), :global(nav), :global(.expiry) { display: none !important; }
  .payslip { display: block; max-width: 140mm; font-size: 11pt; color: #000; }
  .payslip h2 { margin: 0; }
  .payslip table { width: 100%; border: 0; border-collapse: collapse; margin-top: 0.6rem; background: none; }
  .payslip td { border: 0; padding: 0.15rem 0; }
  .payslip td:last-child { text-align: right; }
  .payslip .sum td { border-top: 1px solid #000; font-weight: 700; }
  .payslip .net td { font-size: 13pt; }
  .payslip .small { font-size: 9pt; margin-top: 0.8rem; }
}
</style>
