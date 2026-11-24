/**
 * The customer's API client.
 *
 * Kept separate from services/api.ts on purpose. That client carries a staff
 * token, redirects to the sign-in screen on a 401 and knows about sessions.
 * None of that belongs on a page a stranger is looking at, and a customer who
 * was bounced to a staff sign-in form would simply leave.
 */
const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export interface PublicZone {
  id: string
  name: string
  fee_ngwee: number
  minutes: number
  minimum_ngwee: number
}

export interface ShopInfo {
  name: string
  location: string
  phones: string[]
  accepting_orders: boolean
  prep_minutes: number
  closed_message: string
  zones: PublicZone[]
}

export interface PublicItem {
  id: string
  name: string
  price_ngwee: number
  is_available: boolean
}

export interface PublicGroup {
  id: string
  name: string
  min_select: number
  max_select: number
  items: PublicItem[]
}

export interface PublicProduct {
  id: string
  name: string
  description: string
  price_ngwee: number
  is_available: boolean
  photo_id: string
  groups: PublicGroup[]
}

export interface PublicCategory {
  id: string
  name: string
  description: string
  products: PublicProduct[]
}

export interface PlacedOrder {
  number: string
  token: string
  total_ngwee: number
}

export interface TrackedOrder {
  number: string
  token: string
  status: string
  fulfilment: string
  placed_at: string
  total_ngwee: number
  delivery_fee_ngwee: number
  customer_name: string
  address: string
  zone_name: string
  reject_reason: string
  minutes: number
  paid: boolean
  lines: string[]
}

async function call<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  }
  // A customer on a bad connection will press the button twice. The server
  // keys on this so the kitchen does not cook the same order two times.
  if (options.method && options.method !== 'GET') {
    headers['Idempotency-Key'] = crypto.randomUUID()
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, { ...options, headers })
  } catch {
    throw new Error('We could not reach the restaurant. Check your connection and try again.')
  }
  if (!response.ok) {
    let detail = 'Something went wrong. Please try again.'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* not JSON */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export const publicApi = {
  shop: () => call<ShopInfo>('/public/shop'),
  menu: () => call<{ categories: PublicCategory[] }>('/public/menu'),
  placeOrder: (body: unknown) =>
    call<PlacedOrder>('/public/orders', { method: 'POST', body: JSON.stringify(body) }),
  track: (token: string) => call<TrackedOrder>(`/public/orders/${encodeURIComponent(token)}`),
  points: (phone: string) => call<{ points: number }>(`/public/points/${encodeURIComponent(phone)}`),
  photoUrl: (id: string) => `${BASE}/public/photo/${encodeURIComponent(id)}`,
}
