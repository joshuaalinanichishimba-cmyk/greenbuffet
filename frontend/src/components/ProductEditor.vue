<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  ApiError, api,
  type MenuCategory, type MenuIngredient, type MenuOptionGroup, type MenuProduct, type StoredFile,
} from '../services/api'
import { fileUrl, forgetFile } from '../services/files'
import { kwacha, toNgwee } from '../services/money'
import { entryUnit, fromMilli, toMilli } from '../services/quantities'

const props = defineProps<{
  product: MenuProduct | null
  categories: MenuCategory[]
  groups: MenuOptionGroup[]
  ingredients: MenuIngredient[]
}>()

const emit = defineEmits<{ saved: [MenuProduct]; close: [] }>()

const form = reactive({
  code: '',
  name: '',
  description: '',
  category_id: '',
  price: '',
  price_reason: '',
  station: 'kitchen',
  sort: 100,
  is_active: true,
  is_available: true,
})

const chosenGroups = ref<string[]>([])
const lines = ref<{ ingredient_id: string; typed: string; note: string }[]>([])
const error = ref('')
const saving = ref(false)

// Photographs of the dish, shown on the till and, later, on the website.
const photos = ref<StoredFile[]>([])
const shots = ref<Record<string, string>>({})
const uploading = ref(false)

async function loadPhotos(productId: string) {
  photos.value = await api.storedFiles({ attached_to: 'product', attached_id: productId, kind: 'photo' })
  for (const photo of photos.value) {
    if (shots.value[photo.id]) continue
    try {
      shots.value = { ...shots.value, [photo.id]: await fileUrl(photo.id, true) }
    } catch {
      /* the dish is still editable without its picture */
    }
  }
}

