import { computed, ref } from 'vue'
import { api, setToken, getToken, type User } from '../services/api'

const EXPIRY_KEY = 'gb-token-expires'

const user = ref<User | null>(null)
const permissions = ref<string[]>([])
const ready = ref(false)
const expiresAt = ref<number | null>(null)

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

export const session = {
  user,
  permissions,
  ready,
  expiresAt,
  signedIn: computed(() => !!user.value),
  can: (code: string) => permissions.value.includes(code),
  canAny: (...codes: string[]) => codes.some((c) => permissions.value.includes(c)),

  async signIn(email: string, password: string) {
    const result = await api.login(email, password)
    setToken(result.token)
    writeExpiry(result.expires_at)
    user.value = result.user
    permissions.value = result.permissions
    return result
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

  signOut() {
    setToken(null)
    writeExpiry(null)
    user.value = null
    permissions.value = []
  },
}
