<!--
  Staff sign in, laid out like the demo's: the logo, email and password, and
  below them the kinds of account, each with what it sees.

  In the demo those cards fill in a demo account. Here they say which kind of
  account you are signing in as, and the server checks that the account
  really is that kind, so a manager never lands on the counter's screens by
  mistake. The last choice is remembered on this computer: the till PC
  usually signs in cashiers, the office PC the accountant.
-->
<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { session } from '../stores/session'
import { api, ApiError } from '../services/api'
import logo from '../assets/logo-full.png'

const ROLE_KEY = 'gb-sign-in-role'

const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
interface Account { name: string; email: string; password?: string }
interface Kind { id: string; label: string; sees: string; accounts: Account[] }
const roles = ref<Kind[]>([])
const roleId = ref('')

const chosen = computed(() => roles.value.find((r) => r.id === roleId.value) ?? null)
// Test mode (scripts\test-sign-in.ps1): passwords come filled in.
const testMode = computed(() => roles.value.some((r) => r.accounts.some((a) => a.password)))

function remember(id: string) {
  try {
    localStorage.setItem(ROLE_KEY, id)
  } catch {
    /* private window */
  }
}

// One tap, like the demo's account cards: a kind with one account fills its
// email straight in; a kind with several shows their names to choose from.
function pick(kind: Kind) {
  roleId.value = kind.id
  error.value = ''
  remember(kind.id)
  if (kind.accounts.length === 1) choosePerson(kind.accounts[0])
  else if (!kind.accounts.length) {
    email.value = ''
    focus('email')
  }
}

function choosePerson(account: Account) {
  email.value = account.email
  password.value = account.password ?? ''
  // The cursor waits in the password box: type it, or in test mode just
  // press Enter.
  focus('password')
}

function focus(id: string) {
  window.setTimeout(() => document.getElementById(id)?.focus(), 0)
}

// The online demo says so, instead of the "switch test mode off" warning.
const demo = ref(false)

onMounted(async () => {
  api.get<{ environment?: string }>('/health').then((h) => { demo.value = h.environment === 'demo' }).catch(() => undefined)
  try {
    roles.value = await api.signInRoles()
    let saved = ''
    try {
      saved = localStorage.getItem(ROLE_KEY) ?? ''
    } catch {
      /* private window */
    }
    const kind = roles.value.find((r) => r.id === saved)
    if (kind) {
      roleId.value = kind.id
      if (kind.accounts.length === 1) choosePerson(kind.accounts[0])
    }
  } catch {
    // Without the list, sign-in still works: the role is simply not checked.
    roles.value = []
  }
})

// Two-step sign-in: after the password, the six-digit code from the phone.
const ticket = ref('')
// How the second step is done: the authenticator app, or a code by email.
const codeBy = ref<'app' | 'email'>('app')
const sentTo = ref('')
const resendIn = ref(0)
let resendTimer: number | undefined
function startResendClock() {
  resendIn.value = 60
  window.clearInterval(resendTimer)
  resendTimer = window.setInterval(() => {
    resendIn.value = Math.max(0, resendIn.value - 1)
    if (!resendIn.value) window.clearInterval(resendTimer)
  }, 1000)
}
async function resend() {
  error.value = ''
  try {
    const r = await api.post<{ ticket: string; sent_to: string }>('/auth/login/resend', { ticket: ticket.value })
    ticket.value = r.ticket
    sentTo.value = r.sent_to
    code.value = ''
    startResendClock()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not send a new code.'
  }
}
const code = ref('')
const codeBox = ref<HTMLInputElement | null>(null)

async function submitCode() {
  error.value = ''
  busy.value = true
  try {
    const result = await session.signInCode(ticket.value, code.value.trim())
    remember(result.user.role_id)
    ticket.value = ''
    router.replace(result.user.must_change_password ? '/change-password' : '/')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Something went wrong. Try again.'
    code.value = ''
    if (e instanceof ApiError && e.message.includes('password again')) ticket.value = ''
  } finally {
    busy.value = false
  }
}

