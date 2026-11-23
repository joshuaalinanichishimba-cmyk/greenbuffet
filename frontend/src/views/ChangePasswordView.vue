<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError } from '../services/api'
import { session } from '../stores/session'

const router = useRouter()
const current = ref('')
const next = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  if (next.value !== confirm.value) {
    error.value = 'The two new passwords do not match.'
    return
  }
  if (next.value.length < 8) {
    error.value = 'Use at least 8 characters.'
    return
  }
  busy.value = true
  try {
    await api.changePassword(current.value, next.value)
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
      <h1>Choose a new password</h1>
      <p class="lead">Your account was created with a temporary password. Set your own now.</p>

      <label for="cur">Current password</label>
      <input id="cur" v-model="current" type="password" autocomplete="current-password" required />

      <label for="new">New password</label>
      <input id="new" v-model="next" type="password" autocomplete="new-password" required />

      <label for="con">Repeat new password</label>
      <input id="con" v-model="confirm" type="password" autocomplete="new-password" required />

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button :disabled="busy">{{ busy ? 'Saving…' : 'Save password' }}</button>
    </form>
  </div>
</template>

<style scoped>
.screen { min-height: 100vh; display: grid; place-items: center; padding: 1.5rem; background: #f7f5ef; }
.card { width: min(400px, 100%); background: #fff; border-radius: 20px; padding: 1.75rem; display: grid; gap: 0.45rem; box-shadow: 0 18px 40px -22px rgba(20, 50, 25, 0.45); }
h1 { font-size: 1.4rem; margin: 0; }
.lead { color: #5d665e; font-size: 0.92rem; margin-bottom: 0.6rem; }
label { font-weight: 700; font-size: 0.9rem; }
input { min-height: 46px; padding: 0.6rem 0.8rem; border-radius: 10px; border: 1.5px solid #e1e5dc; font: inherit; }
input:focus { outline: none; border-color: #1f8a3b; box-shadow: 0 0 0 3px rgba(31, 138, 59, 0.22); }
button { min-height: 48px; margin-top: 0.7rem; border: 0; border-radius: 999px; background: #1f8a3b; color: #fff; font-weight: 700; cursor: pointer; }
.error { background: #fbe9e7; color: #b3261e; padding: 0.6rem 0.8rem; border-radius: 10px; font-size: 0.92rem; }
</style>
