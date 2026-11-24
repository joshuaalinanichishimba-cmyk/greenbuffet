<!--
  Menu: prices and availability, laid out as the demo's Menu screen.

  One table per section of the menu board, each row a price box and an
  "Available" tick. A price saves when the box loses focus; a tick saves the
  moment it is pressed, so a cashier who runs out of birria beef can take it
  off every till in one tap. Every change is logged, with the old price.

  Below the menu, the build options - bases, proteins, toppings, dips - with
  the same tick, because "out of avocado" is a topping, not a dish.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import PageHead from '../components/PageHead.vue'
import MenuTabs from '../components/MenuTabs.vue'
import { ApiError, api, type MenuCategory, type MenuOptionGroup, type MenuOptionItem, type MenuProduct } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'

const categories = ref<MenuCategory[]>([])
const products = ref<MenuProduct[]>([])
const groups = ref<MenuOptionGroup[]>([])
const error = ref('')
const saved = ref('')
const prices = ref<Record<string, string>>({})

const canEdit = computed(() => session.can('menu.edit'))
const canToggle = computed(() => session.canAny('menu.edit', 'pos.use', 'kitchen.view'))

const sections = computed(() =>
  categories.value
    .map((c) => ({ ...c, items: products.value.filter((p) => p.category_id === c.id) }))
    .filter((c) => c.items.length),
)

async function load() {
  try {
    const [c, p, g] = await Promise.all([
      api.menuCategories(),
      api.menuProducts(),
      session.can('menu.edit') ? api.optionGroups() : Promise.resolve([] as MenuOptionGroup[]),
    ])
    categories.value = c
    products.value = p
    groups.value = g.filter((x) => x.is_active)
    prices.value = Object.fromEntries(p.map((x) => [x.id, (x.price_ngwee / 100).toFixed(2)]))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the menu.'
  }
}

function flash(text: string) {
  saved.value = text
  window.setTimeout(() => {
    if (saved.value === text) saved.value = ''
  }, 3000)
}

async function savePrice(p: MenuProduct) {
  const ngwee = toNgwee(prices.value[p.id] ?? '')
  if (ngwee === null) {
    error.value = `${p.name}: that is not a price.`
    prices.value[p.id] = (p.price_ngwee / 100).toFixed(2)
    return
  }
  if (ngwee === p.price_ngwee) return
  try {
    const updated = await api.patchProduct(p.id, { price_ngwee: ngwee })
    Object.assign(p, updated)
    prices.value[p.id] = (updated.price_ngwee / 100).toFixed(2)
    error.value = ''
    flash(`${p.name} is now ${kwacha(updated.price_ngwee)}.`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change the price.'
  }
}

async function toggleProduct(p: MenuProduct) {
  try {
    const updated = await api.patchProduct(p.id, { is_available: !p.is_available })
    Object.assign(p, updated)
    flash(`${p.name} ${updated.is_available ? 'is back on' : 'is sold out'}.`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change that.'
  }
}

async function toggleOption(item: MenuOptionItem) {
  try {
    const updated = await api.patchOptionItem(item.id, {
      name: item.name,
      price_ngwee: item.price_ngwee,
      sort: item.sort,
      is_active: item.is_active,
      is_available: !item.is_available,
    })
    Object.assign(item, updated)
    flash(`${item.name} ${updated.is_available ? 'is back in stock' : 'is out of stock'}.`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change that.'
  }
}

async function toggleStamp(c: MenuCategory) {
  try {
    const updated = await api.patchCategory(c.id, { earns_stamp: !c.earns_stamp })
    const found = categories.value.find((x) => x.id === c.id)
    if (found) found.earns_stamp = updated.earns_stamp
    flash(`${c.name} ${updated.earns_stamp ? 'now earns' : 'no longer earns'} stamps.`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change that.'
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <PageHead
      title="Menu"
      lead="Change prices and availability. Every change shows on the till straight away and is written in the activity log with the old price."
    />
    <MenuTabs />

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="saved" class="notice" role="status">{{ saved }}</p>

    <section v-for="c in sections" :key="c.id" class="section">
      <div class="section-head">
        <h2>{{ c.name }}</h2>
        <label v-if="canEdit" class="switch stamp">
          <input type="checkbox" :checked="c.earns_stamp" @change="toggleStamp(c)" />
          Earns a stamp
        </label>
        <span v-else-if="c.earns_stamp" class="pill">Earns a stamp</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th class="price-col">Price (K)</th>
              <th class="avail-col">On the menu</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in c.items" :key="p.id">
              <td>
                <b>{{ p.name }}</b>
                <p v-if="p.description" class="muted small">{{ p.description }}</p>
              </td>
              <td class="price-col">
                <input
                  v-if="canEdit"
                  v-model="prices[p.id]"
                  class="price"
                  type="text"
                  inputmode="decimal"
                  :aria-label="`Price of ${p.name}`"
                  @blur="savePrice(p)"
                  @keydown.enter="($event.target as HTMLInputElement).blur()"
                />
                <span v-else>{{ kwacha(p.price_ngwee) }}</span>
              </td>
              <td class="avail-col">
                <label class="switch">
                  <input type="checkbox" :checked="p.is_available" :disabled="!canToggle" @change="toggleProduct(p)" />
                  {{ p.is_available ? 'Available' : 'Sold out' }}
                </label>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <template v-if="groups.length">
      <h2 class="options-title">Build options</h2>
      <p class="muted">What goes into a build-your-own bowl or burrito. Untick anything you have run out of and it disappears from the till.</p>
      <div class="option-grid">
        <section v-for="g in groups" :key="g.id" class="card">
          <h3>{{ g.name }}</h3>
          <div class="chips">
            <button
              v-for="i in g.items.filter((x) => x.is_active)"
              :key="i.id"
              class="chip"
              :aria-pressed="i.is_available"
              :disabled="!canToggle"
              @click="toggleOption(i)"
            >
              <span class="tick">{{ i.is_available ? '✓' : '✕' }}</span>
              {{ i.name }}<span v-if="i.price_ngwee" class="muted"> +{{ kwacha(i.price_ngwee) }}</span>
            </button>
          </div>
        </section>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.section { margin-bottom: 1.4rem; }
.section-head { display: flex; align-items: center; gap: 1rem; margin: 0 0 .6rem; }
.section-head h2 { margin: 0; font-size: 1.25rem; }
.stamp { font-size: .88rem; color: var(--muted); }
.small { font-size: .85rem; margin: .15rem 0 0; }
.price-col { width: 9rem; }
.avail-col { width: 10rem; }
.price { width: 6.5rem; text-align: right; font-variant-numeric: tabular-nums; }
.options-title { margin-top: 2rem; font-size: 1.25rem; }
.option-grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); margin-top: .8rem; }
.option-grid h3 { margin: 0 0 .7rem; }
.chip { min-height: 38px; font-size: .9rem; }
.chip[aria-pressed='false'] { text-decoration: line-through; color: var(--muted); }
.tick { width: 20px; height: 20px; border-radius: 50%; display: inline-grid; place-items: center; font-size: .72rem; background: var(--leaf-soft); color: var(--green-deep); }
.chip[aria-pressed='false'] .tick { background: var(--danger-soft); color: var(--danger); }
@media (max-width: 560px) {
  .price-col { width: 6.8rem; }
  .avail-col { width: auto; }
  .price { width: 5.2rem; }
}
</style>
