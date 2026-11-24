<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import MenuTabs from '../components/MenuTabs.vue'
import ProductEditor from '../components/ProductEditor.vue'
import {
  ApiError, api,
  type MenuCategory, type MenuIngredient, type MenuOptionGroup, type MenuProduct,
} from '../services/api'
import { kwacha } from '../services/money'
import { session } from '../stores/session'

const categories = ref<MenuCategory[]>([])
const products = ref<MenuProduct[]>([])
const groups = ref<MenuOptionGroup[]>([])
const ingredients = ref<MenuIngredient[]>([])

const selectedCategory = ref('')
const search = ref('')
const showRetired = ref(false)
const loading = ref(true)
const error = ref('')
const busyId = ref('')

const editing = ref<MenuProduct | null>(null)
const editorOpen = ref(false)
const newSection = ref({ open: false, name: '', saving: false })

const mayEdit = computed(() => session.can('menu.edit'))

const shown = computed(() => {
  const term = search.value.trim().toLowerCase()
  return products.value.filter((p) => {
    if (selectedCategory.value && p.category_id !== selectedCategory.value) return false
    if (!term) return true
    return p.name.toLowerCase().includes(term) || p.code.toLowerCase().includes(term)
  })
})

const soldOut = computed(() => products.value.filter((p) => p.is_active && !p.is_available).length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [c, p, g, i] = await Promise.all([
      api.menuCategories(showRetired.value),
      api.menuProducts({ includeHidden: showRetired.value }),
      api.optionGroups(),
      api.ingredients(),
    ])
    categories.value = c
    products.value = p
    groups.value = g
    ingredients.value = i
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the menu.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

function startNew() {
  editing.value = null
  editorOpen.value = true
}

function edit(product: MenuProduct) {
  editing.value = product
  editorOpen.value = true
}

function onSaved(saved: MenuProduct) {
  const at = products.value.findIndex((p) => p.id === saved.id)
  if (at === -1) products.value.push(saved)
  else products.value[at] = saved
  editorOpen.value = false
  editing.value = null
  load()
}

async function toggleAvailable(product: MenuProduct) {
  busyId.value = product.id
  error.value = ''
  try {
    const saved = await api.patchProduct(product.id, { is_available: !product.is_available })
    products.value = products.value.map((p) => (p.id === saved.id ? saved : p))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change that.'
  } finally {
    busyId.value = ''
  }
}

async function addSection() {
  if (newSection.value.name.trim().length < 2) return
  newSection.value.saving = true
  error.value = ''
  try {
    await api.createCategory({ name: newSection.value.name.trim(), sort: (categories.value.length + 1) * 10 })
    newSection.value = { open: false, name: '', saving: false }
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not add the section.'
    newSection.value.saving = false
  }
}
</script>

<template>
  <AppShell>
    <h1>Menu</h1>
    <p class="lead">
      What the till sells and what the kitchen makes. Marking something sold out takes it off the
      till at once without removing it from the menu.
    </p>
    <MenuTabs />

    <p v-if="error" class="error">{{ error }}</p>

    <section class="cards">
      <article class="card">
        <b>{{ products.filter((p) => p.is_active).length }}</b>
        <span>Items on the menu</span>
      </article>
      <article class="card" :class="{ warn: soldOut > 0 }">
        <b>{{ soldOut }}</b>
        <span>Sold out right now</span>
      </article>
      <article class="card">
        <b>{{ groups.length }}</b>
        <span>Choice groups</span>
      </article>
      <article class="card">
        <b>{{ ingredients.length }}</b>
        <span>Ingredients</span>
      </article>
    </section>

    <ProductEditor
      v-if="editorOpen && mayEdit"
      :product="editing"
      :categories="categories"
      :groups="groups"
      :ingredients="ingredients"
      @saved="onSaved"
      @close="editorOpen = false"
    />

    <div class="toolbar">
      <label class="field">
        Search
        <input v-model="search" type="text" placeholder="bowl, BUR-01" />
      </label>
      <label class="field">
        Section
        <select v-model="selectedCategory">
          <option value="">All sections</option>
          <option v-for="c in categories" :key="c.id" :value="c.id">
            {{ c.name }} ({{ c.product_count }})
          </option>
        </select>
      </label>
      <label class="check">
        <input v-model="showRetired" type="checkbox" @change="load" />
        Show retired
      </label>
      <span class="spacer" />
      <button v-if="mayEdit" class="btn-quiet btn-small" @click="newSection.open = !newSection.open">
        Add a section
      </button>
      <button v-if="mayEdit" class="btn-primary btn-small" @click="startNew">Add an item</button>
    </div>

    <div v-if="newSection.open" class="panel new-section">
      <label class="field">
        Section name
        <input v-model="newSection.name" type="text" placeholder="Breakfast" />
      </label>
      <button class="btn-primary btn-small" :disabled="newSection.saving" @click="addSection">Add</button>
      <button class="btn-quiet btn-small" @click="newSection.open = false">Cancel</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!shown.length" class="muted">Nothing here yet.</p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Section</th>
            <th>Price</th>
            <th>Ingredients</th>
            <th>Choices</th>
            <th>State</th>
            <th v-if="mayEdit"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in shown" :key="p.id" :class="{ retired: !p.is_active }">
            <td>
              <b>{{ p.name }}</b>
              <small class="muted">{{ p.code }}</small>
            </td>
            <td>{{ p.category_name }}</td>
            <td class="num">{{ kwacha(p.price_ngwee) }}</td>
            <td class="num">
              <template v-if="p.recipe_cost_ngwee">
                {{ kwacha(p.recipe_cost_ngwee) }}
                <small class="muted">
                  <template v-if="p.option_groups.length">plus what the choices use</template>
                  <template v-else>{{ Math.round(((p.price_ngwee - p.recipe_cost_ngwee) / p.price_ngwee) * 100) }}% margin</template>
                </small>
              </template>
              <small v-else class="muted">no recipe</small>
            </td>
            <td>
              <template v-if="p.option_groups.length">
                {{ p.option_groups.map((g) => g.name).join(', ') }}
              </template>
              <small v-else class="muted">none</small>
            </td>
            <td>
              <span v-if="!p.is_active" class="tag off">Retired</span>
              <span v-else-if="p.is_available" class="tag">On sale</span>
              <span v-else class="tag off">Sold out</span>
            </td>
            <td v-if="mayEdit" class="actions">
              <button class="btn-quiet btn-small" @click="edit(p)">Edit</button>
              <button
                v-if="p.is_active"
                class="btn-quiet btn-small"
                :disabled="busyId === p.id"
                @click="toggleAvailable(p)"
              >
                {{ p.is_available ? 'Mark sold out' : 'Back on sale' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppShell>
</template>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.8rem; margin-bottom: 1.2rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 0.8rem 1rem; display: grid; gap: 0.1rem; }
.card b { font-size: 1.3rem; }
.card span { font-size: 0.8rem; color: var(--muted); }
.card.warn b { color: var(--warn); }
.toolbar { display: flex; gap: 0.7rem; align-items: end; flex-wrap: wrap; margin-bottom: 0.8rem; }
.toolbar .field { min-width: 9rem; }
.check { display: flex; gap: 0.4rem; align-items: center; font-size: 0.88rem; padding-bottom: 0.5rem; }
.check input { width: 17px; height: 17px; accent-color: var(--green-mid); }
.spacer { flex: 1; }
.new-section { display: flex; gap: 0.6rem; align-items: end; margin-bottom: 0.9rem; }
.num { white-space: nowrap; }
td small { display: block; font-size: 0.76rem; }
tr.retired { opacity: 0.6; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; min-width: 13rem; }
</style>
