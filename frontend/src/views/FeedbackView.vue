<!--
  Feedback: what customers say, as on the demo.

  The demo collects ratings from its customer site. This system has none, so
  feedback is what a customer tells staff at the counter, on the phone or on
  WhatsApp, written down here against the order it is about.
-->
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import { api } from '../services/api'

interface Row { id: string; rating: number; comment: string; source: string; order_number: string; customer: string; by: string; at: string }
interface Data { average: number | null; count: number; spread: Record<string, number>; rows: Row[] }

const data = ref<Data | null>(null)
const error = ref('')
const note = ref('')
const form = reactive({ rating: 5, comment: '', order_number: '', source: 'counter' })

const sources: Record<string, string> = { counter: 'At the counter', phone: 'On the phone', whatsapp: 'On WhatsApp', other: 'Other' }

async function load() {
  try {
    data.value = await api.get<Data>('/dashboard/feedback')
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load feedback.'
  }
}

async function add() {
  error.value = ''
  try {
    await api.post('/dashboard/feedback', form)
    note.value = 'Written down. Thank you.'
    form.comment = ''
    form.order_number = ''
    form.rating = 5
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not save that.'
  }
}

function stars(n: number) {
  return '★'.repeat(n) + '☆'.repeat(5 - n)
}

onMounted(load)
</script>

<template>
  <AppShell>
    <PageHead title="Feedback" lead="What customers tell you, at the counter, on the phone or on WhatsApp." />

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <div class="split">
      <div class="col">
        <section class="card">
          <h3>Write one down</h3>
          <div class="pick" role="radiogroup" aria-label="Rating">
            <button
              v-for="n in 5"
              :key="n"
              type="button"
              :aria-checked="form.rating === n"
              role="radio"
              :class="{ on: n <= form.rating }"
              @click="form.rating = n"
            >★</button>
          </div>
          <label class="field">What they said<textarea v-model="form.comment" maxlength="500" placeholder="The bowl was huge and the delivery was fast." /></label>
          <div class="grid-2" style="margin-top: .8rem">
            <label class="field">Order number (optional)<input v-model="form.order_number" type="text" maxlength="24" placeholder="GB-20261124-012" /></label>
            <label class="field">
              Where
              <select v-model="form.source">
                <option v-for="(label, key) in sources" :key="key" :value="key">{{ label }}</option>
              </select>
            </label>
          </div>
          <button class="btn-primary" style="margin-top: 1rem" @click="add">Save it</button>
        </section>

        <div v-if="data && !data.rows.length" class="empty">Nothing written down yet.</div>
        <article v-for="r in data?.rows ?? []" :key="r.id" class="card review">
          <div class="spread">
            <span class="stars">{{ stars(r.rating) }}</span>
            <span class="muted small">{{ r.at }}</span>
          </div>
          <p v-if="r.comment" class="said">“{{ r.comment }}”</p>
          <p class="muted small">
            {{ sources[r.source] ?? r.source }}<template v-if="r.order_number"> · {{ r.order_number }}</template><template v-if="r.customer"> · {{ r.customer }}</template> · noted by {{ r.by }}
          </p>
        </article>
      </div>

      <div class="col">
        <section v-if="data" class="card summary">
          <h3>Overall</h3>
          <template v-if="data.count">
            <p class="big"><b>{{ data.average }}</b><span class="stars">★★★★★</span></p>
            <p class="muted">{{ data.count }} ratings</p>
            <div class="spreadbars">
              <div v-for="n in [5, 4, 3, 2, 1]" :key="n" class="sb">
                <span>{{ n }}★</span>
                <div class="bar amber"><span :style="{ width: `${((data.spread[n] ?? 0) / data.count) * 100}%` }" /></div>
                <b>{{ data.spread[n] ?? 0 }}</b>
              </div>
            </div>
          </template>
          <p v-else class="muted">No ratings yet.</p>
        </section>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
h3 { margin: 0 0 .8rem; }
.small { font-size: .85rem; }
.pick { display: flex; gap: .2rem; margin-bottom: .8rem; }
.pick button { background: none; border: 0; font-size: 2rem; line-height: 1; color: var(--line); padding: 0 .1rem; }
.pick button.on { color: #E8A317; }
.stars { color: #E8A317; letter-spacing: .08em; }
.review .said { margin: .5rem 0; font-size: 1.02rem; }
.big { display: flex; align-items: baseline; gap: .6rem; margin: 0; }
.big b { font-family: var(--display); font-weight: 900; font-size: 2.4rem; }
.spreadbars { display: grid; gap: .45rem; margin-top: 1rem; }
.sb { display: grid; grid-template-columns: 2.2rem minmax(0, 1fr) 2ch; gap: .6rem; align-items: center; font-size: .9rem; }
.sb b { text-align: right; }
</style>
