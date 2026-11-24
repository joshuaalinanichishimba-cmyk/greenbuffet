<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type AttendanceRow, type Employee, type LeaveRow, type User } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'
import MyClocking from '../components/MyClocking.vue'

const tab = ref<'staff' | 'attendance' | 'leave'>('staff')
const employees = ref<Employee[]>([])
const attendance = ref<AttendanceRow[]>([])
const leave = ref<LeaveRow[]>([])
const users = ref<User[]>([])
const error = ref('')
const notice = ref('')
const loading = ref(true)
const busy = ref(false)

const mayManage = computed(() => session.can('hr.manage'))
const mayDecide = computed(() => session.canAny('leave.approve', 'hr.manage'))
const mayClockOthers = computed(() => session.canAny('attendance.manage', 'hr.manage'))
const me = computed(() => employees.value.find((e) => e.user_id === session.user.value?.id) ?? null)

const blank = () => ({
  id: '', name: '', job_title: '', department: '', phone: '', napsa_number: '', tpin: '',
  pay_method: 'bank', pay_account: '', basic: '', allowances: '', leave_days_per_year: 24,
  start_date: '', user_id: '', is_active: true,
})
const form = reactive({ open: false, ...blank() })
const leaveForm = reactive({ open: false, employee_id: '', kind: 'annual', start: '', end: '', reason: '' })

// Without the staff list (a cashier, the kitchen), this screen is just your
// own clocking.
const seesStaff = computed(() => session.canAny('hr.view', 'hr.manage', 'attendance.manage'))

