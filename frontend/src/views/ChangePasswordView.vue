<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError } from '../services/api'
import { session, takeSignInPassword } from '../stores/session'
import logo from '../assets/logo-full.png'

const router = useRouter()
const current = ref('')
const next = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)
const filled = ref(false)

onMounted(() => {
  current.value = takeSignInPassword()
  filled.value = !!current.value
  window.setTimeout(() => document.getElementById(filled.value ? 'new' : 'cur')?.focus(), 0)
})

async function submit() {
  error.value = ''
  if (next.value !== confirm.value) {
    error.value = 'The two new passwords do not match.'
    return
  }
  if (next.value.length < 10) {
    error.value = 'Use at least 10 characters.'
    return
  }
  busy.value = true
  try {
    const result = await api.changePassword(current.value, next.value)
    // Changing the password ends every other session; this one carries on
    // with the fresh token.
    session.adoptToken(result.token, result.expires_at)
    if (session.user.value) session.user.value.must_change_password = false
    router.replace('/')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Something went wrong.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="screen">
    <form class="card" @submit.prevent="submit">
      <img :src="logo" alt="The Green Buffet" class="logo" width="140" height="48" />
      <h1>Choose a new password</h1>
      <p class="lead">Your account was created with a temporary password. Set your own now.</p>

      <template v-if="!filled">
        <label for="cur">Current password</label>
        <input id="cur" v-model="current" type="password" autocomplete="current-password" required />
      </template>

      <label for="new">New password</label>
      <input id="new" v-model="next" type="password" autocomplete="new-password" required />

      <label for="con">Repeat new password</label>
      <input id="con" v-model="confirm" type="password" autocomplete="new-password" required />

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p class="hint">At least 10 characters. A short sentence you will remember works well; not your name or email.</p>
      <button :disabled="busy">{{ busy ? 'Saving…' : 'Save password' }}</button>
    </form>
  </div>
</template>

<style scoped>
.screen { min-height: 100vh; display: grid; place-items: center; padding: 1.5rem 1rem; background: radial-gradient(circle at 18% 12%, var(--leaf) 0, transparent 46%), var(--cream); }
.card { width: min(420px, 100%); background: var(--paper); color: var(--ink); border: 1px solid var(--line); border-radius: 20px; padding: 1.75rem; display: grid; gap: 0.45rem; box-shadow: var(--shadow); }
.logo { width: 156px; height: auto; margin-bottom: .2rem; box-sizing: border-box; background: #F7F5EF; padding: 6px 8px; border-radius: 12px; }
/* The logo's brown lettering needs a light plate to show on the dark theme. */
h1 { font-size: 1.6rem; font-weight: 900; margin: .2rem 0 0; color: var(--brown); letter-spacing: -.02em; }
.lead { color: var(--muted); font-size: 0.95rem; margin: 0 0 0.6rem; }
label { font-weight: 700; font-size: 0.9rem; color: var(--ink); }
input { min-height: 46px; padding: 0.6rem 0.8rem; border-radius: 10px; border: 1.5px solid var(--line); background: var(--paper); color: var(--ink); font: inherit; }
input:focus { outline: none; border-color: var(--green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 25%, transparent); }
button { min-height: 48px; margin-top: 0.7rem; border: 0; border-radius: 999px; background: var(--green); color: var(--green-ink); font-weight: 700; font-size: 1rem; cursor: pointer; }
button:disabled { opacity: .6; }
.error { background: var(--danger-soft); color: var(--danger); padding: 0.6rem 0.8rem; border-radius: 10px; font-size: 0.92rem; margin: 0; }
.hint { color: var(--muted); font-size: .85rem; margin: .2rem 0 0; }
</style>
