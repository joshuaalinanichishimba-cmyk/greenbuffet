<!--
  The frame around every signed-in screen, built to the demo's measurements:
  a 252px forest-green sidebar with the bowl logo, the screens grouped under
  Today, Money, Business and Setup, the signed-in person at the bottom, and a
  white top bar with order search, the date and the kitchen's wait time.

  The demo has no till and no back office. The till sits first under Today,
  because this is a point of sale; everything the demo does not have sits in
  its own Back office group below the demo's four, so the demo's part of the
  sidebar reads exactly as it did.

  On a phone the sidebar slides in from the left behind a menu button, as the
  demo's does.
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { session } from '../stores/session'
import { api } from '../services/api'
import Icon from './Icon.vue'
import AccountMenu from './AccountMenu.vue'
import Avatar from './Avatar.vue'
import logoMark from '../assets/logo-mark.png'
import { homeFor, type HomeKind } from '../services/home'
import { THEME_LABELS, applyTheme, nextTheme, savedTheme, type ThemeChoice } from '../services/theme'

const router = useRouter()
const can = (...codes: string[]) => session.canAny(...codes)

// The first link is each account's own home, named for what it holds.
const home = computed(() => homeFor(session.user.value?.role_id, session.permissions.value))
const HOME_LABELS: Record<HomeKind, string> = {
  overview: 'Overview', system: 'System', money: 'Money', cashier: 'My till', stock: 'Store room', kitchen: 'Overview', it: 'IT workspace',
}

interface Link { to: string; label: string; icon: string; show: boolean; also?: string[] }

const groups = computed(() =>
  [
    {
      name: 'Today',
      links: [
        { to: '/', label: HOME_LABELS[home.value], icon: 'home', show: home.value !== 'kitchen' },
        { to: '/overview', label: 'Business overview', icon: 'chart', show: home.value !== 'overview' && can('reports.view') },
        { to: '/till', label: 'Till', icon: 'till', show: can('pos.use') },
        { to: '/orders', label: 'Orders', icon: 'receipt', show: can('pos.use', 'orders.view', 'reports.view') },
        { to: '/kitchen', label: 'Kitchen display', icon: 'flame', show: can('kitchen.view', 'orders.view', 'pos.use') },
      ],
    },
    {
      name: 'Money',
      links: [
        { to: '/payments', label: 'Payments', icon: 'card', show: can('reports.view', 'books.view') },
        { to: '/end-of-day', label: 'End of day', icon: 'calendarCheck', show: can('reports.view', 'books.view') },
        { to: '/reports', label: 'Sales analytics', icon: 'chart', show: can('reports.view', 'books.view'), also: ['/reports/downloads'] },
      ],
    },
    {
      name: 'Business',
      links: [
        { to: '/menu', label: 'Menu', icon: 'menu', show: can('menu.edit', 'kitchen.view', 'inventory.view'), also: ['/menu/choices', '/menu/ingredients'] },
        { to: '/promotions', label: 'Promotions', icon: 'tag', show: can('promos.manage') },
        { to: '/stock', label: 'Inventory', icon: 'box', show: can('inventory.view', 'purchases.manage'), also: ['/purchases'] },
        { to: '/feedback', label: 'Feedback', icon: 'star', show: can('feedback.view') },
      ],
    },
    {
      name: 'Setup',
      links: [
        { to: '/team', label: 'Team', icon: 'users', show: can('team.view', 'security.manage'), also: ['/team'] },
        { to: '/users', label: 'Staff & roles', icon: 'shield', show: can('staff.manage', 'roles.manage'), also: ['/roles'] },
        { to: '/settings', label: 'Settings', icon: 'sliders', show: can('settings.edit', 'menu.edit', 'books.view', 'audit.view'), also: ['/activity'] },
      ],
    },
    {
      name: 'Back office',
      links: [
        { to: '/customers', label: 'Customers & stamps', icon: 'customers', show: can('customers.view', 'pos.use', 'orders.view') },
        { to: '/books', label: 'The books', icon: 'book', show: can('books.view', 'reports.view') },
        { to: '/books/journal', label: 'Journal', icon: 'journal', show: can('books.view', 'reports.view') },
        { to: '/people', label: can('hr.view', 'hr.manage', 'attendance.manage') ? 'Staff clocking' : 'My clocking', icon: 'clock', show: can('hr.view', 'hr.manage', 'attendance.clock') },
        { to: '/payroll', label: 'Payroll', icon: 'wallet', show: can('payroll.view', 'payroll.manage') },
      ],
    },
    {
      // The technical side, kept apart from the business screens.
      name: 'Technical',
      links: [
        { to: '/it', label: 'IT workspace', icon: 'device', show: can('it.view'), also: ['/it'] },
      ],
    },
  ]
    .map((g) => ({ ...g, links: (g.links as Link[]).filter((l) => l.show) }))
    .filter((g) => g.links.length),
)

