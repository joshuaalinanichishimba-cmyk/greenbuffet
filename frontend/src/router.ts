import { createRouter, createWebHistory } from 'vue-router'
import { session } from './stores/session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/change-password', component: () => import('./views/ChangePasswordView.vue') },
    { path: '/', component: () => import('./views/DashboardView.vue') },
    {
      path: '/users',
      component: () => import('./views/UsersView.vue'),
      meta: { permission: 'staff.manage' },
    },
    {
      path: '/roles',
      component: () => import('./views/RolesView.vue'),
      meta: { permission: 'roles.manage' },
    },
    {
      path: '/till',
      component: () => import('./views/TillView.vue'),
      meta: { permission: 'pos.use' },
    },
    {
      path: '/kitchen',
      component: () => import('./views/KitchenView.vue'),
      meta: { permission: 'kitchen.read' },
    },
    {
      path: '/orders',
      component: () => import('./views/OrdersView.vue'),
      meta: { permission: 'orders.read' },
    },
    {
      path: '/settings',
      component: () => import('./views/SettingsView.vue'),
      meta: { permission: 'settings.read' },
    },
    {
      path: '/reports',
      component: () => import('./views/ReportsView.vue'),
      meta: { permission: 'reports.read' },
    },
    {
      path: '/people',
      component: () => import('./views/PeopleView.vue'),
      meta: { permission: 'people.read' },
    },
    {
      path: '/payroll',
      component: () => import('./views/PayrollView.vue'),
      meta: { permission: 'payroll.read' },
    },
    {
      path: '/books',
      component: () => import('./views/BooksView.vue'),
      meta: { permission: 'books.read' },
    },
    {
      path: '/books/journal',
      component: () => import('./views/JournalView.vue'),
      meta: { permission: 'books.read' },
    },
    {
      path: '/stock',
      component: () => import('./views/StockView.vue'),
      meta: { permission: 'stock.read' },
    },
    {
      path: '/purchases',
      component: () => import('./views/PurchasesView.vue'),
      meta: { permission: 'stock.read' },
    },
    {
      path: '/menu',
      component: () => import('./views/MenuView.vue'),
      meta: { permission: 'menu.read' },
    },
    {
      path: '/menu/choices',
      component: () => import('./views/ChoicesView.vue'),
      meta: { permission: 'menu.edit' },
    },
    {
      path: '/menu/ingredients',
      component: () => import('./views/IngredientsView.vue'),
      meta: { permission: 'menu.edit' },
    },
    {
      path: '/activity',
      component: () => import('./views/ActivityView.vue'),
      meta: { permission: 'audit.view' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (!session.ready.value) await session.restore()
  if (to.meta.public) return true
  if (!session.signedIn.value) return { path: '/login' }
  if (session.user.value?.must_change_password && to.path !== '/change-password') {
    return { path: '/change-password' }
  }
  // The server enforces this too; hiding the page simply avoids a dead end.
  const needed = to.meta.permission as string | undefined
  if (needed === 'settings.read') {
    return session.canAny('settings.edit', 'menu.edit', 'books.view', 'hr.view', 'purchases.manage', 'pos.use')
      ? true
      : { path: '/' }
  }
  if (needed === 'reports.read') {
    return session.canAny('reports.view', 'books.view') ? true : { path: '/' }
  }
  if (needed === 'people.read') {
    return session.canAny('hr.view', 'hr.manage', 'payroll.view', 'attendance.clock') ? true : { path: '/' }
  }
  if (needed === 'payroll.read') {
    return session.canAny('payroll.view', 'payroll.manage') ? true : { path: '/' }
  }
  if (needed === 'books.read') {
    return session.canAny('books.view', 'reports.view') ? true : { path: '/' }
  }
  if (needed === 'stock.read') {
    return session.canAny('inventory.view', 'purchases.manage', 'books.view', 'reports.view')
      ? true
      : { path: '/' }
  }
  if (needed === 'kitchen.read') {
    return session.canAny('kitchen.view', 'orders.view', 'pos.use') ? true : { path: '/' }
  }
  if (needed === 'orders.read') {
    return session.canAny('pos.use', 'orders.view', 'reports.view', 'books.view') ? true : { path: '/' }
  }
  if (needed === 'menu.read') {
    // Reading the menu is open to everyone who serves a customer; the server
    // applies the same list.
    const allowed = session.canAny('menu.edit', 'pos.use', 'orders.view', 'kitchen.view', 'inventory.view')
    return allowed ? true : { path: '/' }
  }
  if (needed && !session.can(needed)) return { path: '/' }
  return true
})

export default router
