<!--
  The administrator's home: accounts, sign-ins, backups, and what changed.

  An administrator looks after the system rather than the service. So this
  screen asks whether everyone who should be able to sign in can, whether
  anyone is trying to guess a password, whether last night's backup exists,
  and what was changed recently. The business Overview is one tap away.
-->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import Icon from '../components/Icon.vue'
import { api } from '../services/api'
import { firstName, greeting, problemText } from '../services/home'
import { session } from '../stores/session'

interface SystemHome {
  users_active: number
  users_disabled: number
  must_change: number
  never_signed_in: number
  by_role: { role: string; count: number }[]
  sign_ins_24h: number
  failed_24h: number
  locked: string[]
  backup: { name: string; size_kb: number; at: string; age_hours: number; count: number } | null
  environment: string
  activity: { at: string; who: string; area: string; action: string; detail: string }[]
}

const data = ref<SystemHome | null>(null)
const health = ref<{ status: string; database: string } | null>(null)
const error = ref('')
let timer: number | undefined

async function load() {
  try {
    data.value = await api.get<SystemHome>('/home/system')
    error.value = ''
  } catch (problem) {
    error.value = problemText(problem, 'Could not load the system summary.')
  }
  try {
    health.value = await api.get('/health')
  } catch {
    health.value = { status: 'degraded', database: 'unreachable' }
  }
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 60000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <div class="home-head">
      <div>
        <h1>{{ greeting() }}, {{ firstName(session.user.value?.name) }}</h1>
        <p class="lead">The system: accounts, sign-ins, backups and recent changes.</p>
      </div>
      <div class="actions">
        <RouterLink to="/overview" class="btn-outline"><Icon name="home" :size="18" /> Business overview</RouterLink>
        <RouterLink to="/users" class="btn-primary"><Icon name="users" :size="18" /> Staff accounts</RouterLink>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="data">
      <section v-if="data.locked.length" class="card home-banner warn">
        <Icon name="alert" :size="22" />
        <div class="text">
          <b>Locked out for 15 minutes: {{ data.locked.join(', ') }}</b>
          <span>Five wrong passwords in a row. If it was them, reset their password from Staff accounts.</span>
        </div>
        <RouterLink to="/users" class="btn-outline">Staff accounts</RouterLink>
      </section>
      <section v-if="!data.backup || data.backup.age_hours > 26" class="card home-banner warn">
        <Icon name="database" :size="22" />
        <div class="text">
          <b>{{ data.backup ? `The last backup is ${Math.round(data.backup.age_hours / 24)} day(s) old` : 'There is no backup yet' }}</b>
          <span>Take one now from Settings, and check the nightly backup is scheduled.</span>
        </div>
        <RouterLink to="/settings" class="btn-outline">Backups</RouterLink>
      </section>

      <div class="kpis">
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon" :class="{ amber: health?.database !== 'connected' }"><Icon name="database" :size="18" /></span><span class="kpi-label">Server</span></div>
          <span class="kpi-value small-value">{{ health?.database === 'connected' ? 'Running' : 'Database down' }}</span>
          <span class="kpi-sub">{{ data.environment === 'production' ? 'Production' : 'Set to ' + data.environment }}</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="users" :size="18" /></span><span class="kpi-label">Active accounts</span></div>
          <span class="kpi-value">{{ data.users_active }}</span>
          <span class="kpi-sub">{{ data.users_disabled }} switched off</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon" :class="{ amber: data.failed_24h > 10 }"><Icon name="shield" :size="18" /></span><span class="kpi-label">Sign-ins, last 24 hours</span></div>
          <span class="kpi-value">{{ data.sign_ins_24h }}</span>
          <span class="kpi-sub" :class="{ bad: data.failed_24h > 10 }">{{ data.failed_24h }} wrong password{{ data.failed_24h === 1 ? '' : 's' }}</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon brown"><Icon name="database" :size="18" /></span><span class="kpi-label">Last backup</span></div>
          <span class="kpi-value small-value">{{ data.backup ? data.backup.at : 'None' }}</span>
          <span class="kpi-sub">{{ data.backup ? `${data.backup.count} kept · ${data.backup.size_kb} KB` : 'Take one in Settings' }}</span>
        </div>
      </div>

      <div class="split">
        <div class="col">
          <section class="card">
            <div class="card-head"><h3>Recent changes</h3><RouterLink to="/activity">Activity log</RouterLink></div>
            <p v-if="!data.activity.length" class="home-empty">Nothing recorded yet.</p>
            <ul class="home-list">
              <li v-for="(a, i) in data.activity" :key="i">
                <div>
                  <b>{{ a.action }}</b> <span class="muted">· {{ a.who }}</span>
                  <p v-if="a.detail" class="sub">{{ a.detail }}</p>
                </div>
                <span class="muted when">{{ a.at }}</span>
              </li>
            </ul>
          </section>
        </div>

        <div class="col">
          <section class="card">
            <div class="card-head"><h3>Accounts by role</h3><RouterLink to="/roles">Roles</RouterLink></div>
            <ul class="home-list">
              <li v-for="r in data.by_role" :key="r.role"><span>{{ r.role }}</span><b class="num">{{ r.count }}</b></li>
            </ul>
          </section>

          <section class="card">
            <div class="card-head"><h3>To tidy up</h3></div>
            <ul class="home-list">
              <li>
                <span>Still on a temporary password</span>
                <b class="num" :class="{ bad: data.must_change }">{{ data.must_change }}</b>
              </li>
              <li>
                <span>Never signed in</span>
                <b class="num">{{ data.never_signed_in }}</b>
              </li>
            </ul>
            <p class="muted small">Switch off accounts nobody uses. A temporary password is one anyone who saw it could use.</p>
          </section>
        </div>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.small-value { font-size: 1.35rem; }
.when { font-size: .85rem; white-space: nowrap; font-variant-numeric: tabular-nums; }
.kpi-sub.bad { color: var(--danger); }
</style>
