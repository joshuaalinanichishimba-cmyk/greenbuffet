import { computed, ref } from 'vue'
import { api, setToken, getToken, type LoginResult, type User } from '../services/api'

const EXPIRY_KEY = 'gb-token-expires'

const user = ref<User | null>(null)
const permissions = ref<string[]>([])
const ready = ref(false)
const expiresAt = ref<number | null>(null)
// The screen is locked: the server refuses work until the same person unlocks.
const locked = ref(false)
// Unread notices, kept fresh by the heartbeat.
const unread = ref(0)
// false while the server cannot be reached (network down, load shedding).
const connected = ref(true)

function readExpiry(): number | null {
  try {
    const raw = localStorage.getItem(EXPIRY_KEY)
    return raw ? Number(raw) : null
  } catch {
    return null
  }
}

function writeExpiry(iso: string | null) {
  const value = iso ? new Date(iso).getTime() : null
  expiresAt.value = value
  try {
    value ? localStorage.setItem(EXPIRY_KEY, String(value)) : localStorage.removeItem(EXPIRY_KEY)
  } catch {
    /* private browsing */
  }
}

let justTyped = ''

/** The password just used to sign in, once, then forgotten. */
export function takeSignInPassword(): string {
  const value = justTyped
  justTyped = ''
  return value
}

export const session = {
  adoptToken(token: string, expiresAt: string) {
    setToken(token)
    writeExpiry(expiresAt)
  },
  user,
  permissions,
  ready,
  expiresAt,
  locked,
  unread,
  connected,
  signedIn: computed(() => !!user.value),
  can: (code: string) => permissions.value.includes(code),
  canAny: (...codes: string[]) => codes.some((c) => permissions.value.includes(c)),

  async signIn(email: string, password: string, roleId?: string) {
    const result = await api.login(email, password, roleId)
    // Held in memory only, for one use: when a temporary password must be
    // changed straight away, the "current password" box is already filled.
    justTyped = result.user.must_change_password ? password : ''
    // Two-step sign-in: the caller asks for the code and finishes with signInCode.
    if (result.needs_code) return result
    session.accept(result)
    return result
  },

  async signInCode(ticket: string, code: string) {
    const result = await api.loginCode(ticket, code)
    session.accept(result)
    return result
  },

  accept(result: LoginResult) {
    locked.value = false
    setToken(result.token)
    writeExpiry(result.expires_at)
    user.value = result.user
    permissions.value = result.permissions
  },

  async restore() {
    if (!getToken()) {
      ready.value = true
      return
    }
    const expiry = readExpiry()
    if (expiry && expiry <= Date.now()) {
      // Expired while the tab was closed: clear it rather than firing a doomed request.
      session.signOut()
      ready.value = true
      return
    }
    try {
      const result = await api.me()
      user.value = result.user
      permissions.value = result.permissions
      expiresAt.value = expiry
    } catch {
      setToken(null)
      writeExpiry(null)
    } finally {
      ready.value = true
    }
  },

  /** Keeps the signed-in details in step after the user edits their own account. */
  update(next: User) {
    user.value = next
  },

  /** Ends this device's session on the server too (best effort), then here. */
  async signOutEverywhere(handOver = false) {
    try {
      if (getToken()) await api.logout(handOver)
    } catch {
      /* already ended, or offline: the token is dropped here either way */
    }
    session.signOut()
  },

  signOut() {
    locked.value = false
    unread.value = 0
    setToken(null)
    writeExpiry(null)
    user.value = null
    permissions.value = []
  },
}
