<!--
  The lock screen for shared counter computers.

  It covers whatever was on screen without closing it, so an order half-way
  through on the till is still there after unlocking. The server refuses the
  locked session's requests too, so the cover cannot be got round by poking
  at the page.

  Only the person who locked it can unlock it, with their own password.
  Anyone else taps "Switch person": this session is signed out (its till
  basket is kept for its owner), and they sign in as themselves, so every
  sale is in the name of whoever made it.
-->
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Avatar from './Avatar.vue'
import { ApiError, api } from '../services/api'
import { session } from '../stores/session'

const router = useRouter()
const password = ref('')
const error = ref('')
const busy = ref(false)
const box = ref<HTMLInputElement | null>(null)

watch(() => session.locked.value, async (on) => {
  if (on) {
    password.value = ''
    error.value = ''
    await nextTick()
    box.value?.focus()
  }
}, { immediate: true })

async function unlock() {
  if (!password.value) return
  busy.value = true
  error.value = ''
  try {
    await api.post('/auth/unlock', { password: password.value })
    session.locked.value = false
    password.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not unlock.'
    password.value = ''
    if (e instanceof ApiError && e.status === 409) await switchPerson()
  } finally {
    busy.value = false
  }
}

async function switchPerson() {
  await session.signOutEverywhere(true)
  router.replace('/login')
}
</script>

<template>
  <div v-if="session.locked.value && session.user.value" class="lock" role="dialog" aria-modal="true" aria-label="Screen locked">
    <form class="card" @submit.prevent="unlock">
      <Avatar :user-id="session.user.value.id" :name="session.user.value.name" :photo-id="session.user.value.photo_id" :size="76" status="away" />
      <h2>{{ session.user.value.name }}</h2>
      <p class="muted">{{ session.user.value.role_label }} · screen locked</p>
      <label class="sr" for="lock-pw">Password</label>
      <input id="lock-pw" ref="box" v-model="password" class="input" type="password" autocomplete="current-password"
             placeholder="Your password" :disabled="busy" />
      <p v-if="error" class="error">{{ error }}</p>
      <button class="btn btn-primary btn-block" :disabled="busy || !password">{{ busy ? 'Checking…' : 'Unlock' }}</button>
      <button type="button" class="btn btn-ghost btn-block" :disabled="busy" @click="switchPerson">
        Not {{ session.user.value.name.split(' ')[0] }}? Switch person
      </button>
      <p class="hint muted small">What was on screen is kept. Switching person signs this account out here;
        anything left in the till basket waits for {{ session.user.value.name.split(' ')[0] }}.</p>
    </form>
  </div>
</template>

<style scoped>
.lock {
  position: fixed; inset: 0; z-index: 200; display: grid; place-items: center; padding: 16px;
  background: color-mix(in srgb, var(--forest) 88%, transparent); backdrop-filter: blur(6px);
}
.card {
  width: min(380px, 100%); background: var(--paper); border-radius: 20px; padding: 2rem 1.5rem 1.5rem;
  display: grid; justify-items: center; gap: .75rem; text-align: center; box-shadow: var(--shadow);
}
h2 { font-size: 1.35rem; margin-top: .25rem; }
.card .input, .card .btn { width: 100%; }
.error { color: var(--danger); font-weight: 600; }
.hint { line-height: 1.4; }
</style>
