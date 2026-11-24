<!--
  Messages the system wanted to send a customer.

  There is no WhatsApp or SMS account yet, so nothing sends itself. Rather
  than pretend, the system writes down exactly what should go out, and this
  screen lets somebody copy it and send it from the restaurant phone in a few
  seconds - which is what they would have done anyway.

  On a phone, the WhatsApp button opens the chat with the message already
  typed, so it is two taps rather than copying by hand.
-->
<template>
  <AppShell>
    <h1>Messages</h1>
    <p class="lead">
      What the system would tell customers. Until a WhatsApp or SMS account is connected,
      send these from the restaurant phone and tick them off.
    </p>

    <div class="info-note">
      No messaging account is connected. Everything below is waiting for a person to send it.
      Connecting an account is an application to Airtel, MTN or a WhatsApp provider.
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <div class="tabs">
      <button :class="{ on: state === 'queued' }" @click="setState('queued')">Waiting</button>
      <button :class="{ on: state === 'sent' }" @click="setState('sent')">Sent</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="!messages.length" class="empty">
      {{ state === 'queued' ? 'Nothing waiting. Everything has been sent.' : 'Nothing sent yet.' }}
    </div>

    <div v-for="message in messages" :key="message.id" class="panel" style="margin-bottom: 0.7rem">
      <div class="spread">
        <div style="min-width: 0">
          <strong>{{ message.to_name || message.to_phone }}</strong>
          <span class="tag info" style="margin-left: 0.4rem">{{ message.about }}</span>
          <div class="muted">{{ message.to_phone }} · {{ at(message.at) }}</div>
        </div>
        <span v-if="message.status === 'sent'" class="tag">Sent {{ at(message.sent_at) }}</span>
      </div>
      <p style="margin: 0.7rem 0 0.8rem">{{ message.body }}</p>
      <div class="row">
        <a
          class="btn-primary btn-small"
          :href="whatsappLink(message)"
          target="_blank"
          rel="noopener"
          style="text-decoration: none; display: inline-block"
        >
          Open in WhatsApp
        </a>
        <button class="btn-quiet btn-small" @click="copy(message)">Copy</button>
        <button
          v-if="message.status === 'queued'"
          class="btn-quiet btn-small"
          @click="markSent(message)"
        >
          I have sent it
        </button>
      </div>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { api } from '../services/api'

interface Message {
  id: string
  to_phone: string
  to_name: string
  channel: string
  body: string
  about: string
  reference: string
  status: string
  at: string
  sent_at: string
}

const messages = ref<Message[]>([])
const loading = ref(true)
const error = ref('')
const note = ref('')
const state = ref<'queued' | 'sent'>('queued')

function at(when: string) {
  return when ? new Date(when).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : ''
}

function whatsappLink(message: Message) {
  // WhatsApp wants the international form with no leading zero or plus.
  const digits = message.to_phone.replace(/\D/g, '')
  const international = digits.startsWith('0') ? `260${digits.slice(1)}` : digits
  return `https://wa.me/${international}?text=${encodeURIComponent(message.body)}`
}

async function copy(message: Message) {
  try {
    await navigator.clipboard.writeText(message.body)
    note.value = 'Copied. Paste it into WhatsApp or a text message.'
  } catch {
    note.value = 'Could not copy on this device. Select the text and copy it by hand.'
  }
}

async function load() {
  try {
    messages.value = await api.get<Message[]>(`/customers/messages?state=${state.value}`)
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load messages.'
  } finally {
    loading.value = false
  }
}

function setState(which: 'queued' | 'sent') {
  state.value = which
  loading.value = true
  load()
}

async function markSent(message: Message) {
  try {
    await api.post(`/customers/messages/${message.id}/sent`, {})
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not tick that off.'
  }
}

onMounted(load)
</script>
