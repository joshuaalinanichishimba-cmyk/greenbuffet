/**
 * Selling cash when the server cannot be reached.
 *
 * The till keeps three things on the device:
 * - the menu and prices from the last time it loaded, so the screen still
 *   works with the network down;
 * - whose till is open (the shift), read from the server each time the till
 *   loads;
 * - the cash sales taken while offline, each with its own id made here
 *   before anything is sent.
 *
 * When the server answers again, the waiting sales are sent one at a time,
 * oldest first. The server records an id once, so a sale sent twice (a
 * dropped reply, a second tab) is still one sale. A sale is only removed
 * from this device after the server has said it has it.
 *
 * Everything is kept in IndexedDB, which survives closing the browser and
 * restarting the computer. Nothing secret is kept: no passwords, no codes.
 */
import { computed, ref } from 'vue'
import { ApiError, api, type MenuCategory, type MenuProduct, type Order, type Receipt } from './api'

export interface OfflineLine {
  product_id: string
  quantity: number
  note: string
  options: { option_item_id: string }[]
  // for the receipt and the waiting list only; the server prices it again
  name: string
  option_names: string[]
  total_ngwee: number
}

export interface OfflineSale {
  id: string
  user_id: string
  user_name: string
  shift_id: string
  receipt_number: string
  taken_at: string
  order_type: string
  customer_name: string
  note: string
  lines: OfflineLine[]
  charged_ngwee: number
  tendered_ngwee: number | null
  // filled in as it is sent
  state: 'waiting' | 'problem'
  problem: string
  tries: number
}

export interface SentSale {
  id: string
  receipt_number: string
  order_number: string
  notes: string[]
  at: string
}

// ---- IndexedDB, kept small --------------------------------------------------

const DB_NAME = 'gb-offline'
let opening: Promise<IDBDatabase> | null = null

function database(): Promise<IDBDatabase> {
  if (opening) return opening
  opening = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains('sales')) db.createObjectStore('sales', { keyPath: 'id' })
      if (!db.objectStoreNames.contains('kept')) db.createObjectStore('kept')
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => {
      opening = null
      reject(req.error)
    }
  })
  return opening
}

async function tx<T>(store: string, mode: IDBTransactionMode, work: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await database()
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode)
    const req = work(t.objectStore(store))
    t.oncomplete = () => resolve(req.result)
    t.onerror = () => reject(t.error)
    t.onabort = () => reject(t.error)
  })
}

export async function keep<T>(name: string, value: T): Promise<void> {
  try {
    await tx('kept', 'readwrite', (s) => s.put(JSON.parse(JSON.stringify(value)), name))
  } catch {
    /* storage blocked: the till still works while online */
  }
}

export async function kept<T>(name: string): Promise<T | null> {
  try {
    return ((await tx('kept', 'readonly', (s) => s.get(name))) as T | undefined) ?? null
  } catch {
    return null
  }
}

async function allSales(): Promise<OfflineSale[]> {
  try {
    const rows = (await tx('sales', 'readonly', (s) => s.getAll())) as OfflineSale[]
    return rows.sort((a, b) => a.taken_at.localeCompare(b.taken_at))
  } catch {
    return []
  }
}

// ---- reachable or not -------------------------------------------------------

/** False while the server cannot be reached. */
export const reachable = ref(true)
/** Sales on this device not yet recorded by the server, for everyone. */
export const waiting = ref<OfflineSale[]>([])
/** Sales the server recorded in this session, newest first, for the till to show. */
export const sent = ref<SentSale[]>([])
export const syncing = ref(false)

export const waitingCount = computed(() => waiting.value.length)

async function refreshWaiting() {
  waiting.value = await allSales()
}

/** Called by the API client after every request, so the till knows at once. */
export function markReachable(ok: boolean) {
  const was = reachable.value
  reachable.value = ok
  if (ok && !was) syncNow().catch(() => undefined)
  if (!ok) startWatching()
}

// While offline, the server is asked once every 15 seconds whether it is
// back. A cheap request with no sign-in, so it works even if the session
// ended in the meantime.
let watcher: number | null = null
function startWatching() {
  if (watcher !== null) return
  watcher = window.setInterval(async () => {
    try {
      await api.health()
      stopWatching()
      markReachable(true)
    } catch {
      /* still down */
    }
  }, 15_000)
}
function stopWatching() {
  if (watcher !== null) window.clearInterval(watcher)
  watcher = null
}

// ---- the menu and the open till, kept for when the network drops -----------

export interface Ready {
  shift_id: string | null
  user_id: string
  user_name: string
}

export async function keepMenu(categories: MenuCategory[], products: MenuProduct[]) {
  await keep('menu', { categories, products, at: new Date().toISOString() })
}

export async function keptMenu() {
  return kept<{ categories: MenuCategory[]; products: MenuProduct[]; at: string }>('menu')
}

export async function keepReady(ready: Ready) {
  await keep(`ready-${ready.user_id}`, ready)
}

export async function keptReady(userId: string) {
  return kept<Ready>(`ready-${userId}`)
}

/** The business details printed at the top of a receipt. */
export async function keepReceiptHeader(r: Receipt) {
  await keep('receipt-header', { business: r.business, address: r.address, phone: r.phone, tpin: r.tpin ?? '', footer: r.footer })
}

