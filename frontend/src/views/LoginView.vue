<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { session } from '../stores/session'
import { ApiError } from '../services/api'

const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    const result = await session.signIn(email.value, password.value)
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
      <div class="brand">
        <span class="mark" aria-hidden="true">GB</span>
        <div>
          <b>The Green Buffet</b>
          <span>Management system</span>
        </div>
      </div>

      <h1>Sign in</h1>

      <label for="email">Email</label>
      <input id="email" v-model="email" type="email" autocomplete="username" required />

      <label for="password">Password</label>
      <input id="password" v-model="password" type="password" autocomplete="current-password" required />

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <button :disabled="busy">{{ busy ? 'Signing in…' : 'Sign in' }}</button>

      <p class="hint">
        Trouble signing in? Ask the owner or an administrator to reset your account.
      </p>
    </form>
  </div>
</template>

<style scoped>
.screen {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1.5rem;
  background: radial-gradient(circle at 18% 12%, #c5e5c0 0, transparent 46%), #f7f5ef;
}
.card {
  width: min(400px, 100%);
  background: #fff;
  border-radius: 20px;
  padding: 1.75rem;
  box-shadow: 0 1px 2px rgba(20, 50, 25, 0.06), 0 18px 40px -22px rgba(20, 50, 25, 0.45);
  display: grid;
  gap: 0.5rem;
}
.brand { display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.5rem; }
.mark {
  width: 44px; height: 44px; border-radius: 13px; background: #0b3b1d; color: #9cdb5a;
  display: grid; place-items: center; font-weight: 800; font-family: var(--display);
}
.brand div { display: grid; line-height: 1.2; }
.brand span:last-child { font-size: 0.8rem; color: #5d665e; }
h1 { font-size: 1.5rem; margin: 0.4rem 0 0.6rem; color: #18201a; }
label { font-weight: 700; font-size: 0.9rem; }
input {
  min-height: 46px; padding: 0.6rem 0.8rem; border-radius: 10px;
  border: 1.5px solid #e1e5dc; font: inherit; margin-bottom: 0.3rem;
}
input:focus { outline: none; border-color: #1f8a3b; box-shadow: 0 0 0 3px rgba(31, 138, 59, 0.22); }
button {
  min-height: 48px; margin-top: 0.6rem; border: 0; border-radius: 999px;
  background: #1f8a3b; color: #fff; font-weight: 700; font-size: 1rem; cursor: pointer;
}
button:disabled { opacity: 0.6; cursor: not-allowed; }
.error { background: #fbe9e7; color: #b3261e; padding: 0.6rem 0.8rem; border-radius: 10px; font-size: 0.92rem; }
.hint { font-size: 0.82rem; color: #5d665e; margin-top: 0.4rem; }
</style>
