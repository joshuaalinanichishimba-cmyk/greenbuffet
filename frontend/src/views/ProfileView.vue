<!--
  A person's profile: your own at /profile, anyone else's at /team/<id>.

  The server decides which tabs a viewer may open and which actions they may
  take, and refuses the rest; this screen only shows what it is told. A
  cashier sees all of their own profile and nobody else's. A manager sees the
  team's work and attendance but not their sign-in history or pay unless
  their role allows it. The owners see everything, and neither owner can
  suspend, demote or archive the other.
-->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QRCode from 'qrcode'
import AppShell from '../components/AppShell.vue'
import Avatar from '../components/Avatar.vue'
import Icon from '../components/Icon.vue'
import { ApiError, api, type DeviceSession, type Notice, type Profile, type Role } from '../services/api'
import { kwacha } from '../services/money'
import { ago, clock } from '../services/presence'
import { session } from '../stores/session'

const route = useRoute()
const router = useRouter()

const profile = ref<Profile | null>(null)
const error = ref('')
const notice = ref('')
const busy = ref(false)

const userId = computed(() => (route.params.id as string | undefined) ?? '')
const isMe = computed(() => !userId.value || userId.value === session.user.value?.id)
const base = computed(() => (isMe.value ? '/profile' : `/team/${userId.value}`))

const TAB_LABELS: Record<string, string> = {
  overview: 'Overview', activity: 'Activity', attendance: 'Attendance & shifts', permissions: 'Roles & permissions',
  logins: 'Sign-in history', sessions: 'Devices', employment: 'Employment', payroll: 'Pay & documents',
  security: 'Security', notifications: 'Notifications', support: 'Problem reports',
}
const tabs = computed(() => {
  const list = [...(profile.value?.tabs ?? ['overview'])]
  if (isMe.value) list.push('notifications')
  if (isMe.value && session.can('tickets.report')) list.push('support')
  return list
})
const tab = computed(() => {
  const asked = (route.params.tab as string | undefined) ?? 'overview'
  return tabs.value.includes(asked) ? asked : 'overview'
})

