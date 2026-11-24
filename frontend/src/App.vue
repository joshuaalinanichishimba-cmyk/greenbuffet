<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { session } from './stores/session'

const router = useRouter()

// The API client raises this when a token is rejected, so an expired shift
// lands on the sign-in page instead of a screen full of failed requests.
function onSessionEnded() {
  session.signOut()
  if (router.currentRoute.value.path !== '/login') router.replace('/login')
}

onMounted(() => window.addEventListener('gb-session-ended', onSessionEnded))
onUnmounted(() => window.removeEventListener('gb-session-ended', onSessionEnded))
</script>

<template>
  <RouterView />
</template>
