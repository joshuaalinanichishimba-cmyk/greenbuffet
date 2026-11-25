<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import LockScreen from './components/LockScreen.vue'
import { startPresence, stopPresence } from './services/presence'
import { session } from './stores/session'

const router = useRouter()

// The API client raises this when a token is rejected, so an expired shift
// lands on the sign-in page instead of a screen full of failed requests.
function onSessionEnded() {
  session.signOut()
  if (router.currentRoute.value.path !== '/login') router.replace('/login')
}
// The server says this screen is locked (another tab locked it, or the
// inactivity timer ran out while a request was on its way).
function onLocked() {
  session.locked.value = true
}
// An owner without two-step sign-in: straight to setting it up.
function onTwoStep() {
  if (session.user.value) session.user.value = { ...session.user.value, two_step_required: true }
  if (!router.currentRoute.value.path.startsWith('/profile/security')) router.replace('/profile/security')
}

// The heartbeat runs whenever someone is signed in.
watch(() => session.signedIn.value, (on) => {
  if (on) startPresence(() => router.currentRoute.value.path)
  else stopPresence()
}, { immediate: true })

onMounted(() => {
  window.addEventListener('gb-session-ended', onSessionEnded)
  window.addEventListener('gb-locked', onLocked)
  window.addEventListener('gb-two-step', onTwoStep)
})
onUnmounted(() => {
  window.removeEventListener('gb-session-ended', onSessionEnded)
  window.removeEventListener('gb-locked', onLocked)
  window.removeEventListener('gb-two-step', onTwoStep)
  stopPresence()
})
</script>

<template>
  <RouterView />
  <LockScreen />
</template>