async function load() {
  error.value = ''
  try {
    profile.value = await api.get<Profile>(isMe.value ? '/profile/me' : `/team/${userId.value}`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load this profile.'
  }
}

function fail(e: unknown, fallback: string) {
  error.value = e instanceof ApiError ? e.message : fallback
}

// ---- the overview: my own contact details and photograph ----
const editing = ref(false)
const phone = ref('')
watch(() => [profile.value?.id, route.query.edit], () => {
  phone.value = profile.value?.phone ?? ''
  editing.value = isMe.value && route.query.edit === '1'
}, { immediate: true })

async function savePhone() {
  busy.value = true
  try {
    profile.value = await api.put<Profile>('/profile/me', { phone: phone.value })
    editing.value = false
    notice.value = 'Saved.'
  } catch (e) {
    fail(e, 'Could not save.')
  } finally {
    busy.value = false
  }
}

const photoInput = ref<HTMLInputElement | null>(null)
async function choosePhoto(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  busy.value = true
  try {
    const { photo_id } = await api.uploadPhoto(file)
    if (session.user.value) session.user.value = { ...session.user.value, photo_id }
    await load()
  } catch (e) {
    fail(e, 'Could not store the photograph.')
  } finally {
    busy.value = false
    if (photoInput.value) photoInput.value.value = ''
  }
}
async function removePhoto() {
  busy.value = true
  try {
    await api.del('/profile/me/photo')
    if (session.user.value) session.user.value = { ...session.user.value, photo_id: null }
    await load()
  } catch (e) {
    fail(e, 'Could not remove the photograph.')
  } finally {
    busy.value = false
  }
}

// ---- account actions ----
const asking = ref<'' | 'suspend' | 'archive'>('')
const reason = ref('')
const tempPassword = ref('')

async function act(path: string, body?: unknown, done?: string) {
  busy.value = true
  error.value = ''
  try {
    profile.value = await api.post<Profile>(`/team/${userId.value}/${path}`, body)
    asking.value = ''
    reason.value = ''
    if (done) notice.value = done
  } catch (e) {
    fail(e, 'That did not work.')
  } finally {
    busy.value = false
  }
}
async function resetPassword() {
  if (!profile.value) return
  busy.value = true
  try {
    const r = await api.resetUserPassword(profile.value.id)
    tempPassword.value = r.temporary_password
    await load()
  } catch (e) {
    fail(e, 'Could not reset the password.')
  } finally {
    busy.value = false
  }
}

// ---- tab data, loaded when a tab opens ----
const data = ref<Record<string, any>>({})
const days = ref(30)
const roles = ref<Role[]>([])
const newRole = ref('')

async function loadTab() {
  if (!profile.value) return
  const id = profile.value.id
  const t = tab.value
  try {
    if (t === 'activity') data.value.activity = await api.get(`/team/${id}/activity?days=${days.value}`)
    if (t === 'attendance') data.value.attendance = await api.get(`/team/${id}/attendance`)
    if (t === 'permissions') {
      data.value.permissions = await api.get(`/team/${id}/permissions`)
      newRole.value = profile.value.role_id
      if (profile.value.can.change_role && !roles.value.length) roles.value = await api.roles()
    }
    if (t === 'logins') data.value.logins = await api.get(`/team/${id}/logins`)
    if (t === 'sessions' || t === 'security') data.value.sessions = await api.get(`/team/${id}/sessions`)
    if (t === 'employment') data.value.employment = await api.get(`/team/${id}/employment`)
    if (t === 'payroll') data.value.payroll = await api.get(`/team/${id}/payroll`)
    if (t === 'notifications') data.value.notices = await api.get<Notice[]>('/notifications?limit=100')
    if (t === 'support') data.value.tickets = await api.get('/tickets/mine')
  } catch (e) {
    fail(e, 'Could not load this tab.')
  }
}

watch(() => [route.fullPath], async () => {
  notice.value = ''
  if (!profile.value || profile.value.id !== (userId.value || session.user.value?.id)) await load()
  await loadTab()
}, { immediate: true })

async function changeRole() {
  if (!profile.value || newRole.value === profile.value.role_id) return
  busy.value = true
  try {
    await api.patchUser(profile.value.id, { role_id: newRole.value })
    notice.value = 'Role changed. Their devices were signed out so the new permissions apply at once.'
    await load()
    await loadTab()
  } catch (e) {
    fail(e, 'Could not change the role.')
  } finally {
    busy.value = false
  }
}

async function revoke(s?: DeviceSession, everything = false) {
  if (!profile.value) return
  busy.value = true
  try {
    const r = await api.post<{ ended: number }>(`/team/${profile.value.id}/sessions/revoke`,
      s ? { session_id: s.id } : { include_this: everything })
    notice.value = r.ended ? `${r.ended} device${r.ended === 1 ? '' : 's'} signed out.` : 'No other devices were signed in.'
    if (s?.this_device || (everything && isMe.value)) {
      session.signOut()
      router.replace('/login')
      return
    }
    await loadTab()
  } catch (e) {
    fail(e, 'Could not sign that device out.')
  } finally {
    busy.value = false
  }
}

// ---- two-step sign-in ----
const setup = ref<{ secret: string; uri: string; qr: string } | null>(null)
const code = ref('')
const recovery = ref<string[]>([])
const offForm = ref({ open: false, password: '', code: '' })
const newCodesPw = ref('')

async function startTwoStep() {
  busy.value = true
  error.value = ''
  try {
    const s = await api.post<{ secret: string; uri: string }>('/auth/two-step/start')
    setup.value = { ...s, qr: await QRCode.toDataURL(s.uri, { margin: 1, width: 220 }) }
  } catch (e) {
    fail(e, 'Could not start two-step sign-in.')
  } finally {
    busy.value = false
  }
}
async function confirmTwoStep() {
  busy.value = true
  error.value = ''
  try {
    const r = await api.post<{ recovery_codes: string[] }>('/auth/two-step/confirm', { code: code.value })
    recovery.value = r.recovery_codes
    setup.value = null
    code.value = ''
    if (session.user.value) session.user.value = { ...session.user.value, totp_enabled: true, two_step_required: false }
    await load()
  } catch (e) {
    fail(e, 'That code did not work.')
  } finally {
    busy.value = false
  }
}
async function newRecoveryCodes() {
  busy.value = true
  try {
    const r = await api.post<{ recovery_codes: string[] }>('/auth/two-step/recovery-codes', { password: newCodesPw.value })
    recovery.value = r.recovery_codes
    newCodesPw.value = ''
  } catch (e) {
    fail(e, 'Could not make new codes.')
  } finally {
    busy.value = false
  }
}
async function turnOff() {
  busy.value = true
  try {
    await api.post('/auth/two-step/off', { password: offForm.value.password, code: offForm.value.code })
    offForm.value = { open: false, password: '', code: '' }
    if (session.user.value) session.user.value = { ...session.user.value, totp_enabled: false }
    await load()
  } catch (e) {
    fail(e, 'Could not turn it off.')
  } finally {
    busy.value = false
  }
}

// ---- notices ----
async function savePrefs(kind: string, on: boolean) {
  if (!profile.value?.preferences) return
  try {
    profile.value = await api.put<Profile>('/profile/me', { notify: { [kind]: on } })
  } catch (e) {
    fail(e, 'Could not save.')
  }
}
async function readAll() {
  await api.post('/notifications/read', { all: true })
  session.unread.value = 0
  await loadTab()
}

const statusClass = (s: string) => (s === 'online' ? '' : s === 'away' || s === 'lost' ? 'warn' : 'neutral')
const money = (n: number) => kwacha(n)
const fmtDay = (d: string) => new Date(d).toLocaleDateString('en-ZM', { weekday: 'short', day: 'numeric', month: 'short' })
const fmtTime = (d: string | null) => (d ? new Date(d).toLocaleTimeString('en-ZM', { hour: '2-digit', minute: '2-digit' }) : '—')
const hours = (a: string, b: string | null) => {
  const ms = (b ? new Date(b).getTime() : Date.now()) - new Date(a).getTime()
  return `${Math.floor(ms / 3600000)} h ${Math.round((ms % 3600000) / 60000)} min`
}
const variance = (v: number | null) => (v === null ? 'Open' : v === 0 ? 'Exact' : v > 0 ? `+${kwacha(v)}` : `−${kwacha(-v)}`)
</script>

<template>
  <AppShell>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="!profile && !error" class="muted">Loading…</p>

    <template v-if="profile">
      <p v-if="!isMe" class="crumb"><RouterLink to="/team">Team</RouterLink> / {{ profile.name }}</p>

      <!-- the owner must set up two-step sign-in before anything else -->
      <section v-if="isMe && session.user.value?.two_step_required" class="card home-banner warn">
        <Icon name="shield" :size="22" />
        <div class="text">
          <b>Owner accounts must use two-step sign-in</b>
          <span>Set it up below with an authenticator app on your phone. The rest of the system opens once it is on.</span>
        </div>
      </section>

      <section class="card head">
        <div class="pic">
          <Avatar :user-id="profile.id" :name="profile.name" :photo-id="profile.photo_id" :size="88"
                  :status="profile.presence.status" :suspended="profile.account.code === 'suspended' || profile.account.code === 'archived'" />
          <template v-if="isMe">
            <input ref="photoInput" type="file" accept="image/jpeg,image/png,image/webp" class="sr" @change="choosePhoto" />
            <button class="btn btn-ghost btn-sm" :disabled="busy" @click="photoInput?.click()"><Icon name="camera" :size="16" /> {{ profile.photo_id ? 'Change' : 'Add photo' }}</button>
            <button v-if="profile.photo_id" class="link small" :disabled="busy" @click="removePhoto">Remove</button>
          </template>
        </div>
        <div class="who">
          <h1>{{ profile.name }}</h1>
          <p class="job">{{ profile.job_title }}<template v-if="profile.job_title !== profile.role_label"> · {{ profile.role_label }}</template><template v-if="profile.department"> · {{ profile.department }}</template></p>
          <div class="tags">
            <span class="pill" :class="statusClass(profile.presence.status)">{{ profile.presence.label }}</span>
            <span class="pill" :class="profile.duty.on_duty ? '' : profile.duty.on_leave ? 'warn' : 'neutral'">{{ profile.duty_label }}</span>
            <span class="pill" :class="profile.account.code === 'active' ? '' : profile.account.code === 'new' ? 'warn' : 'danger'">{{ profile.account.label }}</span>
            <span v-if="profile.two_step.enabled" class="pill"><Icon name="shield" :size="13" /> Two-step on</span>
          </div>
          <p class="muted small">
            {{ profile.presence.status === 'online' ? 'Active now' : `Last active ${ago(profile.presence.last_active).toLowerCase()}` }}
            <template v-if="profile.presence.devices"> · {{ profile.presence.devices }} device{{ profile.presence.devices === 1 ? '' : 's' }} connected</template>
          </p>
          <p v-if="profile.suspended_reason && profile.account.code !== 'active'" class="reason">Reason: {{ profile.suspended_reason }}</p>
        </div>
        <div v-if="!isMe" class="acts">
          <button v-if="profile.can.reset_password" class="btn btn-outline btn-sm" :disabled="busy" @click="resetPassword">Reset password</button>
          <button v-if="profile.can.suspend" class="btn btn-danger btn-sm" :disabled="busy" @click="asking = 'suspend'">Suspend</button>
          <button v-if="profile.can.restore" class="btn btn-primary btn-sm" :disabled="busy" @click="act('restore', undefined, 'Access restored.')">Restore access</button>
          <button v-if="profile.can.archive" class="btn btn-ghost btn-sm" :disabled="busy" @click="asking = 'archive'">Archive</button>
        </div>
      </section>

      <form v-if="asking" class="card ask" @submit.prevent="act(asking, { reason }, asking === 'suspend' ? 'Suspended. Their devices were signed out.' : 'Archived.')">
        <b>{{ asking === 'suspend' ? `Suspend ${profile.name}` : `Archive ${profile.name}` }}</b>
        <p class="muted small">
          {{ asking === 'suspend'
            ? 'They are signed out everywhere at once and cannot sign in until an owner or manager restores access.'
            : 'For someone who has left. The account is switched off and leaves the directory; everything they did stays in the records.' }}
        </p>
        <input v-model="reason" class="input" placeholder="Reason (kept with the account)" maxlength="200" required minlength="3" />
        <div class="row">
          <button class="btn btn-sm" :class="asking === 'suspend' ? 'btn-danger' : 'btn-primary'" :disabled="busy || reason.trim().length < 3">{{ asking === 'suspend' ? 'Suspend' : 'Archive' }}</button>
          <button type="button" class="btn btn-ghost btn-sm" @click="asking = ''">Cancel</button>
        </div>
      </form>

      <section v-if="tempPassword" class="card ask">
        <b>Temporary password for {{ profile.name }}</b>
        <p class="temp">{{ tempPassword }}</p>
        <p class="muted small">Shown once. Give it to them in person; they choose their own at the next sign-in. Their devices were signed out.</p>
        <button class="btn btn-ghost btn-sm" @click="tempPassword = ''">Done</button>
      </section>

      <p v-if="notice" class="ok">{{ notice }}</p>

      <nav class="ptabs" aria-label="Profile">
        <RouterLink v-for="t in tabs" :key="t" :to="`${base}/${t}`" :class="{ on: tab === t }">{{ TAB_LABELS[t] }}</RouterLink>
      </nav>

      <!-- ===== overview ===== -->
      <section v-if="tab === 'overview'" class="split">
        <div class="card">
          <div class="card-head"><h3>Details</h3>
            <button v-if="isMe && !editing" class="link" @click="editing = true">Edit contact</button>
          </div>
          <dl class="facts">
            <dt>Staff number</dt><dd>{{ profile.employee_number || 'Not on the staff list' }}</dd>
            <dt>Job title</dt><dd>{{ profile.job_title }}</dd>
            <dt>Role</dt><dd>{{ profile.role_label }}</dd>
            <dt>Department</dt><dd>{{ profile.department || '—' }}</dd>
            <dt>Email</dt><dd>{{ profile.email }}</dd>
            <dt>Phone</dt>
            <dd>
              <form v-if="editing" class="row" @submit.prevent="savePhone">
                <input v-model="phone" class="input inline" inputmode="tel" maxlength="24" placeholder="0977 000000" />
                <button class="btn btn-primary btn-sm" :disabled="busy">Save</button>
                <button type="button" class="btn btn-ghost btn-sm" @click="editing = false">Cancel</button>
              </form>
              <template v-else>{{ profile.phone || '—' }}</template>
            </dd>
            <dt>Employment</dt><dd>{{ profile.employment_status }}<template v-if="profile.start_date"> since {{ new Date(profile.start_date).toLocaleDateString('en-ZM', { day: 'numeric', month: 'short', year: 'numeric' }) }}</template></dd>
            <dt>Account</dt><dd>{{ profile.account.label }}</dd>
            <dt>Online</dt><dd>{{ profile.presence.label }} · {{ profile.presence.status === 'online' ? 'active now' : `last active ${ago(profile.presence.last_active).toLowerCase()}` }}</dd>
            <dt>Current shift</dt>
            <dd>
              <template v-if="profile.duty.on_duty">Clocked in at {{ fmtTime(profile.duty.since) }}</template>
              <template v-else-if="profile.duty.on_leave">On approved leave</template>
              <template v-else>Not clocked in</template>
              <template v-if="profile.duty.till_open"> · till open since {{ fmtTime(profile.duty.till_since) }}</template>
            </dd>
            <dt>Account made</dt><dd>{{ profile.created_at ? clock(profile.created_at) : '—' }}<template v-if="profile.created_by"> by {{ profile.created_by }}</template></dd>
          </dl>
          <p v-if="isMe" class="muted small note">You can change your photograph, phone, password and notices. Your role, pay, staff number and employment status are changed by an owner or manager.</p>
        </div>
        <div class="card">
          <div class="card-head"><h3>Responsibilities</h3></div>
          <div v-for="g in profile.responsibilities" :key="g.area" class="resp">
            <b>{{ g.area }}</b>
            <p>{{ g.items.join(' · ') }}</p>
          </div>
        </div>
      </section>

      <!-- ===== activity ===== -->
      <section v-if="tab === 'activity'">
        <div class="row between">
          <p class="muted">Work recorded in the system under {{ isMe ? 'your' : `${profile.name}'s` }} name.</p>
          <select v-model.number="days" class="input inline" @change="loadTab">
            <option :value="7">Last 7 days</option><option :value="30">Last 30 days</option><option :value="90">Last 90 days</option>
          </select>
        </div>
        <template v-if="data.activity">
          <p v-if="!data.activity.groups.length" class="home-empty">Nothing recorded in this period.</p>
          <div class="groups">
            <div v-for="g in data.activity.groups" :key="g.title" class="card">
              <div class="card-head"><h3>{{ g.title }}</h3></div>
              <ul class="home-list">
                <li v-for="r in g.rows" :key="r.label"><span>{{ r.label }}</span><b class="num">{{ r.money !== undefined ? money(r.money) : r.count }}</b></li>
              </ul>
            </div>
          </div>
          <div v-if="data.activity.tills.length" class="card">
            <div class="card-head"><h3>Till counts</h3></div>
            <ul class="home-list">
              <li v-for="(t, i) in data.activity.tills" :key="i">
                <div><span>{{ clock(t.closed_at) }}</span><p v-if="t.note" class="sub">{{ t.note }}</p></div>
                <span><b class="num" :class="t.variance_ngwee < 0 ? 'bad' : ''">{{ variance(t.variance_ngwee) }}</b>
                  <span v-if="t.variance_ngwee !== 0" class="muted small"> · {{ t.reviewed ? 'reviewed' : 'not reviewed' }}</span></span>
              </li>
            </ul>
          </div>
          <div class="card">
            <div class="card-head"><h3>Recent actions</h3></div>
            <p v-if="!data.activity.recent.length" class="home-empty">No actions recorded.</p>
            <ul class="home-list">
              <li v-for="(a, i) in data.activity.recent" :key="i">
                <div><b>{{ a.action }}</b> <span class="muted">{{ a.detail }}</span></div>
                <span class="muted small nowrap">{{ clock(a.at) }}</span>
              </li>
            </ul>
            <p class="muted small note">{{ data.activity.note }}</p>
          </div>
        </template>
      </section>

      <!-- ===== attendance ===== -->
      <section v-if="tab === 'attendance' && data.attendance">
        <p class="info-note">{{ data.attendance.note }}</p>
        <p v-if="!data.attendance.on_staff_list" class="home-empty">Not on the staff list, so there is no clocking.
          <RouterLink v-if="session.can('hr.manage')" to="/people">Add them on the staff list</RouterLink></p>
        <div class="kpis">
          <div class="kpi"><span class="kpi-label">Hours, last 30 days</span><span class="kpi-value">{{ data.attendance.hours_30_days }}</span></div>
          <div class="kpi"><span class="kpi-label">Days worked</span><span class="kpi-value">{{ data.attendance.days_30 }}</span></div>
          <div class="kpi"><span class="kpi-label">Now</span><span class="kpi-value small-value">{{ data.attendance.duty.on_duty ? 'On duty' : data.attendance.duty.on_leave ? 'On leave' : 'Off duty' }}</span></div>
        </div>
        <div class="split">
          <div class="card">
            <div class="card-head"><h3>Clocking</h3></div>
            <p v-if="!data.attendance.clocking.length" class="home-empty">No clocking in the last 30 days.</p>
            <div class="table-wrap">
              <table v-if="data.attendance.clocking.length" class="table">
                <thead><tr><th>Day</th><th>In</th><th>Out</th><th>Hours</th></tr></thead>
                <tbody><tr v-for="(c, i) in data.attendance.clocking" :key="i">
                  <td>{{ fmtDay(c.day) }}</td><td>{{ fmtTime(c.in) }}</td><td>{{ c.out ? fmtTime(c.out) : 'Still in' }}</td><td>{{ hours(c.in, c.out) }}</td>
                </tr></tbody>
              </table>
            </div>
          </div>
          <div class="col">
            <div class="card">
              <div class="card-head"><h3>Tills</h3></div>
              <p v-if="!data.attendance.tills.length" class="home-empty">No tills opened.</p>
              <ul class="home-list">
                <li v-for="(t, i) in data.attendance.tills" :key="i"><span>{{ clock(t.opened_at) }}</span><b class="num">{{ variance(t.variance_ngwee) }}</b></li>
              </ul>
            </div>
            <div class="card">
              <div class="card-head"><h3>Leave</h3></div>
              <p v-if="!data.attendance.leave.length" class="home-empty">No leave requested.</p>
              <ul class="home-list">
                <li v-for="(l, i) in data.attendance.leave" :key="i">
                  <span>{{ fmtDay(l.start) }} – {{ fmtDay(l.end) }} · {{ l.days }} day{{ l.days === 1 ? '' : 's' }}</span>
                  <span class="pill" :class="l.status === 'approved' ? '' : l.status === 'pending' ? 'warn' : 'neutral'">{{ l.status }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <!-- ===== roles and permissions ===== -->
      <section v-if="tab === 'permissions' && data.permissions" class="stack">
        <div class="card">
          <div class="card-head"><h3>{{ data.permissions.role_label }}</h3></div>
          <p class="muted">{{ data.permissions.description }}</p>
          <form v-if="profile.can.change_role" class="row role-form" @submit.prevent="changeRole">
            <label class="label" for="role">Change role</label>
            <select id="role" v-model="newRole" class="input inline">
              <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.label }}</option>
            </select>
            <button class="btn btn-primary btn-sm" :disabled="busy || newRole === profile.role_id">Change</button>
            <RouterLink v-if="session.can('roles.manage')" to="/roles" class="link">Edit what each role may do</RouterLink>
          </form>
        </div>
        <div class="groups">
          <div v-for="g in data.permissions.groups" :key="g.area" class="card">
            <div class="card-head"><h3>{{ g.area }}</h3></div>
            <ul class="ticks"><li v-for="p in g.items" :key="p">{{ p }}</li></ul>
          </div>
        </div>
      </section>

      <!-- ===== sign-in history ===== -->
      <section v-if="tab === 'logins' && data.logins" class="card">
        <div class="card-head"><h3>Sign-in history</h3></div>
        <p v-if="!data.logins.length" class="home-empty">No sign-ins recorded.</p>
        <div class="table-wrap">
          <table v-if="data.logins.length" class="table">
            <thead><tr><th>When</th><th>Result</th><th>Device</th><th>Network address</th></tr></thead>
            <tbody><tr v-for="(l, i) in data.logins" :key="i">
              <td>{{ clock(l.at) }}</td>
              <td><span class="pill" :class="l.ok ? '' : 'danger'">{{ l.ok ? 'Signed in' : 'Failed' }}</span></td>
              <td>{{ l.device || '—' }}</td><td>{{ l.ip || '—' }}</td>
            </tr></tbody>
          </table>
        </div>
      </section>

      <!-- ===== devices ===== -->
      <section v-if="tab === 'sessions' && data.sessions" class="stack">
        <div class="card">
          <div class="card-head">
            <h3>Signed in now</h3>
            <button v-if="profile.can.revoke_sessions && data.sessions.open.length" class="btn btn-outline btn-sm" :disabled="busy"
                    @click="revoke(undefined, !isMe)">{{ isMe ? 'Sign out all other devices' : 'Sign out of every device' }}</button>
          </div>
          <p v-if="!data.sessions.open.length" class="home-empty">Not signed in anywhere.</p>
          <ul class="home-list">
            <li v-for="s in data.sessions.open" :key="s.id" class="with-icon">
              <Icon :name="s.device === 'Phone' ? 'phone' : 'device'" />
              <div>
                <b>{{ s.device }} · {{ s.browser }}</b> <span v-if="s.this_device" class="pill">This device</span>
                <p class="sub">Signed in {{ clock(s.started_at) }} · last seen {{ ago(s.last_seen_at).toLowerCase() }} · {{ s.ip || 'address unknown' }}</p>
              </div>
              <span class="right-col">
                <span class="pill" :class="statusClass(s.state)">{{ s.state_label }}</span>
                <button v-if="profile.can.revoke_sessions" class="link small" :disabled="busy" @click="revoke(s)">Sign out</button>
              </span>
            </li>
          </ul>
        </div>
        <div class="card">
          <div class="card-head"><h3>Recently ended</h3></div>
          <p v-if="!data.sessions.ended.length" class="home-empty">None.</p>
          <ul class="home-list">
            <li v-for="s in data.sessions.ended" :key="s.id">
              <div><b>{{ s.device }} · {{ s.browser }}</b><p class="sub">{{ clock(s.started_at) }} to {{ clock(s.ended_at) }}</p></div>
              <span class="muted small">{{ s.reason }}</span>
            </li>
          </ul>
        </div>
      </section>

      <!-- ===== employment ===== -->
      <section v-if="tab === 'employment' && data.employment" class="card">
        <div class="card-head"><h3>Employment</h3>
          <RouterLink v-if="profile.can.edit_employment" to="/people" class="link">Edit on the staff list</RouterLink></div>
        <p v-if="!data.employment.on_staff_list" class="home-empty">Not on the staff list.</p>
        <dl v-else class="facts">
          <dt>Staff number</dt><dd>{{ data.employment.number }}</dd>
          <dt>Job title</dt><dd>{{ data.employment.job_title || '—' }}</dd>
          <dt>Department</dt><dd>{{ data.employment.department || '—' }}</dd>
          <dt>Started</dt><dd>{{ data.employment.start_date ? fmtDay(data.employment.start_date) : '—' }}</dd>
          <dt>Status</dt><dd>{{ data.employment.status }}</dd>
          <dt>Leave this year</dt><dd>{{ data.employment.leave_taken }} of {{ data.employment.leave_days_per_year }} days taken · {{ data.employment.leave_left }} left</dd>
        </dl>
      </section>

      <!-- ===== pay and documents ===== -->
      <section v-if="tab === 'payroll' && data.payroll" class="split">
        <div class="card">
          <div class="card-head"><h3>Pay</h3></div>
          <p v-if="!data.payroll.on_staff_list" class="home-empty">Not on the staff list.</p>
          <dl v-else class="facts">
            <dt>Basic pay</dt><dd>{{ money(data.payroll.basic_ngwee) }} a month</dd>
            <dt>Allowances</dt><dd>{{ money(data.payroll.allowances_ngwee) }}</dd>
            <dt>Paid by</dt><dd>{{ data.payroll.pay_method }} {{ data.payroll.pay_account }}</dd>
            <dt>NAPSA</dt><dd>{{ data.payroll.napsa_number || '—' }}</dd>
            <dt>TPIN</dt><dd>{{ data.payroll.tpin || '—' }}</dd>
          </dl>
        </div>
        <div class="col">
          <div class="card">
            <div class="card-head"><h3>Payslips</h3></div>
            <p v-if="!data.payroll.payslips?.length" class="home-empty">No payslips yet.</p>
            <ul class="home-list">
              <li v-for="p in data.payroll.payslips" :key="p.period"><span>{{ p.period }} · {{ p.status }}</span><b class="num">{{ money(p.net_ngwee) }}</b></li>
            </ul>
          </div>
          <div class="card">
            <div class="card-head"><h3>Documents</h3></div>
            <p v-if="!data.payroll.documents?.length" class="home-empty">No documents filed.</p>
            <ul class="home-list">
              <li v-for="d in data.payroll.documents" :key="d.id"><span>{{ d.name }}</span><span class="muted small">{{ d.kind }}</span></li>
            </ul>
          </div>
        </div>
      </section>

      <!-- ===== security ===== -->
      <section v-if="tab === 'security'" class="stack">
        <div class="card">
          <div class="card-head"><h3>Two-step sign-in</h3>
            <span class="pill" :class="profile.two_step.enabled ? '' : profile.two_step.required ? 'danger' : 'neutral'">
              {{ profile.two_step.enabled ? 'On' : profile.two_step.required ? 'Required, not set up' : 'Off' }}</span></div>
          <p class="muted">A six-digit code from an authenticator app on {{ isMe ? 'your' : 'their' }} phone, as well as the password.
            Google Authenticator, Microsoft Authenticator and Authy all work.{{ profile.two_step.required ? ' Required for owner accounts.' : '' }}</p>

          <template v-if="isMe">
            <div v-if="recovery.length" class="recovery">
              <b>Recovery codes: write these down now</b>
              <p class="muted small">Each one signs you in once if you lose your phone. They are not shown again.</p>
              <ul><li v-for="c in recovery" :key="c"><code>{{ c }}</code></li></ul>
              <button class="btn btn-primary btn-sm" @click="recovery = []">I have written them down</button>
            </div>
            <template v-else-if="!profile.two_step.enabled">
              <button v-if="!setup" class="btn btn-primary" :disabled="busy" @click="startTwoStep">Set up two-step sign-in</button>
              <div v-else class="setup">
                <img :src="setup.qr" alt="QR code for the authenticator app" width="220" height="220" />
                <ol>
                  <li>Open the authenticator app and add an account by scanning this code.</li>
                  <li>No camera? Type this key instead: <code class="key">{{ setup.secret }}</code></li>
                  <li>Type the six-digit code the app shows:</li>
                </ol>
                <form class="row" @submit.prevent="confirmTwoStep">
                  <input v-model="code" class="input inline code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="123456" />
                  <button class="btn btn-primary btn-sm" :disabled="busy || code.length !== 6">Turn on</button>
                </form>
              </div>
            </template>
            <div v-else class="row wrap">
              <form class="row" @submit.prevent="newRecoveryCodes">
                <input v-model="newCodesPw" class="input inline" type="password" placeholder="Your password" autocomplete="current-password" />
                <button class="btn btn-outline btn-sm" :disabled="busy || !newCodesPw">New recovery codes</button>
              </form>
              <button v-if="!profile.two_step.required" class="btn btn-ghost btn-sm" @click="offForm.open = !offForm.open">Turn off</button>
            </div>
            <form v-if="offForm.open" class="row wrap" @submit.prevent="turnOff">
              <input v-model="offForm.password" class="input inline" type="password" placeholder="Your password" />
              <input v-model="offForm.code" class="input inline code" inputmode="numeric" maxlength="6" placeholder="Code" />
              <button class="btn btn-danger btn-sm" :disabled="busy">Turn off two-step</button>
            </form>
          </template>
          <button v-else-if="profile.can.reset_two_step" class="btn btn-outline btn-sm" :disabled="busy"
                  @click="act('two-step/reset', undefined, 'Two-step sign-in reset. They set it up again at their next sign-in.')">Reset for a lost phone</button>
          <p v-else-if="!isMe && profile.role_id === 'owner'" class="muted small">For a lost owner phone, run scripts\reset-owner.ps1 on the server computer.</p>
        </div>

        <div class="card">
          <div class="card-head"><h3>Password</h3></div>
          <p class="muted">Changing the password signs out every other device.</p>
          <RouterLink v-if="isMe" to="/change-password" class="btn btn-outline btn-sm">Change password</RouterLink>
          <button v-else-if="profile.can.reset_password" class="btn btn-outline btn-sm" :disabled="busy" @click="resetPassword">Give a temporary password</button>
        </div>

        <div v-if="data.sessions" class="card">
          <div class="card-head"><h3>Devices</h3><RouterLink :to="`${base}/sessions`">All devices</RouterLink></div>
          <p class="muted">{{ data.sessions.open.length }} signed in now.</p>
          <button v-if="profile.can.revoke_sessions && data.sessions.open.length > (isMe ? 1 : 0)" class="btn btn-outline btn-sm" :disabled="busy"
                  @click="revoke(undefined, !isMe)">{{ isMe ? 'Sign out all other devices' : 'Sign out of every device' }}</button>
          <p class="muted small note"><RouterLink :to="`${base}/logins`">Sign-in history</RouterLink><template v-if="isMe"> · <RouterLink to="/profile/notifications">Security notices</RouterLink></template></p>
        </div>
      </section>

      <!-- ===== my problem reports ===== -->
      <section v-if="tab === 'support' && isMe && data.tickets" class="card">
        <div class="card-head"><h3>Problem reports</h3><span class="muted small">Send a new one from the menu under your picture</span></div>
        <p v-if="!data.tickets.length" class="home-empty">You have not reported a problem.</p>
        <ul class="home-list">
          <li v-for="t in data.tickets" :key="t.id">
            <div>
              <b>{{ t.number }}</b> <span class="muted">· {{ clock(t.created_at) }}</span>
              <p class="sub">{{ t.description }}</p>
              <p v-for="(n, k) in t.notes" :key="k" class="sub reply"><b>{{ n.by }}:</b> {{ n.note }}</p>
              <p v-if="t.resolution" class="sub reply"><b>Done:</b> {{ t.resolution }}</p>
            </div>
            <span class="pill" :class="t.status === 'resolved' || t.status === 'closed' ? '' : 'warn'">{{ t.status }}</span>
          </li>
        </ul>
      </section>

      <!-- ===== notifications (my own) ===== -->
      <section v-if="tab === 'notifications' && isMe" class="split">
        <div class="card">
          <div class="card-head"><h3>Notices</h3><button v-if="data.notices?.some((n: Notice) => !n.read)" class="link" @click="readAll">Mark all read</button></div>
          <p v-if="!data.notices?.length" class="home-empty">No notices.</p>
          <ul class="home-list">
            <li v-for="n in data.notices" :key="n.id" :class="{ unread: !n.read }">
              <div>
                <b>{{ n.title }}</b>
                <p v-if="n.body" class="sub">{{ n.body }}</p>
              </div>
              <span class="right-col">
                <span class="muted small nowrap">{{ clock(n.at) }}</span>
                <RouterLink v-if="n.link" :to="n.link" class="small">Open</RouterLink>
              </span>
            </li>
          </ul>
        </div>
        <div class="card">
          <div class="card-head"><h3>What to tell me</h3></div>
          <p class="muted small">Notices about your own account's security (a new device, a password change) always come. Going online and offline is never a notice; see the Team page for that.</p>
          <ul v-if="profile.preferences" class="prefs">
            <li v-for="(label, kind) in profile.preferences.labels" :key="kind">
              <label class="switch-row">
                <input type="checkbox" :checked="profile.preferences.notify[kind]" @change="savePrefs(kind as string, ($event.target as HTMLInputElement).checked)" />
                <span>{{ label }}</span>
              </label>
            </li>
          </ul>
        </div>
      </section>
    </template>
  </AppShell>
