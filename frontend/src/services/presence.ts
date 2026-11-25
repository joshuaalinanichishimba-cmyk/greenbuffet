/**
 * The heartbeat: how the team directory knows who is really connected.
 *
 * Every 30 seconds an open screen tells the server two things: it is still
 * there, and whether anyone has touched it since last time. Nothing about
 * what was typed, clicked or shown is sent. As the page closes it says so.
 *
 * When the heartbeat fails (network down, load shedding), the screen shows
 * a "reconnecting" strip and keeps trying; work on screen is not thrown away.
 *
 * It also runs the inactivity lock for shared counter computers: after the
 * minutes set in Settings with nobody touching the screen, it locks. The
 * kitchen display never locks itself: it is a board people read, not touch.
 */
import { api, getToken } from './api'
import { session } from '../stores/session'

const BEAT_MS = 30_000
let timer: number | undefined
let touched = true
let lastTouch = Date.now()
let lockMinutes = 10
let currentPath = () => window.location.pathname

function onTouch() {
  touched = true
  lastTouch = Date.now()
}

const EVENTS = ['pointerdown', 'keydown', 'touchstart', 'wheel'] as const

async function beat() {
  if (!getToken() || !session.signedIn.value) return
  const active = touched
  touched = false
  try {
    const result = await api.post<{ tracked: boolean; locked: boolean; unread: number; lock_minutes: number }>(
      '/presence/heartbeat', { active },
    )
    session.connected.value = true
    session.unread.value = result.unread
    lockMinutes = result.lock_minutes
    if (result.locked) session.locked.value = true
  } catch (e) {
    const status = (e as { status?: number }).status
    // 0 = the server could not be reached at all.
    session.connected.value = status !== 0
    touched = touched || active
  }
  maybeLock()
}

function maybeLock() {
  if (session.locked.value || !lockMinutes || !session.signedIn.value) return
  const path = currentPath()
  if (path.startsWith('/kitchen') || path.startsWith('/login') || path.startsWith('/change-password')) return
  if (Date.now() - lastTouch >= lockMinutes * 60_000) lockNow()
}

export async function lockNow() {
  session.locked.value = true
  try {
    await api.post('/auth/lock')
  } catch {
    /* offline: the screen is covered anyway, and unlocking needs the server */
  }
}

function onHide() {
  if (!getToken()) return
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
  // keepalive lets the request finish after the page has gone.
  fetch(`${base}/presence/heartbeat`, {
    method: 'POST',
    keepalive: true,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ closing: true }),
  }).catch(() => undefined)
}

function onShow() {
  if (document.visibilityState === 'visible') {
    touched = true
    beat()
  }
}

export function startPresence(path: () => string) {
  currentPath = path
  stopPresence()
  for (const e of EVENTS) window.addEventListener(e, onTouch, { passive: true })
  window.addEventListener('pagehide', onHide)
  document.addEventListener('visibilitychange', onShow)
  window.addEventListener('online', onShow)
  lastTouch = Date.now()
  touched = true
  beat()
  timer = window.setInterval(beat, BEAT_MS)
}

export function stopPresence() {
  window.clearInterval(timer)
  for (const e of EVENTS) window.removeEventListener(e, onTouch)
  window.removeEventListener('pagehide', onHide)
  document.removeEventListener('visibilitychange', onShow)
  window.removeEventListener('online', onShow)
}

/** A short "5 min ago" for last-active times. */
export function ago(iso: string | null | undefined): string {
  if (!iso) return 'Never'
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`
  return new Date(iso).toLocaleDateString('en-ZM', { day: 'numeric', month: 'short' })
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-ZM', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