function isActive(link: Link) {
  const here = router.currentRoute.value.path
  if (link.to === '/') return here === '/'
  if (here === link.to) return true
  return (link.also ?? []).some((p) => here === p || here.startsWith(p + '/'))
}


const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

// The wait a customer at the counter is told: the base preparation time
// plus two minutes for every order already in the kitchen, as in the demo.
const waitMinutes = ref<number | null>(null)
async function loadWait() {
  try {
    const status = await api.get<{ wait_minutes: number }>('/dashboard/service')
    waitMinutes.value = status.wait_minutes
  } catch {
    waitMinutes.value = null
  }
}

const query = ref('')
function findOrder() {
  const term = query.value.trim()
  if (!term) return
  router.push({ path: '/orders', query: { q: term } })
  query.value = ''
}

const drawerOpen = ref(false)
watch(() => router.currentRoute.value.path, () => (drawerOpen.value = false))

// A quiet warning before an eight-hour shift token runs out mid-sale.
const minutesLeft = ref<number | null>(null)
let timer: number | undefined
function tick() {
  const at = session.expiresAt.value
  minutesLeft.value = at ? Math.round((at - Date.now()) / 60000) : null
}

onMounted(() => {
  tick()
  loadWait()
  timer = window.setInterval(() => {
    tick()
    loadWait()
  }, 30000)
})
onUnmounted(() => window.clearInterval(timer))

const theme = ref<ThemeChoice>(savedTheme())
function cycleTheme() {
  theme.value = nextTheme(theme.value)
  applyTheme(theme.value)
}
const themeIcon = computed(() => (theme.value === 'light' ? 'sun' : theme.value === 'dark' ? 'moon' : 'monitor'))

async function signOut() {
  await session.signOutEverywhere()
  router.replace('/login')
}
</script>