export async function keptReceiptHeader() {
  return kept<{ business: string; address: string; phone: string; tpin: string; footer: string }>('receipt-header')
}

// ---- taking and sending sales ---------------------------------------------

/** The short number on the customer's receipt: T-1, T-2 … per device, per day. */
async function nextReceiptNumber(): Promise<string> {
  const today = new Date().toISOString().slice(0, 10)
  const counter = (await kept<{ day: string; n: number }>('receipt-counter')) ?? { day: today, n: 0 }
  const n = counter.day === today ? counter.n + 1 : 1
  await keep('receipt-counter', { day: today, n })
  return `T-${n}`
}

export async function takeOfflineSale(
  sale: Omit<OfflineSale, 'id' | 'receipt_number' | 'taken_at' | 'state' | 'problem' | 'tries'>,
): Promise<OfflineSale> {
  const full: OfflineSale = {
    ...sale,
    id: crypto.randomUUID(),
    receipt_number: await nextReceiptNumber(),
    taken_at: new Date().toISOString(),
    state: 'waiting',
    problem: '',
    tries: 0,
  }
  // Written before the receipt is shown. If this fails the sale is not taken.
  await tx('sales', 'readwrite', (s) => s.put(JSON.parse(JSON.stringify(full))))
  await refreshWaiting()
  return full
}

let running: Promise<void> | null = null

/**
 * Sends this person's waiting sales. Someone else's wait for them to sign
 * in, because the server puts a sale on the till of whoever took it.
 */
export function syncNow(userId?: string): Promise<void> {
  if (running) return running
  running = (async () => {
    syncing.value = true
    try {
      const me = userId ?? currentUserId
      if (!me) return
      for (const sale of await allSales()) {
        if (sale.user_id !== me || sale.state === 'problem') continue
        try {
          const out = await api.post<{ order: Order; already: boolean; notes: string[] }>('/sales/offline/sales', {
            id: sale.id,
            taken_at: sale.taken_at,
            shift_id: sale.shift_id,
            receipt_number: sale.receipt_number,
            order_type: sale.order_type,
            customer_name: sale.customer_name,
            note: sale.note,
            charged_ngwee: sale.charged_ngwee,
            tendered_ngwee: sale.tendered_ngwee,
            lines: sale.lines.map((l) => ({ product_id: l.product_id, quantity: l.quantity, note: l.note, options: l.options })),
          })
          await tx('sales', 'readwrite', (s) => s.delete(sale.id))
          sent.value = [
            { id: sale.id, receipt_number: sale.receipt_number, order_number: out.order.number, notes: out.notes, at: new Date().toISOString() },
            ...sent.value,
          ].slice(0, 30)
        } catch (e) {
          if (!(e instanceof ApiError) || e.status === 0) break // the network is down again: stop and wait
          if (e.status === 401 || e.status === 423 || e.status === 428 || e.status === 429 || e.status >= 500) break
          // The server read it and said no (a week old, someone else's till,
          // an item that no longer exists). Kept, marked, and not sent again
          // until someone looks at it.
          const marked: OfflineSale = { ...sale, state: 'problem', problem: e.message, tries: sale.tries + 1 }
          await tx('sales', 'readwrite', (s) => s.put(marked))
        }
      }
    } finally {
      await refreshWaiting()
      syncing.value = false
      running = null
    }
  })()
  return running
}

/** Puts a sale marked as a problem back in line, after the cause is fixed. */
export async function tryAgain(id: string) {
  const sale = (await allSales()).find((s) => s.id === id)
  if (!sale) return
  await tx('sales', 'readwrite', (s) => s.put({ ...sale, state: 'waiting', problem: '' }))
  await refreshWaiting()
  await syncNow()
}

/**
 * Removes a problem sale once a manager has entered it by hand. Only for a
 * sale the server has refused; a waiting sale cannot be removed here.
 */
export async function setAside(id: string) {
  const sale = (await allSales()).find((s) => s.id === id)
  if (!sale || sale.state !== 'problem') return
  await tx('sales', 'readwrite', (s) => s.delete(id))
  await refreshWaiting()
}

let currentUserId = ''
let timer: number | null = null
let listening = false

// Listening starts as soon as this file loads, before anyone is signed in:
// the very first request (checking the saved sign-in) may be the one that
// finds the server gone, and that must not be missed.
function listen() {
  if (listening || typeof window === 'undefined') return
  listening = true
  // The API client says when a request failed to reach the server, or got
  // through after failing. The browser's own online/offline events only
  // know about the network card, not whether the server answers, so they
  // only start a check.
  window.addEventListener('gb-reachable', (e) => markReachable((e as CustomEvent<boolean>).detail))
  window.addEventListener('online', () => api.health().then(() => markReachable(true), () => undefined))
  window.addEventListener('offline', () => markReachable(false))
}
listen()

/** Starts the background sending for the person signed in. */
export function startOffline(userId: string) {
  currentUserId = userId
  refreshWaiting()
  listen()
  if (timer === null) {
    timer = window.setInterval(() => {
      if (reachable.value && waiting.value.some((s) => s.user_id === currentUserId && s.state === 'waiting')) {
        syncNow().catch(() => undefined)
      }
    }, 30_000)
  }
  if (reachable.value) syncNow().catch(() => undefined)
}

export function stopOffline() {
  currentUserId = ''
}
