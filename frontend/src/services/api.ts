/**
 * API client for the FastAPI backend.
 *
 * Every call goes through request(), so the token, error handling and the
 * idempotency key are applied in one place.
 */
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

/** The last error the server sent back, for the "Report a problem" form. */
export const lastError = { reference: '', message: '', at: 0 }

/** Shown on reports and in the IT workspace; raised with each release. */
export const APP_VERSION = '1.24.0'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

let token: string | null = null
try {
  token = localStorage.getItem('gb-token')
} catch {
  /* private browsing */
}

export function setToken(value: string | null) {
  token = value
  try {
    value ? localStorage.setItem('gb-token', value) : localStorage.removeItem('gb-token')
  } catch {
    /* ignore */
  }
}

export function getToken(): string | null {
  return token
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  }
  if (token) headers.Authorization = `Bearer ${token}`
  // A retried write must never charge twice; the server keys on this.
  if (options.method && options.method !== 'GET') {
    headers['Idempotency-Key'] = crypto.randomUUID()
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, { ...options, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check that the backend is running.')
  }

  // A 401 on the login form means the details were wrong; a 401 anywhere else
  // means the token has expired. Showing the wrong one of those two confuses
  // someone who simply mistyped their password.
  // A locked screen: the server refuses the token until the person unlocks.
  if (response.status === 423) {
    window.dispatchEvent(new CustomEvent('gb-locked'))
    throw new ApiError(423, 'The screen is locked. Unlock it to carry on.')
  }
  // An owner without two-step sign-in is sent to set it up.
  if (response.status === 428) {
    window.dispatchEvent(new CustomEvent('gb-two-step'))
  }
  if (response.status === 401 && !path.startsWith('/auth/login') && !path.startsWith('/auth/unlock')) {
    setToken(null)
    window.dispatchEvent(new CustomEvent('gb-session-ended'))
    throw new ApiError(401, 'Your session has ended. Sign in again.')
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error */
    }
    // Kept so a problem report can carry the reference without anyone copying it.
    const ref = /reference ([0-9a-f]{6})/.exec(detail)
    if (ref) lastError.reference = ref[1]
    lastError.message = detail
    lastError.at = Date.now()
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export interface User {
  id: string
  name: string
  email: string
  role_id: string
  role_label: string
  is_active: boolean
  must_change_password: boolean
  photo_id?: string | null
  totp_enabled?: boolean
  two_step_required?: boolean
}

export interface LoginResult {
  token: string
  expires_at: string
  user: User
  permissions: string[]
  needs_code?: boolean
  ticket?: string
  session_id?: string
}

export interface Role {
  id: string
  label: string
  description: string
  is_system: boolean
  permissions: string[]
}

export interface PermissionInfo {
  code: string
  label: string
  area: string
}

export interface AuditEntry {
  id: string
  at: string
  actor: string
  area: string
  action: string
  detail: string
  reference: string
  before: string | null
  after: string | null
}

export interface MenuCategory {
  id: string
  name: string
  description: string
  sort: number
  is_active: boolean
  product_count: number
  earns_stamp: boolean
}

export interface MenuOptionItem {
  id: string
  group_id: string
  name: string
  price_ngwee: number
  sort: number
  is_active: boolean
  is_available: boolean
}

export interface MenuOptionGroup {
  id: string
  name: string
  helper: string
  min_select: number
  max_select: number
  free_count?: number
  extra_ngwee?: number
  is_active: boolean
  items: MenuOptionItem[]
  used_by: number
}

export interface ProductOption {
  group_id: string
  name: string
  helper: string
  min_select: number
  max_select: number
  /** "Five included": picks after this many add extra_ngwee each. 0 = no such rule. */
  free_count?: number
  extra_ngwee?: number
  sort: number
  items: MenuOptionItem[]
}

export interface RecipeLine {
  id: string
  ingredient_id: string
  ingredient_name: string
  unit: string
  quantity_milli: number
  quantity_label: string
  note: string
  cost_ngwee: number
  line_cost_ngwee: number
}

export interface MenuProduct {
  id: string
  code: string
  name: string
  description: string
  category_id: string
  category_name: string
  price_ngwee: number
  vat_rate: number
  station: string
  is_active: boolean
  is_available: boolean
  sort: number
  option_groups: ProductOption[]
  recipe: RecipeLine[]
  recipe_cost_ngwee: number
}

export interface MenuIngredient {
  id: string
  name: string
  unit: string
  cost_ngwee: number
  note: string
  is_active: boolean
  used_in: number
}

export interface PriceChange {
  id: string
  at: string
  product_id: string
  product_name: string
  old_ngwee: number
  new_ngwee: number
  reason: string
  changed_by: string | null
}

export interface Shift {
  id: string
  opened_by: string
  opened_at: string
  float_ngwee: number
  closed_at: string | null
  closed_by: string | null
  expected_ngwee: number | null
  counted_ngwee: number | null
  variance_ngwee: number | null
  note: string
  is_open: boolean
  orders: number
  sales_ngwee: number
  // null while the till is open and the viewer is its cashier: the count is blind
  cash_ngwee: number | null
  cash_moves_ngwee?: number
  first_count_ngwee?: number | null
  reviewed_by?: string | null
  review_note?: string
  needs_review?: boolean
  by_method: { method: string; label: string; amount_ngwee: number; count: number }[]
}

export interface OrderLine {
  id: string
  product_id: string
  product_name: string
  product_code: string
  station: string
  unit_ngwee: number
  options_ngwee: number
  quantity: number
  line_ngwee: number
  note: string
  options: { group_name: string; item_name: string; price_ngwee: number; option_item_id?: string | null }[]
}

export interface OrderPayment {
  id: string
  method: string
  label: string
  amount_ngwee: number
  tendered_ngwee: number | null
  change_ngwee: number | null
  reference: string
  is_refund: boolean
  at: string
  taken_by: string | null
}

export interface Order {
  id: string
  number: string
  status: string
  order_type: string
  customer_name: string
  customer_phone: string
  note: string
  subtotal_ngwee: number
  discount_ngwee: number
  discount_reason?: string
  discount_approved_by?: string | null
  total_ngwee: number
  vat_ngwee: number
  paid_ngwee: number
  outstanding_ngwee: number
  change_ngwee: number
  created_by: string | null
  created_at: string
  paid_at: string | null
  cancelled_at: string | null
  cancel_reason: string
  lines: OrderLine[]
  payments: OrderPayment[]
}

export interface Receipt {
  business: string
  address: string
  phone: string
  tpin?: string
  vat_registered?: boolean
  number: string
  at: string
  served_by: string | null
  order_type: string
  customer: string
  status: string
  lines: { name: string; quantity: number; each_ngwee: number; total_ngwee: number; options: string[]; note: string }[]
  subtotal_ngwee: number
  discount_ngwee: number
  total_ngwee: number
  vat_ngwee: number
  payments: { label: string; amount_ngwee: number; reference: string; is_refund: boolean }[]
  change_ngwee: number
  footer: string
}

export interface DayTotals {
  date: string
  orders: number
  sales_ngwee: number
  vat_ngwee: number
  refunds_ngwee: number
  by_method: { method: string; label: string; amount_ngwee: number; count: number }[]
}

export interface KitchenItem {
  id: string
  product_name: string
  quantity: number
  choices: string
  note: string
  station: string
  station_label: string
  status: string
  handled_by: string | null
}

export interface KitchenTicket {
  order_id: string
  order_number: string
  order_type: string
  customer_name: string
  placed_at: string
  waiting_minutes: number
  status: string
  items: KitchenItem[]
}

export interface StockLevel {
  ingredient_id: string
  name: string
  unit: string
  quantity_milli: number
  reorder_milli: number
  cost_ngwee: number
  value_ngwee: number
  is_low: boolean
  used_in: number
}

export interface StockMove {
  id: string
  at: string
  ingredient_id: string
  ingredient_name: string
  unit: string
  kind: string
  kind_label: string
  quantity_milli: number
  balance_milli: number
  value_ngwee: number
  reference: string
  note: string
  by: string | null
}

export interface Supplier {
  id: string
  name: string
  contact: string
  phone: string
  email: string
  note: string
  is_active: boolean
  purchases: number
  spent_ngwee: number
}

export interface SupplierPayment {
  id: string
  at: string
  method: string
  amount_ngwee: number
  reference: string
  note: string
  by: string | null
}

export interface OwedRow {
  supplier_id: string
  supplier_name: string
  phone: string
  purchases: number
  owed_ngwee: number
  oldest_days: number
  overdue_ngwee: number
}

export interface Purchase {
  id: string
  number: string
  supplier_id: string
  supplier_name: string
  status: string
  invoice_number: string
  note: string
  total_ngwee: number
  created_at: string
  created_by: string | null
  received_at: string | null
  received_by: string | null
  lines: {
    id: string
    ingredient_id: string
    ingredient_name: string
    unit: string
    quantity_milli: number
    unit_cost_ngwee: number
    line_ngwee: number
  }[]
  paid_ngwee: number
  owed_ngwee: number
  payments: SupplierPayment[]
}

export interface BookAccount {
  id: string
  code: string
  name: string
  type: string
  type_label: string
  description: string
  is_system: boolean
  is_active: boolean
  is_cash: boolean
  balance_ngwee: number
}

export interface JournalEntry {
  id: string
  number: string
  entry_date: string
  memo: string
  source: string
  reference: string
  status: string
  total_ngwee: number
  created_by: string | null
  approved_by: string | null
  reverses_id: string | null
  reversed_by_id: string | null
  lines: {
    account_code: string
    account_name: string
    debit_ngwee: number
    credit_ngwee: number
    memo: string
  }[]
}

export interface LedgerRow {
  at: string
  entry_number: string
  memo: string
  reference: string
  debit_ngwee: number
  credit_ngwee: number
  balance_ngwee: number
}

export interface StatementRow {
  code: string
  name: string
  amount_ngwee: number
}

export interface ProfitAndLoss {
  from: string
  to: string
  income: StatementRow[]
  total_income_ngwee: number
  cost_of_sales: StatementRow[]
  total_cost_of_sales_ngwee: number
  gross_profit_ngwee: number
  gross_margin_percent: number
  expenses: StatementRow[]
  total_expenses_ngwee: number
  profit_ngwee: number
}

export interface BalanceSheet {
  as_at: string
  assets: StatementRow[]
  total_assets_ngwee: number
  liabilities: StatementRow[]
  total_liabilities_ngwee: number
  equity: StatementRow[]
  profit_this_period_ngwee: number
  total_equity_ngwee: number
  balanced: boolean
  difference_ngwee: number
}

export interface CashFlow {
  from: string
  to: string
  accounts: {
    code: string
    name: string
    opening_ngwee: number
    in_ngwee: number
    out_ngwee: number
    closing_ngwee: number
  }[]
  opening_ngwee: number
  in_ngwee: number
  out_ngwee: number
  closing_ngwee: number
}

export interface TrialBalance {
  as_at: string
  rows: { code: string; name: string; type: string; debit_ngwee: number; credit_ngwee: number }[]
  total_debit_ngwee: number
  total_credit_ngwee: number
  balanced: boolean
}

export interface Employee {
  id: string
  number: string
  name: string
  job_title: string
  department: string
  phone: string
  napsa_number: string
  tpin: string
  pay_method: string
  pay_account: string
  basic_ngwee: number
  allowances_ngwee: number
  leave_days_per_year: number
  start_date: string | null
  user_id: string | null
  is_active: boolean
  leave_taken: number
  leave_left: number
  clocked_in: boolean
}

export interface AttendanceRow {
  id: string
  employee_id: string
  employee_name: string
  day: string
  clock_in: string
  clock_out: string | null
  hours: number | null
}

export interface LeaveRow {
  id: string
  employee_id: string
  employee_name: string
  kind: string
  start: string
  end: string
  days: number
  reason: string
  status: string
  decided_by: string | null
}

export interface Payslip {
  id: string
  employee_id: string
  employee_name: string
  employee_number: string
  job_title: string
  napsa_number: string
  tpin: string
  basic_ngwee: number
  allowances_ngwee: number
  unpaid_days: number
  unpaid_deduction_ngwee: number
  gross_ngwee: number
  paye_ngwee: number
  napsa_employee_ngwee: number
  napsa_employer_ngwee: number
  nhima_employee_ngwee: number
  nhima_employer_ngwee: number
  net_ngwee: number
  days_worked: number
}

export interface PayrollRun {
  id: string
  period: string
  status: string
  gross_ngwee: number
  net_ngwee: number
  paye_ngwee: number
  napsa_ngwee: number
  nhima_ngwee: number
  employer_cost_ngwee: number
  created_by: string | null
  approved_by: string | null
  paid_by: string | null
  payslips: Payslip[]
}

export interface PayRates {
  paye_bands: (number | null)[][]
  napsa_percent: number
  napsa_ceiling_ngwee: number
  nhima_percent: number
  working_days: number
  checked: boolean
  note: string
}

export interface Dashboard {
  days: number
  orders: number
  sales_ngwee: number
  refunds_ngwee: number
  vat_ngwee: number
  food_cost_ngwee: number
  gross_margin_percent: number
  average_order_ngwee: number
  by_day: { date: string; orders: number; sales_ngwee: number }[]
  by_hour: { hour: number; sales_ngwee: number }[]
  top_items: { name: string; quantity: number; sales_ngwee: number }[]
  by_method: { method: string; label: string; amount_ngwee: number }[]
  kitchen_minutes: number | null
  stock_value_ngwee: number
  low_stock: string[]
  staff_on_now: number
}

export interface ReportInfo {
  id: string
  name: string
  permission: string
}

export interface ReportData {
  id: string
  name: string
  days: number
  headings: string[]
  rows: (string | number)[][]
}

export interface StoredFile {
  id: string
  name: string
  kind: string
  attached_to: string
  attached_id: string | null
  media_type: string
  size_bytes: number
  note: string
  is_primary: boolean
  at: string
  by: string | null
  url: string
  thumb_url: string | null
}

export interface BackupFile {
  name: string
  size_bytes: number
  at: string
}

export const api = {
  health: () => request<{ status: string; database: string; environment: string }>('/health'),
  login: (email: string, password: string, role_id?: string) =>
    request<LoginResult>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password, role_id: role_id || null }) }),
  signInRoles: () => request<{ id: string; label: string; sees: string; accounts: { name: string; email: string }[] }[]>('/auth/roles'),
  me: () => request<LoginResult>('/auth/me'),
  loginCode: (ticket: string, code: string) =>
    request<LoginResult>('/auth/login/code', { method: 'POST', body: JSON.stringify({ ticket, code }) }),
  logout: (sw = false) => request<{ ok: boolean }>('/auth/logout', { method: 'POST', body: JSON.stringify({ switch: sw }) }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean; token: string; expires_at: string }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
  roles: () => request<Role[]>('/admin/roles'),
  saveRole: (id: string, permissions: string[], label?: string) =>
    request<Role>(`/admin/roles/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ permissions, label }),
    }),
  createRole: (label: string, description: string, permissions: string[]) =>
    request<Role>('/admin/roles', {
      method: 'POST',
      body: JSON.stringify({ label, description, permissions }),
    }),
  users: () => request<User[]>('/admin/users'),
  createUser: (name: string, email: string, role_id: string) =>
    request<User & { temporary_password: string | null }>('/admin/users', {
      method: 'POST',
      body: JSON.stringify({ name, email, role_id }),
    }),
  patchUser: (id: string, changes: Partial<Pick<User, 'name' | 'email' | 'role_id' | 'is_active'>>) =>
    request<User>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  resetUserPassword: (id: string) =>
    request<{ user: User; temporary_password: string }>(`/admin/users/${id}/reset-password`, {
      method: 'POST',
    }),
  permissions: () => request<PermissionInfo[]>('/admin/permissions'),
  audit: (area?: string) =>
    request<AuditEntry[]>(`/admin/audit${area ? `?area=${encodeURIComponent(area)}` : ''}`),

  // ---- menu ----
  menuCategories: (includeHidden = false) =>
    request<MenuCategory[]>(`/menu/categories?include_hidden=${includeHidden}`),
  createCategory: (body: { name: string; description?: string; sort?: number }) =>
    request<MenuCategory>('/menu/categories', { method: 'POST', body: JSON.stringify(body) }),
  patchCategory: (id: string, body: Partial<Pick<MenuCategory, 'name' | 'description' | 'sort' | 'is_active' | 'earns_stamp'>>) =>
    request<MenuCategory>(`/menu/categories/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  menuProducts: (opts: { categoryId?: string; includeHidden?: boolean; search?: string } = {}) => {
    const q = new URLSearchParams()
    if (opts.categoryId) q.set('category_id', opts.categoryId)
    if (opts.includeHidden) q.set('include_hidden', 'true')
    if (opts.search) q.set('search', opts.search)
    const query = q.toString()
    return request<MenuProduct[]>(`/menu/products${query ? `?${query}` : ''}`)
  },
  createProduct: (body: Record<string, unknown>) =>
    request<MenuProduct>('/menu/products', { method: 'POST', body: JSON.stringify(body) }),
  patchProduct: (id: string, body: Record<string, unknown>) =>
    request<MenuProduct>(`/menu/products/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  setProductGroups: (id: string, group_ids: string[]) =>
    request<MenuProduct>(`/menu/products/${id}/option-groups`, {
      method: 'PUT',
      body: JSON.stringify({ group_ids }),
    }),
  setProductRecipe: (id: string, lines: { ingredient_id: string; quantity_milli: number; note?: string }[]) =>
    request<MenuProduct>(`/menu/products/${id}/recipe`, { method: 'PUT', body: JSON.stringify(lines) }),

  optionGroups: () => request<MenuOptionGroup[]>('/menu/option-groups'),
  createOptionGroup: (body: Record<string, unknown>) =>
    request<MenuOptionGroup>('/menu/option-groups', { method: 'POST', body: JSON.stringify(body) }),
  patchOptionGroup: (id: string, body: Record<string, unknown>) =>
    request<MenuOptionGroup>(`/menu/option-groups/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  addOptionItem: (groupId: string, body: Record<string, unknown>) =>
    request<MenuOptionItem>(`/menu/option-groups/${groupId}/items`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  patchOptionItem: (id: string, body: Record<string, unknown>) =>
    request<MenuOptionItem>(`/menu/option-items/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  ingredients: (includeHidden = false) =>
    request<MenuIngredient[]>(`/menu/ingredients?include_hidden=${includeHidden}`),
  createIngredient: (body: Record<string, unknown>) =>
    request<MenuIngredient>('/menu/ingredients', { method: 'POST', body: JSON.stringify(body) }),
  patchIngredient: (id: string, body: Record<string, unknown>) =>
    request<MenuIngredient>(`/menu/ingredients/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  priceChanges: () => request<PriceChange[]>('/menu/price-changes'),

  // ---- the till ----
  currentShift: () => request<Shift | null>('/sales/shifts/current'),
  openShift: (float_ngwee: number) =>
    request<Shift>('/sales/shifts', { method: 'POST', body: JSON.stringify({ float_ngwee }) }),
  closeShift: (id: string, counted_ngwee: number, note = '') =>
    request<Shift>(`/sales/shifts/${id}/close`, {
      method: 'POST',
      body: JSON.stringify({ counted_ngwee, note }),
    }),
  shifts: () => request<Shift[]>('/sales/shifts'),

  createOrder: (body: Record<string, unknown>) =>
    request<Order>('/sales/orders', { method: 'POST', body: JSON.stringify(body) }),
  orders: (opts: { status?: string; today?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (opts.status) q.set('status', opts.status)
    q.set('today', String(opts.today ?? true))
    return request<Order[]>(`/sales/orders?${q.toString()}`)
  },
  takePayment: (orderId: string, body: Record<string, unknown>) =>
    request<Order>(`/sales/orders/${orderId}/payments`, { method: 'POST', body: JSON.stringify(body) }),
  refundOrder: (orderId: string, body: Record<string, unknown>) =>
    request<Order>(`/sales/orders/${orderId}/refund`, { method: 'POST', body: JSON.stringify(body) }),
  cancelOrder: (orderId: string, reason: string) =>
    request<Order>(`/sales/orders/${orderId}/cancel`, { method: 'POST', body: JSON.stringify({ reason }) }),
  receipt: (orderId: string) => request<Receipt>(`/sales/orders/${orderId}/receipt`),
  todayTotals: () => request<DayTotals>('/sales/today'),

  // ---- the kitchen board ----
  kitchenTickets: (station?: string) =>
    request<KitchenTicket[]>(`/kitchen/tickets${station ? `?station=${station}` : ''}`),
  setTicketStatus: (orderId: string, status: string) =>
    request<KitchenTicket[]>(`/kitchen/tickets/${orderId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),
  setKitchenItemStatus: (itemId: string, status: string) =>
    request<KitchenTicket[]>(`/kitchen/items/${itemId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),

  // ---- stock ----
  stockLevels: (lowOnly = false) =>
    request<StockLevel[]>(`/stock/levels?low_only=${lowOnly}`),
  stockMoves: (ingredientId?: string) =>
    request<StockMove[]>(`/stock/moves${ingredientId ? `?ingredient_id=${ingredientId}` : ''}`),
  adjustStock: (ingredient_id: string, quantity_milli: number, kind = 'adjustment', note = '') =>
    request<StockLevel>('/stock/adjust', {
      method: 'POST',
      body: JSON.stringify({ ingredient_id, quantity_milli, kind, note }),
    }),
  countStock: (ingredient_id: string, counted_milli: number, note = '') =>
    request<StockLevel>('/stock/count', {
      method: 'POST',
      body: JSON.stringify({ ingredient_id, counted_milli, note }),
    }),
  setReorderLevel: (ingredient_id: string, reorder_milli: number) =>
    request<StockLevel>('/stock/reorder-level', {
      method: 'POST',
      body: JSON.stringify({ ingredient_id, reorder_milli }),
    }),
  stockValue: () =>
    request<{ ingredients: number; value_ngwee: number; low: string[]; negative: string[] }>('/stock/value'),

  suppliers: () => request<Supplier[]>('/stock/suppliers'),
  createSupplier: (body: Record<string, unknown>) =>
    request<Supplier>('/stock/suppliers', { method: 'POST', body: JSON.stringify(body) }),
  purchases: () => request<Purchase[]>('/stock/purchases'),
  createPurchase: (body: Record<string, unknown>) =>
    request<Purchase>('/stock/purchases', { method: 'POST', body: JSON.stringify(body) }),
  receivePurchase: (id: string) =>
    request<Purchase>(`/stock/purchases/${id}/receive`, { method: 'POST' }),
  cancelPurchase: (id: string) =>
    request<Purchase>(`/stock/purchases/${id}/cancel`, { method: 'POST' }),
  paySupplier: (id: string, body: Record<string, unknown>) =>
    request<Purchase>(`/stock/purchases/${id}/pay`, { method: 'POST', body: JSON.stringify(body) }),
  owedToSuppliers: () => request<OwedRow[]>('/stock/owed'),

  // ---- the books ----
  bookAccounts: () => request<BookAccount[]>('/books/accounts'),
  journal: (source?: string) =>
    request<JournalEntry[]>(`/books/journal${source ? `?source=${source}` : ''}`),
  createJournalEntry: (body: Record<string, unknown>) =>
    request<JournalEntry>('/books/journal', { method: 'POST', body: JSON.stringify(body) }),
  approveJournalEntry: (id: string) =>
    request<JournalEntry>(`/books/journal/${id}/approve`, { method: 'POST' }),
  reverseJournalEntry: (id: string, reason: string) =>
    request<JournalEntry>(`/books/journal/${id}/reverse`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  ledger: (code: string) => request<LedgerRow[]>(`/books/ledger/${code}`),
  trialBalance: (month?: string) =>
    request<TrialBalance>(`/books/trial-balance${month ? `?month=${month}` : ''}`),
  profitAndLoss: (month?: string) =>
    request<ProfitAndLoss>(`/books/profit-and-loss${month ? `?month=${month}` : ''}`),
  balanceSheet: (month?: string) =>
    request<BalanceSheet>(`/books/balance-sheet${month ? `?month=${month}` : ''}`),
  cashFlow: (month?: string) =>
    request<CashFlow>(`/books/cash-flow${month ? `?month=${month}` : ''}`),

  // ---- people and payroll ----
  employees: () => request<Employee[]>('/people/employees'),
  createEmployee: (body: Record<string, unknown>) =>
    request<Employee>('/people/employees', { method: 'POST', body: JSON.stringify(body) }),
  updateEmployee: (id: string, body: Record<string, unknown>) =>
    request<Employee>(`/people/employees/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  attendance: () => request<AttendanceRow[]>('/people/attendance'),
  clockIn: (employee_id?: string) =>
    request<AttendanceRow>('/people/clock-in', { method: 'POST', body: JSON.stringify({ employee_id }) }),
  clockOut: (employee_id?: string) =>
    request<AttendanceRow>('/people/clock-out', { method: 'POST', body: JSON.stringify({ employee_id }) }),
  leaveRequests: () => request<LeaveRow[]>('/people/leave'),
  requestLeave: (body: Record<string, unknown>) =>
    request<LeaveRow>('/people/leave', { method: 'POST', body: JSON.stringify(body) }),
  decideLeave: (id: string, approve: boolean) =>
    request<LeaveRow>(`/people/leave/${id}/decide`, { method: 'POST', body: JSON.stringify({ approve }) }),
  payrollRuns: () => request<PayrollRun[]>('/people/payroll/runs'),
  preparePayroll: (period: string) =>
    request<PayrollRun>('/people/payroll/runs', { method: 'POST', body: JSON.stringify({ period }) }),
  approvePayroll: (id: string) =>
    request<PayrollRun>(`/people/payroll/runs/${id}/approve`, { method: 'POST' }),
  payPayroll: (id: string) =>
    request<PayrollRun>(`/people/payroll/runs/${id}/pay`, { method: 'POST' }),
  payRates: () => request<PayRates>('/people/payroll/rates'),
  savePayRates: (body: PayRates) =>
    request<PayRates>('/people/payroll/rates', { method: 'PUT', body: JSON.stringify(body) }),

  // ---- reports ----
  dashboard: (days = 30) => request<Dashboard>(`/reports/dashboard?days=${days}`),
  reportList: () => request<ReportInfo[]>('/reports/list'),
  report: (id: string, days = 30) => request<ReportData>(`/reports/${id}?days=${days}`),

  // ---- settings, files and backups ----
  settings: () => request<{ values: Record<string, string> }>('/settings'),
  saveSettings: (values: Record<string, string>) =>
    request<{ values: Record<string, string> }>('/settings', {
      method: 'PUT',
      body: JSON.stringify({ values }),
    }),
  storedFiles: (opts: { attached_to?: string; attached_id?: string; kind?: string } = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(opts)) if (v) q.set(k, v)
    const query = q.toString()
    return request<StoredFile[]>(`/settings/files${query ? `?${query}` : ''}`)
  },
  uploadPhoto: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
    const response = await fetch(`${base}/profile/me/photo`, {
      method: 'POST', headers: { Authorization: `Bearer ${getToken()}` }, body: form,
    })
    if (!response.ok) {
      let detail = 'The photograph could not be stored.'
      try {
        const body = await response.json()
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        /* non-JSON error */
      }
      throw new ApiError(response.status, detail)
    }
    return (await response.json()) as { photo_id: string }
  },
  uploadFile: async (file: File, fields: Record<string, string | boolean>) => {
    const form = new FormData()
    form.append('file', file)
    for (const [k, v] of Object.entries(fields)) form.append(k, String(v))
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
    const response = await fetch(`${base}/settings/files`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
      body: form,
    })
    if (!response.ok) {
      let detail = 'The file could not be stored.'
      try {
        const body = await response.json()
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        /* non-JSON error */
      }
      throw new ApiError(response.status, detail)
    }
    return (await response.json()) as StoredFile
  },
  deleteFile: (id: string) => request<void>(`/settings/files/${id}`, { method: 'DELETE' }),
  backups: () => request<BackupFile[]>('/settings/backups'),
  makeBackup: () => request<BackupFile>('/settings/backups', { method: 'POST' }),

  // The named methods above were written one screen at a time. The customer
  // stages added enough routes that naming every one of them stopped earning
  // its keep, so these four are the plain way to call anything.
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) }),
  remove: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

// ---- profiles and the team (stage 23) ----

export type PresenceStatus = 'online' | 'away' | 'lost' | 'offline' | 'unknown'

export interface Presence {
  status: PresenceStatus
  label: string
  last_active: string | null
  devices: number
}

export interface Duty {
  on_staff_list: boolean
  on_duty: boolean
  since: string | null
  on_leave: boolean
  till_open: boolean
  till_since: string | null
}

export interface TeamCard {
  id: string
  name: string
  initials: string
  photo_id: string | null
  role_id: string
  role_label: string
  job_title: string
  department: string
  employee_number: string
  presence: Presence
  duty: Duty
  duty_label: string
  account: { code: 'active' | 'suspended' | 'archived' | 'new'; label: string }
}

export interface Profile extends TeamCard {
  email: string
  phone: string
  employment_status: string
  start_date: string | null
  created_at: string | null
  created_by: string
  responsibilities: { area: string; items: string[] }[]
  two_step: { enabled: boolean; required: boolean }
  tabs: string[]
  can: Record<'edit_account' | 'edit_employment' | 'change_role' | 'suspend' | 'restore' | 'archive'
    | 'reset_password' | 'revoke_sessions' | 'reset_two_step', boolean>
  is_me: boolean
  suspended_reason?: string
  archived_at?: string | null
  preferences?: { notify: Record<string, boolean>; labels: Record<string, string> }
}

export interface Notice {
  id: string
  at: string
  kind: string
  level: 'info' | 'warn'
  title: string
  body: string
  link: string
  read: boolean
}

export interface DeviceSession {
  id: string
  device: string
  browser: string
  ip: string
  started_at: string
  last_seen_at: string | null
  last_active_at: string | null
  expires_at: string
  state: PresenceStatus
  state_label: string
  this_device: boolean
  ended_at?: string
  reason?: string
}