<template>
  <div class="shell" :class="{ open: drawerOpen }">
    <aside class="side" aria-label="Main">
      <div class="brand">
        <img :src="logoMark" alt="" width="40" height="31" />
        <div>
          <b>The Green Buffet</b>
          <span>Operations</span>
        </div>
        <button class="close" aria-label="Close menu" @click="drawerOpen = false">
          <Icon name="close" />
        </button>
      </div>

      <nav>
        <section v-for="g in groups" :key="g.name">
          <p class="group">{{ g.name }}</p>
          <RouterLink
            v-for="l in g.links"
            :key="l.to"
            :to="l.to"
            class="nav"
            :class="{ on: isActive(l) }"
          >
            <Icon :name="l.icon" />
            <span>{{ l.label }}</span>
          </RouterLink>
        </section>
      </nav>

      <div class="me">
        <RouterLink to="/profile" class="me-link" aria-label="My profile">
          <Avatar v-if="session.user.value" :user-id="session.user.value.id" :name="session.user.value.name"
                  :photo-id="session.user.value.photo_id" :size="38" />
        </RouterLink>
        <div class="me-text">
          <b>{{ session.user.value?.name }}</b>
          <span>{{ session.user.value?.role_label }}</span>
        </div>
        <button class="out" :aria-label="THEME_LABELS[theme]" :title="THEME_LABELS[theme]" @click="cycleTheme">
          <Icon :name="themeIcon" />
        </button>
        <button class="out" aria-label="Sign out" title="Sign out" @click="signOut">
          <Icon name="logout" />
        </button>
      </div>
    </aside>

    <div class="scrim" @click="drawerOpen = false" />

    <div class="body">
      <header class="top">
        <button class="burger" aria-label="Open menu" @click="drawerOpen = true">
          <Icon name="burger" />
        </button>
        <form class="search" role="search" @submit.prevent="findOrder">
          <Icon name="search" :size="18" />
          <input
            v-model="query"
            type="search"
            placeholder="Find an order, e.g. 1402 or a name"
            aria-label="Find an order"
          />
        </form>
        <span class="date">{{ today }}</span>
        <RouterLink v-if="waitMinutes !== null" to="/kitchen" class="open-pill">
          <span class="live" />
          Open · {{ waitMinutes }} min wait
        </RouterLink>
        <AccountMenu class="acct-slot" />
      </header>

      <p v-if="!session.connected.value" class="offline" role="status">
        Connection to the server lost (network or power). Reconnecting… What is on screen is kept;
        nothing is sent twice.
      </p>

      <p v-if="minutesLeft !== null && minutesLeft <= 15" class="expiry">
        Your sign-in ends in {{ Math.max(minutesLeft, 0) }} minutes. Sign in again to carry on.
      </p>

      <main class="page">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell { display: grid; grid-template-columns: 252px minmax(0, 1fr); min-height: 100vh; }