</template>

<style scoped>
.crumb { color: var(--muted); margin-bottom: .75rem; font-size: .9rem; }
.crumb a { color: var(--green-deep); font-weight: 700; text-decoration: none; }
.head { display: flex; gap: 1.25rem; align-items: flex-start; flex-wrap: wrap; }
.pic { display: grid; justify-items: center; gap: .35rem; }
.who { flex: 1 1 260px; display: grid; gap: .35rem; min-width: 0; }
.who h1 { font-size: 1.6rem; }
.job { color: var(--muted); font-weight: 600; }
.tags { display: flex; gap: .35rem; flex-wrap: wrap; }
.reason { color: var(--danger); font-weight: 600; font-size: .9rem; }
.acts { display: flex; gap: .5rem; flex-wrap: wrap; align-items: flex-start; }
.ask { display: grid; gap: .6rem; margin-top: .85rem; max-width: 640px; }
.temp { font-family: ui-monospace, monospace; font-size: 1.5rem; font-weight: 800; letter-spacing: .08em; color: var(--brown); }
.ok { margin: .85rem 0 0; color: var(--green-deep); font-weight: 700; }
.ptabs { display: flex; gap: .25rem; margin: 1.25rem 0 1rem; border-bottom: 1px solid var(--line); overflow-x: auto; scrollbar-width: thin; }
.ptabs a {
  padding: .6rem .9rem; text-decoration: none; color: var(--muted); font-weight: 700; white-space: nowrap;
  border-bottom: 3px solid transparent; margin-bottom: -1px;
}
.ptabs a.on { color: var(--green-deep); border-bottom-color: var(--green); }
.facts { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: .55rem 1.25rem; margin: 0; }
.facts dt { color: var(--muted); font-weight: 600; }
.facts dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.note { margin-top: 1rem; }
.resp + .resp { margin-top: .8rem; }
.resp b { font-size: .88rem; color: var(--brown); }
.resp p { color: var(--muted); font-size: .9rem; }
.input.inline { width: auto; min-height: 40px; padding: .4rem .7rem; }
.input.code { width: 8.5rem; letter-spacing: .25em; font-weight: 800; }
.row.between { justify-content: space-between; margin-bottom: 1rem; }
.row.wrap { flex-wrap: wrap; }
.groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); gap: .85rem; margin-bottom: .85rem; }
.ticks { margin: 0; padding-left: 1.1rem; display: grid; gap: .3rem; }
.role-form { margin-top: .85rem; }
.link { border: 0; background: none; color: var(--green-deep); font-weight: 700; cursor: pointer; padding: 0; text-decoration: none; }
.right-col { display: grid; justify-items: end; gap: .25rem; }
.nowrap { white-space: nowrap; }
.setup { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 1.25rem; align-items: start; margin-top: .5rem; }
.setup img { border-radius: 10px; background: #fff; padding: 6px; }
.setup ol { margin: 0; padding-left: 1.2rem; display: grid; gap: .45rem; }
.setup form { grid-column: 2; }
.key { word-break: break-all; font-weight: 700; }
.recovery { background: var(--warn-soft); border-radius: 12px; padding: 1rem; display: grid; gap: .5rem; }
.recovery ul { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: .35rem; list-style: none; padding: 0; margin: 0; }
.recovery code { font-size: 1.05rem; font-weight: 800; }
.prefs { list-style: none; padding: 0; margin: .75rem 0 0; display: grid; gap: .6rem; }
.switch-row { display: flex; gap: .6rem; align-items: center; font-weight: 600; }
.switch-row input { width: 20px; height: 20px; accent-color: var(--green); }
li.unread b { color: var(--green-deep); }
.small-value { font-size: 1.3rem; }
.reply { border-left: 3px solid var(--leaf); padding-left: .6rem; margin-top: .35rem; }
.table-wrap { overflow-x: auto; }
@media (max-width: 640px) {
  .setup { grid-template-columns: 1fr; }
  .setup form { grid-column: 1; }
  .facts { grid-template-columns: 1fr; gap: .15rem; }
  .facts dd { margin-bottom: .55rem; }
  .who h1 { font-size: 1.35rem; }
}
</style>