async function submit() {
  if (ticket.value) return submitCode()
  error.value = ''
  if (roles.value.length && !roleId.value) {
    error.value = 'Choose the kind of account you are signing in as.'
    return
  }
  busy.value = true
  try {
    const result = await session.signIn(email.value, password.value, roleId.value || undefined)
    if (result.needs_code) {
      ticket.value = result.ticket ?? ''
      codeBy.value = (result as { code_by?: string }).code_by === 'email' ? 'email' : 'app'
      sentTo.value = (result as { sent_to?: string }).sent_to ?? ''
      if (codeBy.value === 'email') startResendClock()
      code.value = ''
      busy.value = false
      await nextTick()
      codeBox.value?.focus()
      return
    }
    remember(result.user.role_id)
    router.replace(result.user.must_change_password ? '/change-password' : '/')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Something went wrong. Try again.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="screen">
    <form class="card" @submit.prevent="submit">
      <img :src="logo" alt="The Green Buffet" class="logo" width="140" height="48" />

      <h1>Staff sign in</h1>

      <p v-if="demo" class="test">
        <b>Online demo.</b> Everything here is made up: the staff, the orders and the money. Pick an account below,
        then press Sign in. Each kind of account sees its own screens.
      </p>
      <p v-else-if="testMode" class="test">
        <b>Test mode.</b> Tap your card and press Enter. Switch this off before real use.
      </p>

      <p v-if="chosen" class="as" aria-live="polite">
        Signing in as <b>{{ chosen.label }}</b>
        <button type="button" class="change" @click="roleId = ''">Change</button>
      </p>

      <template v-if="ticket">
        <p class="as">Two-step sign-in for <b>{{ email }}</b></p>
        <p v-if="codeBy === 'email'" class="hint">We emailed a six-digit code to <b>{{ sentTo }}</b>. It works for 5 minutes.
          Nobody at the restaurant will ever ask you for it.</p>
        <label for="code">{{ codeBy === 'email' ? 'Code from the email' : 'Code from your authenticator app' }}</label>
        <input id="code" ref="codeBox" v-model="code" inputmode="numeric" autocomplete="one-time-code"
               maxlength="9" placeholder="123456" required class="code" />
        <p class="hint">{{ codeBy === 'email' ? 'No email? Check spam, or type one of your recovery codes.' : 'Lost your phone? Type one of your recovery codes instead.' }}</p>
        <button v-if="codeBy === 'email'" type="button" class="change" :disabled="resendIn > 0" @click="resend">
          {{ resendIn > 0 ? `Send a new code in ${resendIn} s` : 'Send a new code' }}
        </button>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="go" :disabled="busy || code.trim().length < 6">{{ busy ? 'Checking…' : 'Sign in' }}</button>
        <button type="button" class="change" @click="ticket = ''; code = ''; error = ''">Back</button>
      </template>
      <template v-else>
      <label for="email">Email</label>
      <input id="email" v-model="email" type="email" autocomplete="username" required />

      <label for="password">Password</label>
      <input id="password" v-model="password" type="password" autocomplete="current-password" required />

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <button class="go" :disabled="busy">
        {{ busy ? 'Signing in…' : chosen ? `Sign in as ${chosen.label}` : 'Sign in' }}
      </button>
      <RouterLink to="/forgot-password" class="forgot">Forgot your password?</RouterLink>
      </template>

      <template v-if="roles.length && !ticket">
        <hr />
        <p class="label" id="kinds">I am signing in as</p>
        <div class="kinds" role="radiogroup" aria-labelledby="kinds">
          <div v-for="r in roles" :key="r.id" class="kind-wrap" :class="{ on: r.id === roleId }">
            <button
              type="button"
              role="radio"
              class="kind"
              :aria-checked="r.id === roleId"
              @click="pick(r)"
            >
              <b>{{ r.label }}</b>
              <span>{{ r.sees }}</span>
              <small v-if="r.accounts.length === 1" class="who">{{ r.accounts[0].name }} · {{ r.accounts[0].email }}</small>
              <small v-else-if="!r.accounts.length" class="who none">No account yet. Ask the owner to make one.</small>
            </button>
            <div v-if="r.id === roleId && r.accounts.length > 1" class="people">
              <button
                v-for="a in r.accounts"
                :key="a.email"
                type="button"
                class="person"
                :class="{ on: email === a.email }"
                @click="choosePerson(a)"
              >{{ a.name }}</button>
            </div>
          </div>
        </div>
        <p class="hint">
          Tap your card and your email is filled in; type your password and sign in. Each kind of
          account only sees what it is allowed to, and the server checks your account really is the
          kind you chose.
        </p>
      </template>

      <p class="hint">
        Trouble signing in? Use "Forgot your password?", or ask an owner or manager.
      </p>
    </form>
  </div>
</template>

<style scoped>
.screen {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1.5rem 1rem;
  background: radial-gradient(circle at 18% 12%, var(--leaf) 0, transparent 46%), var(--cream);
}
.card {
  width: min(440px, 100%);
  background: var(--paper);
  border-radius: 20px;
  padding: 1.75rem;
  box-shadow: 0 1px 2px rgba(20, 50, 25, 0.06), 0 18px 40px -22px rgba(20, 50, 25, 0.45);
  display: grid;
  gap: 0.5rem;
}
.logo { width: 156px; height: auto; margin-bottom: .2rem; box-sizing: border-box; background: #F7F5EF; padding: 6px 8px; border-radius: 12px; }
/* The logo's brown lettering needs a light plate to show on the dark theme. */
h1 { font-size: 1.75rem; font-weight: 900; margin: 0.4rem 0 0.2rem; color: var(--brown); letter-spacing: -.02em; }
label { font-weight: 700; font-size: 0.9rem; }
input {
  min-height: 46px; padding: 0.6rem 0.8rem; border-radius: 10px;
  border: 1.5px solid var(--line); font: inherit; margin-bottom: 0.3rem;
  background: var(--paper); color: var(--ink);
}
input:focus { outline: none; border-color: var(--green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 25%, transparent); }
.go {
  min-height: 48px; margin-top: 0.6rem; border: 0; border-radius: 999px;
  background: var(--green); color: var(--green-ink); font-weight: 700; font-size: 1rem; cursor: pointer;
}
.go:disabled { opacity: 0.6; cursor: not-allowed; }

.as {
  display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; margin: 0 0 .4rem;
  padding: .55rem .8rem; border-radius: 10px; font-size: .95rem;
  background: var(--leaf-soft); color: var(--green-deep);
}
.change { margin-left: auto; background: none; border: 0; padding: 0; font: inherit; font-weight: 700; color: var(--green-deep); text-decoration: underline; cursor: pointer; }

hr { border: 0; border-top: 1px solid var(--line); margin: 1rem 0 .4rem; width: 100%; }
.label { font-weight: 700; margin: 0 0 .2rem; }
.test { margin: 0 0 .3rem; padding: .55rem .8rem; border-radius: 10px; background: var(--warn-soft); color: var(--warn); font-size: .9rem; }
.kinds { display: grid; gap: .5rem; }
.kind-wrap { border: 1.5px solid var(--line); border-radius: 12px; background: var(--paper); overflow: hidden; }
.kind-wrap:hover { border-color: color-mix(in srgb, var(--green) 50%, var(--line)); }
.kind-wrap.on { border-color: var(--green); background: color-mix(in srgb, var(--leaf-soft) 60%, var(--paper)); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 18%, transparent); }
.kind {
  width: 100%; border: 0 !important; background: none !important;
  display: grid; gap: .15rem; text-align: left; padding: .75rem .9rem; border-radius: 12px;
  border: 1.5px solid var(--line); background: var(--paper); color: var(--ink); font: inherit; cursor: pointer;
}
.kind b { font-size: 1rem; }
.kind span { color: var(--muted); font-size: .9rem; }
.who { color: var(--green-deep); font-weight: 600; font-size: .82rem; overflow-wrap: anywhere; }
.who.none { color: var(--muted); font-weight: 400; }
.people { display: flex; flex-wrap: wrap; gap: .4rem; padding: 0 .9rem .8rem; }
.person { border: 1.5px solid var(--line); background: var(--paper); color: var(--ink); border-radius: 999px; padding: .35rem .8rem; font: inherit; font-weight: 600; font-size: .9rem; cursor: pointer; }
.person.on { border-color: var(--green); background: var(--green); color: var(--green-ink); }
.kind:focus-visible { outline: 3px solid color-mix(in srgb, var(--green) 45%, transparent); outline-offset: 2px; }

.error { background: color-mix(in srgb, var(--danger) 12%, var(--paper)); color: var(--danger); padding: 0.6rem 0.8rem; border-radius: 10px; font-size: 0.92rem; margin: 0; }
.hint { font-size: 0.85rem; color: var(--muted); margin: 0.3rem 0 0; }
.code { letter-spacing: .3em; font-weight: 800; font-size: 1.3rem; text-align: center; }
.forgot { display: block; text-align: center; margin-top: .6rem; font-size: .9rem; color: var(--green-deep); font-weight: 700; }
</style>
