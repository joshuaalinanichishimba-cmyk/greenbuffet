export type Choice = { id: string; name: string; price_ngwee: number; available: boolean }
export type Group = { id: string; name: string; min: number; max: number; items: Choice[] }
export type Product = {
  id: string; code: string; name: string; description: string; category: string
  price_ngwee: number; available: boolean; groups: Group[]
}
export type PaymentOutcome = 'successful' | 'pending' | 'failed'
export type Tracking = {
  order_number: string; total_ngwee: number; payment: PaymentOutcome | 'initiated'; kitchen: string | null
}

const api = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

export async function demoRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${api}/demo${path}`, body === undefined ? undefined : {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    if (response.status === 404 && path === '/menu') throw new Error('The demo API is disabled in this environment.')
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : 'The demo could not process that request.')
  }
  return response.json() as Promise<T>
}