async function load() {
  if (!seesStaff.value) return
  loading.value = true
  error.value = ''
  try {
    const [e, a, l] = await Promise.all([api.employees(), api.attendance(), api.leaveRequests()])
    employees.value = e
    attendance.value = a
    leave.value = l
    if (session.can('staff.manage')) users.value = await api.users()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Could not load staff.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

function edit(e?: Employee) {
  Object.assign(form, blank(), { open: true })
  if (e) {
    Object.assign(form, {
      ...e,
      basic: (e.basic_ngwee / 100).toFixed(2),
      allowances: (e.allowances_ngwee / 100).toFixed(2),
      start_date: e.start_date ?? '',
      user_id: e.user_id ?? '',
    })
  }
}

async function save() {
  error.value = ''
  const basic = toNgwee(form.basic || '')
  const allowances = toNgwee(form.allowances || '0')
  if (form.name.trim().length < 3) return (error.value = 'Enter the full name.')
  if (basic === null || allowances === null) return (error.value = 'Enter basic pay and allowances as amounts.')
  busy.value = true
  try {
    const body = {
      name: form.name.trim(), job_title: form.job_title, department: form.department, phone: form.phone,
      napsa_number: form.napsa_number, tpin: form.tpin, pay_method: form.pay_method,
      pay_account: form.pay_account, basic_ngwee: basic, allowances_ngwee: allowances,
      leave_days_per_year: Number(form.leave_days_per_year) || 0,
      start_date: form.start_date || null, user_id: form.user_id || null, is_active: form.is_active,
    }
    if (form.id) await api.updateEmployee(form.id, body)
    else await api.createEmployee(body)
    form.open = false
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save.'
  } finally {
    busy.value = false
  }
}

async function clock(direction: 'in' | 'out', employeeId?: string) {
  error.value = ''
  notice.value = ''
  try {
    const row = direction === 'in' ? await api.clockIn(employeeId) : await api.clockOut(employeeId)
    notice.value = direction === 'in'
      ? `${row.employee_name} clocked in.`
      : `${row.employee_name} clocked out after ${row.hours} hours.`
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not clock that.'
  }
}

async function askLeave() {
  error.value = ''
  try {
    await api.requestLeave({ ...leaveForm })
    leaveForm.open = false
    await load()
    tab.value = 'leave'
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not ask for leave.'
  }
}

async function decide(row: LeaveRow, approve: boolean) {
  error.value = ''
  try {
    await api.decideLeave(row.id, approve)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not decide that.'
  }
}

function time(iso: string | null) {
  return iso
    ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lusaka' })
    : '—'
}
</script>

<template>
  <AppShell>
    <template v-if="!seesStaff">
      <h1>Clocking</h1>
      <p class="lead">Clock in when you start and out when you finish.</p>
      <MyClocking />
    </template>
    <template v-else>
    <h1>Staff</h1>
    <p class="lead">Who works here, when they clocked in, and their leave.</p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <section v-if="me" class="panel mine">
      <div>
        <b>{{ me.name }}</b>
        <span class="muted">{{ me.clocked_in ? 'Clocked in' : 'Not clocked in' }} · {{ me.leave_left }} days of leave left</span>
      </div>
      <div class="row">
        <button v-if="!me.clocked_in" class="btn-primary" @click="clock('in')">Clock in</button>
        <button v-else class="btn-quiet" @click="clock('out')">Clock out</button>
        <button class="btn-quiet" @click="Object.assign(leaveForm, { open: true, employee_id: me.id })">Ask for leave</button>
      </div>
    </section>

    <div class="tabs">
      <button :class="{ on: tab === 'staff' }" @click="tab = 'staff'">Employees</button>
      <button :class="{ on: tab === 'attendance' }" @click="tab = 'attendance'">Clocking</button>
      <button :class="{ on: tab === 'leave' }" @click="tab = 'leave'">Leave</button>
      <span class="spacer" />
      <button v-if="mayManage && tab === 'staff'" class="btn-primary btn-small" @click="edit()">Add an employee</button>
      <button v-if="mayDecide && tab === 'leave'" class="btn-primary btn-small"
              @click="Object.assign(leaveForm, { open: true, employee_id: employees[0]?.id ?? '' })">Record leave</button>
    </div>

    <section v-if="form.open" class="panel editor">
      <header><b>{{ form.id ? form.name : 'New employee' }}</b>
        <button class="btn-quiet btn-small" @click="form.open = false">Close</button></header>
      <div class="grid">
        <label class="field span2">Full name<input v-model="form.name" type="text" /></label>
        <label class="field">Job<input v-model="form.job_title" type="text" placeholder="Chef" /></label>
        <label class="field">Department<input v-model="form.department" type="text" placeholder="Kitchen" /></label>
        <label class="field">Basic pay a month<input v-model="form.basic" type="text" inputmode="decimal" placeholder="4000.00" /></label>
        <label class="field">Allowances a month<input v-model="form.allowances" type="text" inputmode="decimal" placeholder="0.00" /></label>
        <label class="field">NAPSA number<input v-model="form.napsa_number" type="text" /></label>
        <label class="field">TPIN<input v-model="form.tpin" type="text" /></label>
        <label class="field">Phone<input v-model="form.phone" type="text" /></label>
        <label class="field">Paid by
          <select v-model="form.pay_method"><option value="bank">Bank</option><option value="mobile">Mobile money</option><option value="cash">Cash</option></select>
        </label>
        <label class="field">Account or number<input v-model="form.pay_account" type="text" /></label>
        <label class="field">Leave days a year<input v-model.number="form.leave_days_per_year" type="text" inputmode="numeric" /></label>
        <label class="field">Started<input v-model="form.start_date" type="date" /></label>
        <label v-if="users.length" class="field">Signs in as
          <select v-model="form.user_id"><option value="">Does not sign in</option>
            <option v-for="u in users" :key="u.id" :value="u.id">{{ u.name }} · {{ u.email }}</option></select>
        </label>
      </div>
      <label class="check"><input v-model="form.is_active" type="checkbox" /> Still employed</label>
      <div class="row"><button class="btn-primary" :disabled="busy" @click="save">Save</button></div>
    </section>

    <section v-if="leaveForm.open" class="panel editor">
      <header><b>Leave</b><button class="btn-quiet btn-small" @click="leaveForm.open = false">Close</button></header>
      <div class="grid">
        <label v-if="mayDecide" class="field">Who
          <select v-model="leaveForm.employee_id"><option v-for="e in employees" :key="e.id" :value="e.id">{{ e.name }}</option></select>
        </label>
        <label class="field">Kind
          <select v-model="leaveForm.kind">
            <option value="annual">Annual</option><option value="sick">Sick</option><option value="maternity">Maternity</option>
            <option value="paternity">Paternity</option><option value="compassionate">Compassionate</option><option value="unpaid">Unpaid</option>
          </select>
        </label>
        <label class="field">From<input v-model="leaveForm.start" type="date" /></label>
        <label class="field">To<input v-model="leaveForm.end" type="date" /></label>
        <label class="field span2">Reason<input v-model="leaveForm.reason" type="text" /></label>
      </div>
      <p class="muted">Sundays are not counted. Unpaid leave comes off that month's pay.</p>
      <div class="row"><button class="btn-primary" @click="askLeave">Send</button></div>
    </section>

    <p v-if="loading" class="muted">Loading…</p>

    <div v-else-if="tab === 'staff'" class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Job</th><th>Pay a month</th><th>Leave left</th><th>Now</th><th></th></tr></thead>
        <tbody>
          <tr v-for="e in employees" :key="e.id">
            <td><b>{{ e.name }}</b><small class="muted">{{ e.number }}</small></td>
            <td>{{ e.job_title }}<small class="muted">{{ e.department }}</small></td>
            <td class="num">{{ kwacha(e.basic_ngwee + e.allowances_ngwee) }}</td>
            <td class="num">{{ e.leave_left }} of {{ e.leave_days_per_year }}</td>
            <td><span class="tag" :class="{ off: !e.clocked_in }">{{ e.clocked_in ? 'In' : 'Out' }}</span></td>
            <td class="actions">
              <button v-if="mayClockOthers" class="btn-quiet btn-small" @click="clock(e.clocked_in ? 'out' : 'in', e.id)">
                {{ e.clocked_in ? 'Clock out' : 'Clock in' }}
              </button>
              <button v-if="mayManage" class="btn-quiet btn-small" @click="edit(e)">Edit</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="tab === 'attendance'" class="table-wrap">
      <table>
        <thead><tr><th>Day</th><th>Who</th><th>In</th><th>Out</th><th>Hours</th></tr></thead>
        <tbody>
          <tr v-for="a in attendance" :key="a.id">
            <td class="num">{{ a.day }}</td><td>{{ a.employee_name }}</td>
            <td class="num">{{ time(a.clock_in) }}</td><td class="num">{{ time(a.clock_out) }}</td>
            <td class="num">{{ a.hours ?? 'still in' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="table-wrap">
      <table>
        <thead><tr><th>Who</th><th>Kind</th><th>Dates</th><th>Days</th><th>State</th><th></th></tr></thead>
        <tbody>
          <tr v-for="l in leave" :key="l.id">
            <td><b>{{ l.employee_name }}</b><small v-if="l.reason" class="muted">{{ l.reason }}</small></td>
            <td>{{ l.kind }}</td><td class="num">{{ l.start }} to {{ l.end }}</td><td class="num">{{ l.days }}</td>
            <td><span class="tag" :class="{ off: l.status !== 'approved' }">{{ l.status }}</span>
              <small v-if="l.decided_by" class="muted">{{ l.decided_by }}</small></td>
            <td class="actions">
              <template v-if="mayDecide && l.status === 'pending'">
                <button class="btn-primary btn-small" @click="decide(l, true)">Approve</button>
                <button class="btn-quiet btn-small" @click="decide(l, false)">Decline</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    </template>
  </AppShell>
</template>

<style scoped>
.mine { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.mine span { display: block; font-size: 0.85rem; }
.spacer { flex: 1; }
.editor { margin-bottom: 1rem; }
.editor > header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.7rem; }
.grid { display: grid; gap: 0.7rem; grid-template-columns: 1fr; }
.row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.7rem; }
.check { display: flex; gap: 0.4rem; align-items: center; margin-top: 0.7rem; font-size: 0.9rem; }
.num { white-space: nowrap; }
td small { display: block; font-size: 0.76rem; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }
@media (min-width: 760px) { .grid { grid-template-columns: repeat(4, 1fr); } .span2 { grid-column: span 2; } }
</style>
