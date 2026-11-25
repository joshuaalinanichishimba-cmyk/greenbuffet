<!--
  The team directory: everyone with an account, who is connected, who is on
  duty, and whose account needs attention.

  Online status and being on duty are shown side by side and never mixed: a
  cashier can be on duty with the network down, or signed in on a day off.
  On duty comes from clocking in only.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import Avatar from '../components/Avatar.vue'
import Icon from '../components/Icon.vue'
import { ApiError, api, type TeamCard } from '../services/api'
import { ago } from '../services/presence'
import { session } from '../stores/session'

const people = ref<TeamCard[]>([])
const loading = ref(true)
const error = ref('')
const query = ref('')
const filter = ref('all')
const showArchived = ref(false)
let timer: number | undefined

const FILTERS: { id: string; label: string; test: (p: TeamCard) => boolean }[] = [
  { id: 'all', label: 'Everyone', test: () => true },
  { id: 'online', label: 'Online', test: (p) => p.presence.status === 'online' },
  { id: 'away', label: 'Away', test: (p) => p.presence.status === 'away' || p.presence.status === 'lost' },
  { id: 'offline', label: 'Offline', test: (p) => p.presence.status === 'offline' || p.presence.status === 'unknown' },
  { id: 'duty', label: 'On duty', test: (p) => p.duty.on_duty },
  { id: 'offduty', label: 'Off duty', test: (p) => !p.duty.on_duty },
  { id: 'owner', label: 'Owners', test: (p) => p.role_id === 'owner' },
  { id: 'manager', label: 'Managers', test: (p) => p.role_id === 'manager' },
  { id: 'cashier', label: 'Cashiers', test: (p) => p.role_id === 'cashier' },
  { id: 'kitchen', label: 'Kitchen', test: (p) => p.role_id === 'kitchen' },
  { id: 'accountant', label: 'Accountants', test: (p) => p.role_id === 'accountant' },
  { id: 'suspended', label: 'Suspended', test: (p) => p.account.code === 'suspended' || p.account.code === 'archived' },
]

async function load() {
  try {
    people.value = await api.get<TeamCard[]>(`/team${showArchived.value ? '?archived=true' : ''}`)
    error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the team.'
  } finally {
    loading.value = false
  }
}

const counts = computed(() => Object.fromEntries(FILTERS.map((f) => [f.id, people.value.filter(f.test).length])))

const shown = computed(() => {
  const f = FILTERS.find((x) => x.id === filter.value) ?? FILTERS[0]
  const q = query.value.trim().toLowerCase()
  const order = { online: 0, away: 1, lost: 2, unknown: 3, offline: 4 }
  return people.value
    .filter(f.test)
    .filter((p) => !q || [p.name, p.job_title, p.department, p.role_label, p.employee_number].join(' ').toLowerCase().includes(q))
    .sort((a, b) => order[a.presence.status] - order[b.presence.status] || a.name.localeCompare(b.name))
})

function lastSeen(p: TeamCard) {
  if (p.presence.status === 'online') return 'Active now'
  return `Last active ${ago(p.presence.last_active).toLowerCase()}`
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 30000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <div class="home-head">
      <div>
        <h1>Team</h1>
        <p class="lead">Who is connected, who is on duty, and whose account needs attention.</p>
      </div>
      <div class="actions">
        <RouterLink v-if="session.canAny('staff.manage', 'roles.manage')" to="/users" class="btn-outline"><Icon name="shield" :size="18" /> Accounts &amp; roles</RouterLink>
      </div>
    </div>

    <div class="tools">
      <label class="search">
        <Icon name="search" :size="18" />
        <input v-model="query" type="search" placeholder="Search by name, job, department or staff number" aria-label="Search the team" />
      </label>
      <label class="arch"><input v-model="showArchived" type="checkbox" @change="load" /> Show archived</label>
    </div>

    <div class="filters" role="tablist" aria-label="Filter the team">
      <button v-for="f in FILTERS" :key="f.id" role="tab" class="chip" :aria-pressed="filter === f.id" @click="filter = f.id">
        {{ f.label }} <span class="n">{{ counts[f.id] }}</span>
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">Loading the team…</p>
    <p v-else-if="!shown.length" class="home-empty">Nobody matches.</p>

    <div class="grid">
      <RouterLink v-for="p in shown" :key="p.id" :to="`/team/${p.id}`" class="person card" :class="{ dim: p.account.code === 'suspended' || p.account.code === 'archived' }">
        <Avatar :user-id="p.id" :name="p.name" :photo-id="p.photo_id" :size="52"
                :status="p.presence.status" :suspended="p.account.code === 'suspended' || p.account.code === 'archived'" />
        <div class="text">
          <b>{{ p.name }}</b>
          <span class="job">{{ p.job_title }}<template v-if="p.department"> · {{ p.department }}</template></span>
          <div class="tags">
            <span class="pill" :class="{ warn: p.presence.status === 'away' || p.presence.status === 'lost', neutral: p.presence.status === 'offline' || p.presence.status === 'unknown' }">
              {{ p.presence.label }}
            </span>
            <span class="pill" :class="p.duty.on_duty ? '' : p.duty.on_leave ? 'warn' : 'neutral'">{{ p.duty_label }}</span>
            <span v-if="p.account.code !== 'active'" class="pill" :class="p.account.code === 'new' ? 'warn' : 'danger'">{{ p.account.label }}</span>
          </div>
          <span class="seen">{{ lastSeen(p) }}<template v-if="p.duty.till_open"> · till open</template></span>
        </div>
      </RouterLink>
    </div>
  </AppShell>
</template>

<style scoped>
.tools { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; margin: 1rem 0 .75rem; }
.search {
  display: flex; align-items: center; gap: .55rem; flex: 1 1 320px; min-width: 0; max-width: 520px;
  padding: .55rem .85rem; border-radius: 12px; border: 1.5px solid var(--line); background: var(--paper); color: var(--muted);
}
.search input { border: 0; background: transparent; padding: 0; width: 100%; color: var(--ink); min-height: 0; }
.search input:focus { outline: none; }
.arch { display: inline-flex; gap: .4rem; align-items: center; font-weight: 600; color: var(--muted); }
.filters { display: flex; gap: .45rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
.filters .chip { min-height: 38px; padding: .3rem .8rem; }
.n { font-size: .78rem; color: var(--muted); font-weight: 700; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); gap: .85rem; }
.person { display: flex; gap: .9rem; align-items: flex-start; padding: 1rem; text-decoration: none; color: inherit; border: 1px solid var(--line); }
.person:hover { border-color: var(--green); }
.person.dim { opacity: .75; }
.text { display: grid; gap: .25rem; min-width: 0; }
.text b { font-family: var(--display); color: var(--brown); font-size: 1.02rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job { color: var(--muted); font-size: .9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tags { display: flex; gap: .35rem; flex-wrap: wrap; margin-top: .15rem; }
.seen { color: var(--muted); font-size: .8rem; }
</style>