async function addPhoto(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !props.product) return
  uploading.value = true
  error.value = ''
  try {
    await api.uploadFile(file, {
      kind: 'photo', attached_to: 'product', attached_id: props.product.id,
      is_primary: photos.value.length === 0,
    })
    await loadPhotos(props.product.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not store that photograph.'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function removePhoto(photo: StoredFile) {
  try {
    await api.deleteFile(photo.id)
    forgetFile(photo.id)
    photos.value = photos.value.filter((p) => p.id !== photo.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not remove it.'
  }
}

const isNew = computed(() => !props.product)
const priceNgwee = computed(() => toNgwee(form.price))
const priceChanged = computed(
  () => !isNew.value && priceNgwee.value !== null && priceNgwee.value !== props.product?.price_ngwee,
)

const ingredientById = computed(
  () => new Map(props.ingredients.map((i) => [i.id, i])),
)

const recipeCost = computed(() =>
  lines.value.reduce((total, line) => {
    const ingredient = ingredientById.value.get(line.ingredient_id)
    const milli = ingredient ? toMilli(ingredient.unit, line.typed) : null
    if (!ingredient || milli === null) return total
    return total + Math.round((ingredient.cost_ngwee * milli) / 1000)
  }, 0),
)

const margin = computed(() => {
  if (priceNgwee.value === null || !recipeCost.value) return null
  const value = priceNgwee.value - recipeCost.value
  return { value, percent: priceNgwee.value ? Math.round((value / priceNgwee.value) * 100) : 0 }
})

watch(
  () => props.product,
  (p) => {
    error.value = ''
    form.price_reason = ''
    if (p) {
      Object.assign(form, {
        code: p.code,
        name: p.name,
        description: p.description,
        category_id: p.category_id,
        price: (p.price_ngwee / 100).toFixed(2),
        station: p.station,
        sort: p.sort,
        is_active: p.is_active,
        is_available: p.is_available,
      })
      chosenGroups.value = p.option_groups.map((g) => g.group_id)
      loadPhotos(p.id).catch(() => undefined)
      lines.value = p.recipe.map((line) => ({
        ingredient_id: line.ingredient_id,
        typed: fromMilli(line.unit, line.quantity_milli),
        note: line.note,
      }))
    } else {
      Object.assign(form, {
        code: '', name: '', description: '',
        category_id: props.categories[0]?.id ?? '',
        price: '', station: 'kitchen', sort: 100, is_active: true, is_available: true,
      })
      chosenGroups.value = []
      lines.value = []
      photos.value = []
    }
  },
  { immediate: true },
)

function toggleGroup(id: string) {
  const at = chosenGroups.value.indexOf(id)
  if (at === -1) chosenGroups.value.push(id)
  else chosenGroups.value.splice(at, 1)
}

function moveGroup(id: string, by: number) {
  const at = chosenGroups.value.indexOf(id)
  const to = at + by
  if (at === -1 || to < 0 || to >= chosenGroups.value.length) return
  const next = [...chosenGroups.value]
  next.splice(to, 0, next.splice(at, 1)[0])
  chosenGroups.value = next
}

function addLine() {
  const first = props.ingredients[0]
  if (first) lines.value.push({ ingredient_id: first.id, typed: '', note: '' })
}

async function save() {
  error.value = ''
  if (form.name.trim().length < 2) {
    error.value = 'Give the item a name.'
    return
  }
  if (priceNgwee.value === null) {
    error.value = 'Enter the price as a number, for example 95 or 95.50.'
    return
  }
  const badLine = lines.value.find((line) => {
    const ingredient = ingredientById.value.get(line.ingredient_id)
    return !ingredient || toMilli(ingredient.unit, line.typed) === null
  })
  if (badLine) {
    error.value = 'Every recipe line needs an amount greater than zero.'
    return
  }
  const seen = new Set<string>()
  for (const line of lines.value) {
    if (seen.has(line.ingredient_id)) {
      error.value = 'An ingredient can only appear once; add the amounts together.'
      return
    }
    seen.add(line.ingredient_id)
  }

  saving.value = true
  try {
    const body: Record<string, unknown> = {
      code: form.code.trim() || form.name.trim().slice(0, 12).toUpperCase().replace(/\s+/g, '-'),
      name: form.name.trim(),
      description: form.description.trim(),
      category_id: form.category_id,
      price_ngwee: priceNgwee.value,
      station: form.station,
      sort: form.sort,
      is_active: form.is_active,
      is_available: form.is_available,
    }
    let saved: MenuProduct
    if (isNew.value) {
      saved = await api.createProduct(body)
    } else {
      saved = await api.patchProduct(props.product!.id, { ...body, price_reason: form.price_reason.trim() })
    }
    saved = await api.setProductGroups(saved.id, chosenGroups.value)
    saved = await api.setProductRecipe(
      saved.id,
      lines.value.map((line) => ({
        ingredient_id: line.ingredient_id,
        quantity_milli: toMilli(ingredientById.value.get(line.ingredient_id)!.unit, line.typed)!,
        note: line.note.trim(),
      })),
    )
    emit('saved', saved)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save the item.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="editor panel">
    <header>
      <b>{{ isNew ? 'New menu item' : form.name || 'Menu item' }}</b>
      <button class="btn-quiet btn-small" @click="emit('close')">Close</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="grid">
      <label class="field span2">
        Name
        <input v-model="form.name" type="text" placeholder="Build your own bowl" />
      </label>
      <label class="field">
        Item code
        <input v-model="form.code" type="text" placeholder="BOWL-01" />
      </label>
      <label class="field">
        Price
        <input v-model="form.price" type="text" inputmode="decimal" placeholder="95.00" />
      </label>
      <label class="field">
        Section
        <select v-model="form.category_id">
          <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </label>
      <label class="field">
        Made at
        <select v-model="form.station">
          <option value="kitchen">Kitchen</option>
          <option value="cold">Cold station</option>
          <option value="bar">Juice bar</option>
        </select>
      </label>
      <label class="field span4">
        Description on the menu
        <input v-model="form.description" type="text" placeholder="Pick a base, a protein, toppings and a sauce." />
      </label>
      <label v-if="priceChanged" class="field span4">
        Why is the price changing?
        <input v-model="form.price_reason" type="text" placeholder="Avocado up at the supplier" />
      </label>
    </div>

    <div class="switches">
      <label><input v-model="form.is_active" type="checkbox" /> On the menu</label>
      <label><input v-model="form.is_available" type="checkbox" /> Available today</label>
    </div>

    <h3>Photographs</h3>
    <p v-if="isNew" class="muted">Save the item first, then photographs can be added to it.</p>
    <template v-else>
      <p class="muted">The first one is what the till shows. Up to 8 MB each.</p>
      <div class="photos">
        <figure v-for="photo in photos" :key="photo.id">
          <img v-if="shots[photo.id]" :src="shots[photo.id]" :alt="photo.name" />
          <span v-else class="loading">…</span>
          <figcaption>
            <span v-if="photo.is_primary" class="tag">on the till</span>
            <button class="btn-quiet btn-small" @click="removePhoto(photo)">Remove</button>
          </figcaption>
        </figure>
        <label class="add-photo">
          <span>{{ uploading ? 'Storing…' : '+ Add a photograph' }}</span>
          <input type="file" accept="image/jpeg,image/png,image/webp" @change="addPhoto" />
        </label>
      </div>
    </template>

    <h3>Choices the customer makes</h3>
    <p class="muted">
      Tick the groups this item asks about. The order here is the order the till and the website
      ask in.
    </p>
    <ul class="groups">
      <li v-for="g in groups" :key="g.id" :class="{ on: chosenGroups.includes(g.id) }">
        <label>
          <input type="checkbox" :checked="chosenGroups.includes(g.id)" @change="toggleGroup(g.id)" />
          <span>
            <b>{{ g.name }}</b>
            <small>{{ g.min_select === g.max_select ? `pick ${g.max_select}` : `${g.min_select}–${g.max_select}` }}
              · {{ g.items.length }} choices</small>
          </span>
        </label>
        <span v-if="chosenGroups.includes(g.id)" class="order">
          <button class="btn-quiet btn-small" @click="moveGroup(g.id, -1)" aria-label="Move earlier">↑</button>
          <button class="btn-quiet btn-small" @click="moveGroup(g.id, 1)" aria-label="Move later">↓</button>
          <em>{{ chosenGroups.indexOf(g.id) + 1 }}</em>
        </span>
      </li>
    </ul>

    <h3>Recipe</h3>
    <p class="muted">
      What the kitchen uses for one of these, before any choices. A base or protein brings its own
      ingredients, recorded against the choice itself, so a build-your-own item only lists what
      every one of them uses. Stage 6 takes all of it out of stock as orders are made.
    </p>
    <table v-if="lines.length">
      <thead>
        <tr><th>Ingredient</th><th>Amount</th><th>Cost</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="(line, index) in lines" :key="index">
          <td>
            <select v-model="line.ingredient_id">
              <option v-for="i in ingredients" :key="i.id" :value="i.id">{{ i.name }}</option>
            </select>
          </td>
          <td class="amount">
            <input v-model="line.typed" type="text" inputmode="decimal" />
            <span class="muted">{{ entryUnit(ingredientById.get(line.ingredient_id)?.unit ?? 'each') }}</span>
          </td>
          <td class="muted">
            {{ kwacha(Math.round(((ingredientById.get(line.ingredient_id)?.cost_ngwee ?? 0) *
              (toMilli(ingredientById.get(line.ingredient_id)?.unit ?? 'each', line.typed) ?? 0)) / 1000)) }}
          </td>
          <td>
            <button class="btn-quiet btn-small" @click="lines.splice(index, 1)">Remove</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No ingredients recorded yet.</p>

    <div class="row">
      <button class="btn-quiet btn-small" :disabled="!ingredients.length" @click="addLine">
        Add an ingredient
      </button>
      <span v-if="recipeCost" class="muted">
        Ingredients {{ kwacha(recipeCost) }}<template v-if="margin">
          · margin {{ kwacha(margin.value) }} ({{ margin.percent }}%)</template>
      </span>
    </div>

    <footer>
      <button class="btn-primary" :disabled="saving" @click="save">
        {{ saving ? 'Saving…' : isNew ? 'Add to the menu' : 'Save item' }}
      </button>
      <button class="btn-quiet" @click="emit('close')">Cancel</button>
    </footer>
  </section>
</template>

<style scoped>
.editor { margin-bottom: 1rem; }
.editor > header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.8rem; }
h3 { font-size: 0.98rem; margin: 1.4rem 0 0.2rem; }
h3 + .muted { margin: 0 0 0.6rem; }
.grid { display: grid; gap: 0.7rem; grid-template-columns: 1fr; }
.switches { display: flex; gap: 1.2rem; flex-wrap: wrap; margin-top: 0.9rem; font-size: 0.9rem; }
.switches input, .groups input { width: 17px; height: 17px; accent-color: var(--green-mid); }
.groups { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
.groups li {
  display: flex; justify-content: space-between; align-items: center; gap: 0.6rem;
  border: 1px solid var(--line); border-radius: 12px; padding: 0.5rem 0.7rem; background: #fff;
}
.groups li.on { border-color: var(--green-mid); background: #f4fbf0; }
.groups label { display: flex; gap: 0.6rem; align-items: center; }
.groups small { display: block; color: var(--muted); font-size: 0.78rem; }
.order { display: flex; gap: 0.3rem; align-items: center; }
.order em { font-style: normal; font-weight: 700; color: var(--green-mid); min-width: 1.2em; text-align: center; }
.photos { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.4rem; }
.photos figure { margin: 0; width: 120px; }
.photos img { width: 120px; height: 90px; object-fit: cover; border-radius: 10px; display: block; }
.photos .loading { width: 120px; height: 90px; display: grid; place-items: center; background: #eef2ea; border-radius: 10px; color: var(--muted); }
.photos figcaption { display: flex; gap: 0.3rem; align-items: center; justify-content: space-between; margin-top: 0.25rem; font-size: 0.72rem; }
.add-photo {
  width: 120px; height: 90px; border: 1px dashed #b9c4b4; border-radius: 10px;
  display: grid; place-items: center; text-align: center; font-size: 0.78rem;
  color: var(--muted); cursor: pointer; position: relative; overflow: hidden; padding: 0.3rem;
}
.add-photo input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.amount { display: flex; gap: 0.4rem; align-items: center; }
.amount input { width: 6.5rem; }
.row { display: flex; gap: 0.8rem; align-items: center; flex-wrap: wrap; margin-top: 0.7rem; }
footer { display: flex; gap: 0.5rem; margin-top: 1.4rem; }
table { margin-top: 0.3rem; }

@media (min-width: 760px) {
  .grid { grid-template-columns: repeat(4, 1fr); }
  .span2 { grid-column: span 2; }
  .span4 { grid-column: span 4; }
}
</style>
