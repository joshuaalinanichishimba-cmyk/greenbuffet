<!--
  Forgot password, and the page the emailed link opens.

  /forgot-password asks for the email and always gives the same answer, so
  it cannot be used to find out who works here. /reset-password?token=...
  sets the new password; the link works once, for 30 minutes, and signs out
  every device that was signed in.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, api } from '../services/api'
import logo from '../assets/logo-full.png'

const route = useRoute()
const router = useRouter()
const token = computed(() => (route.query.token as string) || '')
const email = ref('')
const next = ref('')
const again = ref('')
const busy = ref(false)
const error = ref('')
const done = ref('')

async function ask() {
  busy.value = true
  error.value = ''
  try {
    const r = await api.post<{ message: string }>('/auth/password/forgot', { email: email.value })
    done.value = r.message
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Something went wrong. Try again.'
  } finally {
    busy.value = false
  }
}

async function reset() {
  error.value = ''
  if (next.value !== again.value) {
    error.value = 'The two passwords are not the same.'
    return
  }
  if (next.value.length < 10) {
    error.value = 'Use at least 10 characters. A short sentence you will remember works well.'
    return
  }
  busy.value = true
  try {
    await api.post('/auth/password/reset', { token: token.value, new_password: next.value })
    done.value = 'Your password is changed and every device was signed out. Sign in with the new one.'
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Something went wrong. Try again.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="screen">
    <div class="card">
      <img :src="logo" alt="The Green Buffet" class="logo" width="140" height="48" />
      <template v-if="done">
        <h1>{{ token ? 'Password changed' : 'Check your email' }}</h1>
        <p>{{ done }}</p>
        <button @click="router.replace('/login')">Back to sign in</button>
      </template>
      <form v-else-if="!token" @submit.prevent="ask">
        <h1>Forgot your password</h1>
        <p class="hint">Type the email you sign in with. If it is confirmed on your account, a link to set a new
          password arrives in a minute or two.</p>
        <label for="em">Email</label>
        <input id="em" v-model="email" type="email" autocomplete="username" required />
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button :disabled="busy">{{ busy ? 'Sending…' : 'Send the link' }}</button>
        <RouterLink to="/login" class="back">Back to sign in</RouterLink>
      </form>
      <form v-else @submit.prevent="reset">
        <h1>Choose a new password</h1>
        <label for="np">New password</label>
        <input id="np" v-model="next" type="password" autocomplete="new-password" required />
        <label for="np2">The same again</label>
        <input id="np2" v-model="again" type="password" autocomplete="new-password" required />
        <p class="hint">At least 10 characters. Not your name or email, and not one you use elsewhere.</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button :disabled="busy">{{ busy ? 'Saving…' : 'Save the new password' }}</button>
      </form>
    </div>
  </main>
</template>

<style scoped>
.screen { min-height: 100vh; display: grid; place-items: center; padding: 1.5rem 1rem; background: radial-gradient(circle at 18% 12%, var(--leaf) 0, transparent 46%), var(--cream); }
.card { width: min(420px, 100%); background: var(--paper); color: var(--ink); border: 1px solid var(--line); border-radius: 20px; padding: 1.75rem; display: grid; gap: 0.45rem; box-shadow: var(--shadow); }
form { display: grid; gap: .45rem; }
.logo { width: 156px; height: auto; margin-bottom: .2rem; box-sizing: border-box; background: #F7F5EF; padding: 6px 8px; border-radius: 12px; }
h1 { font-size: 1.5rem; font-weight: 900; margin: .2rem 0 0; color: var(--brown); letter-spacing: -.02em; }
label { font-weight: 700; font-size: 0.9rem; color: var(--ink); margin-top: .3rem; }
input { min-height: 46px; padding: 0.6rem 0.8rem; border-radius: 10px; border: 1.5px solid var(--line); background: var(--paper); color: var(--ink); font: inherit; }
button { min-height: 48px; margin-top: 0.7rem; border: 0; border-radius: 999px; background: var(--green); color: var(--green-ink); font-weight: 700; font-size: 1rem; cursor: pointer; }
button[disabled] { opacity: .6; }
.hint { color: var(--muted); font-size: .9rem; margin: 0; }
.error { color: var(--danger); font-weight: 600; margin: 0; }
.back { text-align: center; margin-top: .5rem; color: var(--green-deep); font-weight: 700; font-size: .9rem; }
</style>
