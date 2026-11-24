<!--
  Promotions: codes the cashier types at the till, as on the demo.

  A code is checked on the server every time it is used, so stopping one here
  stops it at every till at once, and a use is only counted when the order it
  was used on is paid for.
-->
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import { api } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'

interface Promo {
  id: string; code: string; label: string; kind: string; value: number
  minimum_ngwee: number; is_active: boolean; uses: number; discount_given_ngwee: number; summary: string
}

const promos = ref<Promo[]>([])
const error = ref('')
const note = ref('')
const canEdit = computed(() => session.can('promos.manage'))

const form = reactive({ code: '', label: '', kind: 'percent', value: '', minimum: '' })

async function load() {
  try {
    promos.value = await api.get<Promo[]>('/dashboard/promotions')
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not load promotions.'
  }
}

async function add() {
  error.value = ''
  const value = form.kind === 'percent' ? Number(form.value) : toNgwee(form.value || '0')
  if (!value || value <= 0) {
    error.value = form.kind === 'percent' ? 'Enter the percentage off.' : 'Enter the kwacha off.'
    return
  }
  try {
    await api.post('/dashboard/promotions', {
      code: form.code,
      label: form.label,
      kind: form.kind,
      value,
      minimum_ngwee: toNgwee(form.minimum || '0') ?? 0,
    })
    note.value = `${form.code.toUpperCase()} is running.`
    form.code = ''
    form.label = ''
    form.value = ''
    form.minimum = ''
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not add the promotion.'
  }
}

async function toggle(p: Promo) {
  try {
    await api.post(`/dashboard/promotions/${p.id}/toggle`)
    await load()
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'Could not change it.'
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <PageHead title="Promotions" lead="Codes the cashier types at the till. Each use is counted when the order is paid for." />

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="note" class="notice">{{ note }}</p>

    <section v-if="canEdit" class="card add">
      <h3>New code</h3>
      <div class="form">
        <label class="field">Code<input v-model="form.code" type="text" maxlength="24" placeholder="STUDENT10" /></label>
        <label class="field grow">What it is for<input v-model="form.label" type="text" maxlength="120" placeholder="10% off for CBU students" /></label>
        <label class="field">
          Type
          <select v-model="form.kind">
            <option value="percent">% off</option>
            <option value="amount">K off</option>
          </select>
        </label>
        <label class="field">{{ form.kind === 'percent' ? 'Percent' : 'Kwacha' }}<input v-model="form.value" type="number" min="0" step="any" /></label>
        <label class="field">Min. order (K)<input v-model="form.minimum" type="number" min="0" step="any" placeholder="0" /></label>
        <button class="btn-primary" :disabled="!form.code.trim()" @click="add">Start it</button>
      </div>
    </section>

    <div v-if="!promos.length" class="empty">No promotions yet.</div>
    <div class="list">
      <article v-for="p in promos" :key="p.id" class="card promo" :class="{ stopped: !p.is_active }">
        <div class="code">{{ p.code }}</div>
        <div class="body">
          <b>{{ p.label || p.summary }}</b>
          <p class="muted">{{ p.summary }}</p>
        </div>
        <div class="count">
          <b>{{ p.uses }}</b>
          <span class="muted">uses · {{ kwacha(p.discount_given_ngwee) }} given</span>
        </div>
        <span class="pill" :class="{ neutral: !p.is_active }">{{ p.is_active ? 'Running' : 'Stopped' }}</span>
        <button v-if="canEdit" class="btn-quiet btn-small" @click="toggle(p)">{{ p.is_active ? 'Stop' : 'Start again' }}</button>
      </article>
    </div>
  </AppShell>
</template>

<style scoped>
.add { margin-bottom: 1.2rem; }
.add h3 { margin: 0 0 .8rem; }
.form { display: flex; gap: .8rem; flex-wrap: wrap; align-items: flex-end; }
.form .field { flex: 0 1 140px; }
.form .grow { flex: 1 1 240px; }
.list { display: grid; gap: .8rem; }
.promo { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto auto; gap: 1rem; align-items: center; }
.promo.stopped { opacity: .7; }
.code {
  font-family: var(--display); font-weight: 900; letter-spacing: .04em;
  padding: .5rem .8rem; border-radius: 12px; border: 2px dashed var(--green);
  color: var(--green-deep); background: var(--leaf-soft);
}
.body { min-width: 0; }
.body p { margin: .1rem 0 0; }
.count { display: grid; text-align: right; }
.count b { font-family: var(--display); font-weight: 900; font-size: 1.3rem; }
@media (max-width: 700px) {
  .promo { grid-template-columns: auto minmax(0, 1fr); }
  .count { text-align: left; }
}
</style>
