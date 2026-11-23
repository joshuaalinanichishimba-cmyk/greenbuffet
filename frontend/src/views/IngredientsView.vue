<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type MenuIngredient } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'

const ingredients = ref<MenuIngredient[]>([])
const loading = ref(true)
const error = ref('')
const showRetired = ref(false)

const mayEdit = computed(() => session.can('menu.edit'))

const form = reactive({ name: '', unit: 'kg', cost: '', note: '', saving: false })

const units = [
  { value: 'kg', label: 'by the kilogram' },
  { value: 'g', label: 'by the gram' },
  { value: 'l', label: 'by the litre' },
  { value: 'ml', label: 'by the millilitre' },
  { value: 'each', label: 'counted singly' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    ingredients.value = await api.ingredients(showRetired.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the ingredients.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function add() {
  const cost = toNgwee(form.cost || '0')
  if (form.name.trim().length < 2) {
    error.value = 'Give the ingredient a name.'
    return
  }
  if (cost === null) {
    error.value = 'Enter the cost as a number, for example 85 or 85.50.'
    return
  }
  form.saving = true
  error.value = ''
  try {
    await api.createIngredient({
      name: form.name.trim(), unit: form.unit, cost_ngwee: cost, note: form.note.trim(),
    })
    Object.assign(form, { name: '', unit: form.unit, cost: '', note: '', saving: false })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not add the ingredient.'
    form.saving = false
  }
}

async function recost(ingredient: MenuIngredient) {
  const typed = window.prompt(
    `What does one ${ingredient.unit === 'each' ? 'of these' : ingredient.unit} cost now?`,
    (ingredient.cost_ngwee / 100).toFixed(2),
  )
  if (typed === null) return
  const cost = toNgwee(typed)
  if (cost === null) {
    error.value = 'That is not a price. Use a number like 85 or 85.50.'
    return
  }
  await patch(ingredient, { cost_ngwee: cost })
}

async function patch(ingredient: MenuIngredient, changes: Record<string, unknown>) {
  error.value = ''
  try {
    const saved = await api.patchIngredient(ingredient.id, changes)
    ingredients.value = ingredients.value.map((i) => (i.id === saved.id ? saved : i))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save that change.'
    await load()
  }
}
</script>

<template>
  <AppShell>
    <h1>Ingredients</h1>
    <p class="lead">
      What the kitchen buys, and what it costs. Recipes are written against this list, so a new
      supplier price here changes the cost of every dish that uses it. Stock levels and purchase
      orders arrive at stage 6.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="mayEdit" class="panel add">
      <b>Add an ingredient</b>
      <div class="add-grid">
        <label class="field">
          Name
          <input v-model="form.name" type="text" placeholder="Chicken breast" />
        </label>
        <label class="field">
          Bought
          <select v-model="form.unit">
            <option v-for="u in units" :key="u.value" :value="u.value">{{ u.label }}</option>
          </select>
        </label>
        <label class="field">
          Cost per {{ form.unit === 'each' ? 'one' : form.unit }}
          <input v-model="form.cost" type="text" inputmode="decimal" placeholder="85.00" />
        </label>
        <label class="field">
          Note
          <input v-model="form.note" type="text" placeholder="From Shoprite, 2 kg packs" />
        </label>
        <button class="btn-primary" :disabled="form.saving" @click="add">
          {{ form.saving ? 'Adding…' : 'Add' }}
        </button>
      </div>
    </section>

    <div class="toolbar">
      <label class="check">
        <input v-model="showRetired" type="checkbox" @change="load" />
        Show retired
      </label>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!ingredients.length" class="muted">No ingredients yet.</p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ingredient</th>
            <th>Bought</th>
            <th>Cost</th>
            <th>Used in</th>
            <th v-if="mayEdit"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="i in ingredients" :key="i.id" :class="{ retired: !i.is_active }">
            <td>
              <b>{{ i.name }}</b>
              <small v-if="i.note" class="muted">{{ i.note }}</small>
            </td>
            <td>{{ units.find((u) => u.value === i.unit)?.label ?? i.unit }}</td>
            <td class="num">{{ kwacha(i.cost_ngwee) }} <small class="muted">per {{ i.unit === 'each' ? 'one' : i.unit }}</small></td>
            <td class="num">{{ i.used_in }} recipe{{ i.used_in === 1 ? '' : 's' }}</td>
            <td v-if="mayEdit" class="actions">
              <button class="btn-quiet btn-small" @click="recost(i)">New cost</button>
              <button class="btn-quiet btn-small" @click="patch(i, { is_active: !i.is_active })">
                {{ i.is_active ? 'Retire' : 'Bring back' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppShell>
</template>

<style scoped>
.add { margin-bottom: 0.8rem; }
.add > b { display: block; margin-bottom: 0.7rem; }
.add-grid { display: grid; gap: 0.7rem; grid-template-columns: 1fr; align-items: end; }
.toolbar { margin-bottom: 0.7rem; }
.check { display: flex; gap: 0.4rem; align-items: center; font-size: 0.88rem; }
.check input { width: 17px; height: 17px; accent-color: var(--green-mid); }
.num { white-space: nowrap; }
td small { display: block; font-size: 0.76rem; }
tr.retired { opacity: 0.6; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }

@media (min-width: 820px) {
  .add-grid { grid-template-columns: 1.4fr 1fr 0.9fr 1.4fr auto; }
}
</style>
