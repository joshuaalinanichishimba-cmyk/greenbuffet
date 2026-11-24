<!--
  Clocking in and out for someone who does not manage staff: a cashier, the
  kitchen, the store room. Their own times only, from /people/me.
-->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../services/api'

interface Row { id: string; day: string; clock_in: string; clock_out: string | null; hours: number | null }
const me = ref<{ linked: boolean; name: string; clocked_in: boolean; rows: Row[] } | null>(null)
const error = ref('')
const busy = ref(false)

async function load() {
  try {
    me.value = await api.get('/people/me')
    error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load your clocking.'
  }
}

async function clock(direction: 'in' | 'out') {
  busy.value = true
  try {
    await api.post(`/people/clock-${direction}`, {})
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not clock you ' + direction + '.'
  } finally {
    busy.value = false
  }
}

function time(iso: string | null) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '–'
}
function day(iso: string) {
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-ZM', { weekday: 'short', day: 'numeric', month: 'short' })
}

onMounted(load)
</script>

<template>
  <p v-if="error" class="error">{{ error }}</p>
  <template v-if="me">
    <section v-if="!me.linked" class="card home-banner warn">
      <div class="text">
        <b>Your account is not on the staff list yet</b>
        <span>Ask the manager to add you under Staff, linked to this account. Then you can clock in here.</span>
      </div>
    </section>
    <template v-else>
      <section class="card home-banner" :class="me.clocked_in ? 'good' : 'warn'">
        <span class="home-dot" :class="{ warn: !me.clocked_in }" />
        <div class="text">
          <b>{{ me.clocked_in ? `Clocked in since ${time(me.rows.find((r) => !r.clock_out)?.clock_in ?? null)}` : 'You are not clocked in' }}</b>
          <span>Your hours go straight to payroll.</span>
        </div>
        <button v-if="me.clocked_in" class="btn-outline" :disabled="busy" @click="clock('out')">Clock out</button>
        <button v-else class="btn-primary" :disabled="busy" @click="clock('in')">Clock in</button>
      </section>
      <section class="card">
        <div class="card-head"><h3>Your last two weeks</h3></div>
        <p v-if="!me.rows.length" class="home-empty">No clocking yet.</p>
        <ul class="home-list">
          <li v-for="r in me.rows" :key="r.id">
            <div><b>{{ day(r.day) }}</b> <span class="muted">· {{ time(r.clock_in) }} to {{ r.clock_out ? time(r.clock_out) : 'now' }}</span></div>
            <b class="num">{{ r.hours !== null ? `${r.hours} h` : 'on now' }}</b>
          </li>
        </ul>
      </section>
    </template>
  </template>
</template>
