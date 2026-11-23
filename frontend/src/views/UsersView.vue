<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type Role, type User } from '../services/api'
import { session } from '../stores/session'

const users = ref<User[]>([])
const roles = ref<Role[]>([])
const loading = ref(true)
const error = ref('')
const busyId = ref('')

/** Shown once after a password is issued; never retrievable afterwards. */
const issued = ref<{ name: string; email: string; password: string } | null>(null)

const form = reactive({ name: '', email: '', role_id: '', saving: false })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [u, r] = await Promise.all([api.users(), api.roles()])
    users.value = u
    roles.value = r
    if (!form.role_id) form.role_id = r.find((x) => x.id === 'cashier')?.id ?? r[0]?.id ?? ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load staff accounts.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function addUser() {
  error.value = ''
  if (form.name.trim().length < 3) {
    error.value = 'Enter the full name.'
    return
  }
  form.saving = true
  try {
    const created = await api.createUser(form.name.trim(), form.email.trim(), form.role_id)
    issued.value = {
      name: created.name,
      email: created.email,
      password: created.temporary_password ?? '',
    }
    form.name = ''
    form.email = ''
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not create the account.'
  } finally {
    form.saving = false
  }
}

async function changeRole(user: User, role_id: string) {
  if (role_id === user.role_id) return
  await patch(user, { role_id })
}

async function toggleActive(user: User) {
  await patch(user, { is_active: !user.is_active })
}

async function patch(user: User, changes: Partial<Pick<User, 'name' | 'email' | 'role_id' | 'is_active'>>) {
  error.value = ''
  busyId.value = user.id
  try {
    const updated = await api.patchUser(user.id, changes)
    users.value = users.value.map((u) => (u.id === updated.id ? updated : u))
    if (updated.id === session.user.value?.id) session.update(updated)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save that change.'
    await load()
  } finally {
    busyId.value = ''
  }
}

async function resetPassword(user: User) {
  error.value = ''
  busyId.value = user.id
  try {
    const result = await api.resetUserPassword(user.id)
    issued.value = { name: result.user.name, email: result.user.email, password: result.temporary_password }
    users.value = users.value.map((u) => (u.id === result.user.id ? result.user : u))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not reset that password.'
  } finally {
    busyId.value = ''
  }
}

async function copyPassword() {
  if (!issued.value) return
  try {
    await navigator.clipboard.writeText(issued.value.password)
  } catch {
    /* clipboard blocked: the password is on screen to read anyway */
  }
}

function rename(user: User) {
  const next = window.prompt('Full name', user.name)
  if (next && next.trim() !== user.name) patch(user, { name: next.trim() })
}

function changeEmail(user: User) {
  const next = window.prompt('Email used to sign in', user.email)
  if (next && next.trim().toLowerCase() !== user.email) patch(user, { email: next.trim().toLowerCase() })
}
</script>

<template>
  <AppShell>
    <h1>Staff accounts</h1>
    <p class="lead">
      Everyone who signs in needs their own account, so the till, the kitchen and the books all
      record who did what. New accounts get a temporary password and must choose their own on first
      sign-in.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="issued" class="issued">
      <b>Temporary password for {{ issued.name }}</b>
      <code>{{ issued.password }}</code>
      <p class="muted">
        Hand this to them now, with the email {{ issued.email }}. It cannot be shown again, but you
        can reset it as often as you need.
      </p>
      <div class="issued-actions">
        <button class="btn-quiet btn-small" @click="copyPassword">Copy password</button>
        <button class="btn-quiet btn-small" @click="issued = null">Done</button>
      </div>
    </div>

    <section class="panel add">
      <b>Add someone</b>
      <div class="add-grid">
        <label class="field">
          Full name
          <input v-model="form.name" type="text" placeholder="Mary Banda" autocomplete="off" />
        </label>
        <label class="field">
          Email
          <input v-model="form.email" type="email" placeholder="mary@greenbuffet.zm" autocomplete="off" />
        </label>
        <label class="field">
          Role
          <select v-model="form.role_id">
            <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.label }}</option>
          </select>
        </label>
        <button class="btn-primary" :disabled="form.saving" @click="addUser">
          {{ form.saving ? 'Creating…' : 'Create account' }}
        </button>
      </div>
    </section>

    <h2>{{ users.length }} account{{ users.length === 1 ? '' : 's' }}</h2>
    <p v-if="loading" class="muted">Loading…</p>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <b>{{ u.name }}</b>
              <span v-if="u.id === session.user.value?.id" class="tag">you</span>
            </td>
            <td>{{ u.email }}</td>
            <td>
              <select
                :value="u.role_id"
                :disabled="busyId === u.id"
                @change="changeRole(u, ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.label }}</option>
              </select>
            </td>
            <td>
              <span class="tag" :class="{ off: !u.is_active }">{{ u.is_active ? 'Active' : 'Disabled' }}</span>
              <span v-if="u.must_change_password" class="muted pending">Temporary password</span>
            </td>
            <td class="actions">
              <button class="btn-quiet btn-small" :disabled="busyId === u.id" @click="rename(u)">Rename</button>
              <button class="btn-quiet btn-small" :disabled="busyId === u.id" @click="changeEmail(u)">Email</button>
              <button class="btn-quiet btn-small" :disabled="busyId === u.id" @click="resetPassword(u)">
                Reset password
              </button>
              <button
                v-if="u.id !== session.user.value?.id"
                class="btn-quiet btn-small"
                :disabled="busyId === u.id"
                @click="toggleActive(u)"
              >
                {{ u.is_active ? 'Disable' : 'Enable' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppShell>
</template>

<style scoped>
.add { margin-bottom: 0.6rem; }
.add > b { display: block; margin-bottom: 0.7rem; }
.add-grid { display: grid; gap: 0.7rem; grid-template-columns: 1fr; align-items: end; }
.issued {
  background: #11491f;
  color: #eaf7e4;
  border-radius: 16px;
  padding: 1rem 1.1rem;
  margin-bottom: 1rem;
}
.issued > b { display: block; }
.issued code {
  display: inline-block;
  font-size: 1.5rem;
  letter-spacing: 0.08em;
  background: rgba(255, 255, 255, 0.12);
  padding: 0.3rem 0.7rem;
  border-radius: 10px;
  margin: 0.45rem 0;
}
.issued .muted { color: #c8dec2; margin: 0 0 0.7rem; }
.issued-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }
td .tag + .tag, td b + .tag { margin-left: 0.4rem; }
.pending { display: block; margin-top: 0.2rem; }
tbody td:first-child { white-space: nowrap; }
tbody td { padding-top: 0.75rem; padding-bottom: 0.75rem; }

@media (min-width: 760px) {
  .add-grid { grid-template-columns: 1.2fr 1.4fr 0.9fr auto; }
}
</style>
