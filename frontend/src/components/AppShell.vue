<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { session } from '../stores/session'

const router = useRouter()

const can = (...codes: string[]) => session.canAny(...codes)

// The bar holds the handful of screens someone uses all day; everything else
// lives behind "More", so the navigation stays one line on a laptop.
const primary = computed(() =>
  [
    { to: '/', label: 'Dashboard', show: true },
    { to: '/till', label: 'Till', show: can('pos.use') },
    { to: '/kitchen', label: 'Kitchen', show: can('kitchen.view', 'orders.view', 'pos.use') },
    { to: '/orders', label: 'Orders', show: can('pos.use', 'orders.view', 'reports.view') },
    { to: '/reports', label: 'Reports', show: can('reports.view', 'books.view') },
  ].filter((l) => l.show),
)

const groups = computed(() =>
  [
    {
      name: 'Menu',
      links: [
        { to: '/menu', label: 'Menu and prices', show: can('menu.edit', 'pos.use', 'orders.view', 'kitchen.view', 'inventory.view') },
        { to: '/menu/choices', label: 'Choices', show: can('menu.edit') },
        { to: '/menu/ingredients', label: 'Ingredients', show: can('menu.edit') },
      ],
    },
    {
      name: 'Stock',
      links: [
        { to: '/stock', label: 'Stock on hand', show: can('inventory.view', 'purchases.manage') },
        { to: '/purchases', label: 'Buying in', show: can('inventory.view', 'purchases.manage') },
      ],
    },
    {
      name: 'Money',
      links: [
        { to: '/books', label: 'The books', show: can('books.view', 'reports.view') },
        { to: '/books/journal', label: 'Journal', show: can('books.view', 'reports.view') },
      ],
    },
    {
      name: 'People',
      links: [
        { to: '/people', label: 'Staff and clocking', show: can('hr.view', 'hr.manage', 'attendance.clock') },
        { to: '/payroll', label: 'Payroll', show: can('payroll.view', 'payroll.manage') },
        { to: '/users', label: 'Sign-ins', show: session.can('staff.manage') },
        { to: '/roles', label: 'Roles', show: session.can('roles.manage') },
        { to: '/activity', label: 'Activity log', show: session.can('audit.view') },
        { to: '/settings', label: 'Settings and files', show: can('settings.edit', 'menu.edit', 'books.view') },
      ],
    },
  ]
    .map((g) => ({ ...g, links: g.links.filter((l) => l.show) }))
    .filter((g) => g.links.length),
)

const menuOpen = ref(false)

// A quiet warning before an eight-hour shift token runs out mid-sale.
const minutesLeft = ref<number | null>(null)
let timer: number | undefined

function tick() {
  const at = session.expiresAt.value
  minutesLeft.value = at ? Math.round((at - Date.now()) / 60000) : null
}

onMounted(() => {
  tick()
  timer = window.setInterval(tick, 30000)
})
onUnmounted(() => window.clearInterval(timer))

// A tap on a link inside the sheet navigates; the sheet should not linger.
watch(() => router.currentRoute.value.path, () => (menuOpen.value = false))

function signOut() {
  session.signOut()
  router.replace('/login')
}
</script>

<template>
  <div class="shell">
    <header>
      <span class="mark" aria-hidden="true">GB</span>
      <div class="who">
        <b>{{ session.user.value?.name }}</b>
        <span>{{ session.user.value?.role_label }}</span>
      </div>
      <nav aria-label="Main">
        <RouterLink v-for="l in primary" :key="l.to" :to="l.to">{{ l.label }}</RouterLink>
        <div v-if="groups.length" class="more" @keydown.esc="menuOpen = false">
          <button class="more-button" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
            More
          </button>
          <div v-if="menuOpen" class="sheet" @click="menuOpen = false">
            <section v-for="g in groups" :key="g.name">
              <b>{{ g.name }}</b>
              <RouterLink v-for="l in g.links" :key="l.to" :to="l.to">{{ l.label }}</RouterLink>
            </section>
          </div>
        </div>
      </nav>
      <button class="btn-quiet btn-small sign-out" @click="signOut">Sign out</button>
    </header>

    <p v-if="minutesLeft !== null && minutesLeft <= 15" class="expiry">
      Your sign-in ends in {{ Math.max(minutesLeft, 0) }} minutes. Sign in again to carry on.
    </p>

    <main class="page">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell { min-height: 100vh; background: var(--bg); }
header {
  display: flex;
  align-items: center;
  gap: 0.7rem 1rem;
  flex-wrap: wrap;
  padding: 0.7rem clamp(0.8rem, 3vw, 1.4rem);
  background: var(--green);
  color: #eef5ec;
}
.mark {
  width: 36px; height: 36px; border-radius: 11px;
  background: var(--lime); color: #0f2a14;
  display: grid; place-items: center; font-weight: 800;
}
.who { display: grid; line-height: 1.2; margin-right: auto; }
.who span { font-size: 0.78rem; color: #bfd3bb; }
nav { display: flex; gap: 0.3rem; flex-wrap: wrap; order: 3; width: 100%; }
nav a {
  color: #d7e7d2;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.9rem;
  padding: 0.35rem 0.7rem;
  border-radius: 999px;
}
nav a.router-link-exact-active { background: rgba(255, 255, 255, 0.14); color: #fff; }
.more { position: relative; }
.more-button { background: none; border: 0; color: #d7e7d2; font-weight: 600; font-size: 0.9rem; padding: 0.35rem 0.7rem; border-radius: 999px; }
.more-button[aria-expanded='true'] { background: rgba(255, 255, 255, 0.14); color: #fff; }
.sheet {
  position: absolute; top: calc(100% + 0.4rem); left: 0; z-index: 30;
  background: #fff; color: var(--ink); border: 1px solid var(--line); border-radius: 14px;
  padding: 0.6rem; min-width: 240px; box-shadow: 0 12px 28px rgba(10, 30, 14, 0.18);
  display: grid; gap: 0.7rem;
}
.sheet b { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
.sheet section { display: grid; gap: 0.1rem; }
.sheet a { color: var(--ink); padding: 0.3rem 0.45rem; border-radius: 8px; font-weight: 500; }
.sheet a:hover, .sheet a.router-link-exact-active { background: #eef6ea; color: #11491f; }
.sign-out { background: transparent; border-color: rgba(255, 255, 255, 0.35); color: inherit; }
.expiry { margin: 0; padding: 0.5rem 1.2rem; background: #fff5d8; color: #6b4e00; font-size: 0.87rem; }

@media (min-width: 720px) {
  nav { order: 0; width: auto; }
}
</style>
