<!--
  A manager approves on the spot: they step up to the till and type their own
  email and password. The server checks they may approve it and are not the
  person asking. Nothing typed here is kept on this screen afterwards.
-->
<script setup lang="ts">
import { onMounted, reactive } from 'vue'

const props = defineProps<{ what: string; error?: string }>()
const emit = defineEmits<{ approve: [approval: { email: string; password: string }]; cancel: [] }>()
const form = reactive({ email: '', password: '' })

function submit() {
  if (!form.email.trim() || !form.password) return
  emit('approve', { email: form.email.trim(), password: form.password })
  form.password = ''
}

onMounted(() => window.setTimeout(() => document.getElementById('approve-email')?.focus(), 0))
</script>

<template>
  <div class="veil" @click.self="emit('cancel')">
    <form class="box" @submit.prevent="submit">
      <b>Manager approval</b>
      <p class="muted">{{ props.what }} A manager types their own email and password to approve it.</p>
      <label class="field">Manager's email
        <input id="approve-email" v-model="form.email" type="email" autocomplete="off" />
      </label>
      <label class="field">Password
        <input v-model="form.password" type="password" autocomplete="off" />
      </label>
      <p v-if="props.error" class="error">{{ props.error }}</p>
      <div class="row">
        <button class="btn-primary" type="submit">Approve</button>
        <button class="btn-quiet" type="button" @click="emit('cancel')">Cancel</button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.veil { position: fixed; inset: 0; background: rgba(0, 0, 0, .45); display: grid; place-items: center; z-index: 60; padding: 1rem; }
.box { background: var(--paper); color: var(--ink); border: 1px solid var(--line); border-radius: 16px; padding: 1.3rem; width: min(380px, 100%); display: grid; gap: .6rem; box-shadow: var(--shadow); }
.box p { margin: 0; }
.row { display: flex; gap: .6rem; flex-wrap: wrap; }
</style>
