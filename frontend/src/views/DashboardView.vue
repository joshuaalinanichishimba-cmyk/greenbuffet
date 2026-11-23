<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api } from '../services/api'
import { session } from '../stores/session'

const health = ref<{ status: string; database: string; environment: string } | null>(null)
const users = ref<number | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    health.value = await api.health()
  } catch {
    error.value = 'The backend is not answering. Check its window.'
  }
  if (session.can('staff.manage')) {
    try {
      users.value = (await api.users()).length
    } catch {
      /* not permitted */
    }
  }
})

// Each module arrives at the stage shown. Stage 2 is staff accounts and roles.
const modules = [
  { name: 'Till', perm: 'pos.use', stage: 4, to: '/till' },
  { name: 'Orders', perm: 'orders.view', stage: 4, to: '/orders' },
  { name: 'Kitchen display', perm: 'kitchen.view', stage: 5, to: '/kitchen' },
  { name: 'Menu and recipes', perm: 'menu.edit', stage: 3, to: '/menu' },
  { name: 'Staff accounts', perm: 'staff.manage', stage: 2, to: '/users' },
  { name: 'Roles', perm: 'roles.manage', stage: 2, to: '/roles' },
  { name: 'Activity log', perm: 'audit.view', stage: 2, to: '/activity' },
  { name: 'Stock', perm: 'inventory.view', stage: 6, to: '/stock' },
  { name: 'Buying in', perm: 'purchases.manage', stage: 6, to: '/purchases' },
  { name: 'Accounting and books', perm: 'books.view', stage: 7, to: '/books' },
  { name: 'Staff and clocking', perm: 'hr.view', stage: 8, to: '/people' },
  { name: 'Payroll', perm: 'payroll.view', stage: 8, to: '/payroll' },
  { name: 'Reports', perm: 'reports.view', stage: 9, to: '/reports' },
]
</script>

<template>
  <AppShell>
    <h1>The Green Buffet</h1>
    <p class="lead">
      Signed in as {{ session.user.value?.name }}. The till, orders, the menu, staff accounts, roles
      and the activity log are ready to use; the rest arrive stage by stage.
    </p>

    <section class="cards">
      <article class="card" :class="health?.status === 'ok' ? 'good' : 'bad'">
        <b>{{ health?.status === 'ok' ? 'Connected' : 'Not connected' }}</b>
        <span>Backend and database</span>
      </article>
      <article class="card">
        <b>{{ health?.environment ?? '—' }}</b>
        <span>Environment</span>
      </article>
      <article class="card">
        <b>{{ session.permissions.value.length }}</b>
        <span>Permissions on your role</span>
      </article>
      <article v-if="users !== null" class="card">
        <b>{{ users }}</b>
        <span>Staff accounts</span>
      </article>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <h2>What you can open</h2>
    <ul class="modules">
      <li v-for="m in modules" :key="m.name" :class="{ off: !session.can(m.perm) }">
        <template v-if="m.to && session.can(m.perm)">
          <RouterLink :to="m.to"><b>{{ m.name }}</b></RouterLink>
          <span>Ready now</span>
        </template>
        <template v-else>
          <b>{{ m.name }}</b>
          <span v-if="!session.can(m.perm)">Your role does not include this</span>
          <span v-else>Ready at stage {{ m.stage }}</span>
        </template>
      </li>
    </ul>
  </AppShell>
</template>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.8rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 0.9rem 1rem; display: grid; gap: 0.15rem; }
.card b { font-size: 1.3rem; }
.card span { font-size: 0.82rem; color: var(--muted); }
.card.good b { color: var(--green-mid); }
.card.bad b { color: var(--danger); }
.modules { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 0.6rem; }
.modules li { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 0.7rem 0.9rem; display: grid; gap: 0.15rem; }
.modules li span { font-size: 0.8rem; color: var(--muted); }
.modules li.off { opacity: 0.55; }
.modules a { color: var(--green-mid); text-decoration: none; }
.modules a:hover b { text-decoration: underline; }
</style>
