/**
 * Which first screen an account gets.
 *
 * The seven starting roles are matched by name. A role the owner made up
 * later is placed by what it is allowed to do, so "Shift supervisor" with the
 * till and reports lands on the Overview, and "Store hand" with only stock
 * lands on the store-room home.
 */
export type HomeKind = 'overview' | 'system' | 'money' | 'cashier' | 'kitchen' | 'stock' | 'it'

// The five account types. The Administrator and Inventory staff roles were
// retired (24 Nov 2026): the system panel now sits on the owner's Overview,
// the store-room panel on the manager's and owner's.
const BY_ROLE: Record<string, HomeKind> = {
  owner: 'overview',
  manager: 'overview',
  accountant: 'money',
  cashier: 'cashier',
  kitchen: 'kitchen',
  it: 'it',
}

export function homeFor(roleId: string | undefined, permissions: string[]): HomeKind {
  if (roleId && BY_ROLE[roleId]) return BY_ROLE[roleId]
  const has = (...codes: string[]) => codes.some((c) => permissions.includes(c))
  if (has('service.control', 'promos.manage', 'menu.edit') && has('reports.view')) return 'overview'
  if (has('books.view', 'payroll.view')) return 'money'
  if (has('reports.view')) return 'overview'
  if (has('staff.manage', 'settings.edit')) return 'system'
  if (has('pos.use')) return 'cashier'
  if (has('kitchen.view')) return 'kitchen'
  if (has('inventory.view', 'inventory.adjust', 'purchases.manage')) return 'stock'
  return 'overview'
}

export function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

export function firstName(name: string | undefined): string {
  return (name ?? '').split(/\s+/)[0] || 'there'
}

export function problemText(problem: unknown, fallback: string): string {
  return problem instanceof Error ? problem.message : fallback
}