/* ---- the sidebar, as measured from the demo ---- */
.side {
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  background:
    radial-gradient(120% 40% at 0% 100%, rgba(156, 219, 90, .14), transparent 60%),
    var(--forest);
  color: #f6f3ec;
  padding: 1.1rem .8rem .9rem;
  display: flex; flex-direction: column; gap: .9rem;
  scrollbar-width: thin; scrollbar-color: rgba(255, 255, 255, .18) transparent;
}
.brand { display: flex; align-items: center; gap: .75rem; padding: 0 .4rem .4rem; }
.brand img { width: 40px; height: auto; background: #f6f3ec; padding: 5px; border-radius: 12px; display: block; }
.brand b { display: block; font-family: var(--display); font-weight: 800; font-size: .98rem; color: #f6f3ec; line-height: 1.1; }
.brand span { display: block; font-size: .78rem; font-weight: 700; color: var(--sprout); margin-top: .1rem; }
.close { display: none; margin-left: auto; background: none; border: 0; color: #f6f3ec; padding: .3rem; border-radius: 8px; }

nav { display: grid; gap: .9rem; }
nav section { display: grid; gap: .15rem; }
.group { margin: 0 0 .2rem; padding: 0 .75rem; font-size: .72rem; font-weight: 800; color: rgba(246, 243, 236, .5); letter-spacing: .02em; }
.nav {
  display: flex; align-items: center; gap: .75rem;
  padding: .55rem .75rem; border-radius: 12px;
  color: #dce8d9; text-decoration: none; font-weight: 600; font-size: .95rem;
  position: relative;
}
.nav:hover { background: rgba(255, 255, 255, .06); color: #fff; }
.nav.on { background: rgba(166, 217, 106, .16); color: #fff; }
.nav.on::before {
  content: ''; position: absolute; left: -.8rem; top: .45rem; bottom: .45rem;
  width: 4px; border-radius: 0 4px 4px 0; background: var(--sprout);
}
.nav :deep(svg) { flex: none; opacity: .92; }

.me {
  margin-top: auto; display: flex; align-items: center; gap: .65rem;
  background: rgba(255, 255, 255, .06); border-radius: 14px; padding: .6rem .65rem;
}
.avatar {
  width: 36px; height: 36px; border-radius: 50%; flex: none;
  display: grid; place-items: center;
  background: var(--sprout); color: #0f2a14; font-weight: 800; font-size: .85rem;
}
.me-text { min-width: 0; line-height: 1.25; }
.me-text b { display: block; font-size: .92rem; font-weight: 700; color: #f6f3ec; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.me-text span { display: block; font-size: .78rem; color: rgba(246, 243, 236, .7); }
.me-text + .out { margin-left: auto; }
.out { background: none; border: 0; color: rgba(246, 243, 236, .8); padding: .35rem; border-radius: 8px; }
.out:hover { background: rgba(255, 255, 255, .1); color: #fff; }

/* ---- the top bar ---- */
.body { min-width: 0; display: flex; flex-direction: column; }
.top {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; gap: 1rem;
  padding: .7rem 2rem;
  background: color-mix(in srgb, var(--paper) 88%, transparent);
  backdrop-filter: saturate(1.4) blur(10px);
  border-bottom: 1px solid var(--line);
}
.burger { display: none; background: none; border: 0; padding: .35rem; color: var(--ink); border-radius: 8px; }
.search {
  display: flex; align-items: center; gap: .55rem;
  flex: 0 1 380px; min-width: 0;
  padding: .55rem .85rem; border-radius: 12px;
  border: 1.5px solid var(--line); background: var(--paper); color: var(--muted);
}
.search:focus-within { border-color: var(--green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 25%, transparent); }
.search input { border: 0; background: transparent; padding: 0; min-height: 0; width: 100%; color: var(--ink); box-shadow: none; }
.search input:focus { box-shadow: none; }
.date { margin-left: auto; color: var(--muted); font-weight: 600; font-size: .92rem; white-space: nowrap; }
.open-pill {
  display: inline-flex; align-items: center; gap: .45rem;
  padding: .4rem .8rem; border-radius: 999px;
  background: var(--ok-soft); color: var(--green-deep);
  font-size: .85rem; font-weight: 800; text-decoration: none; white-space: nowrap;
}
.live { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 25%, transparent); }
.offline { margin: 0; padding: .55rem 2rem; background: var(--warn-soft); color: var(--warn); font-size: .88rem; font-weight: 700; }
.me-link { display: inline-flex; border-radius: 50%; }
.expiry { margin: 0; padding: .55rem 2rem; background: var(--warn-soft); color: var(--warn); font-size: .88rem; }

.page { padding: 1.4rem 2rem 5rem; max-width: 1220px; width: 100%; }

.scrim { display: none; }

/* ---- phones and small tablets: the sidebar becomes a drawer ---- */
@media (max-width: 900px) {
  .shell { grid-template-columns: minmax(0, 1fr); }
  .side {
    position: fixed; z-index: 50; left: 0; top: 0; bottom: 0; width: min(290px, 86vw); height: auto;
    transform: translateX(-102%); transition: transform .22s ease;
    padding-top: calc(1.1rem + env(safe-area-inset-top, 0px));
  }
  .shell.open .side { transform: none; }
  .shell.open .scrim { display: block; position: fixed; inset: 0; z-index: 40; background: rgba(10, 25, 14, .45); }
  .close, .burger { display: inline-grid; place-items: center; }
  .top { padding: .6rem max(1rem, env(safe-area-inset-left, 0px)); gap: .6rem; }
  .date { display: none; }
  .search { flex: 1 1 auto; }
  .acct-slot { margin-left: auto; }
  .offline { padding: .55rem 1rem; }
  .page { padding: 1.1rem max(1rem, env(safe-area-inset-left, 0px)) 4rem; }
}
@media (max-width: 520px) {
  .open-pill { padding: .35rem .6rem; font-size: .78rem; }
}
@media (max-width: 460px) {
  .open-pill { display: none; }
}
</style>
