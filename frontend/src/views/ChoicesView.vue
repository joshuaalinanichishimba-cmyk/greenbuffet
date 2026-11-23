<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type MenuOptionGroup, type MenuOptionItem } from '../services/api'
import { kwacha, toNgwee } from '../services/money'
import { session } from '../stores/session'

const groups = ref<MenuOptionGroup[]>([])
const loading = ref(true)
const error = ref('')
const openId = ref('')

const mayEdit = computed(() => session.can('menu.edit'))

const newGroup = reactive({ open: false, name: '', helper: '', min_select: 1, max_select: 1, saving: false })
const newItem = reactive({ groupId: '', name: '', price: '', saving: false })

async function load() {
  loading.value = true
  error.value = ''
  try {
    groups.value = await api.optionGroups()
    if (!openId.value) openId.value = groups.value[0]?.id ?? ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the choices.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function addGroup() {
  if (newGroup.name.trim().length < 2) {
    error.value = 'Give the group a name, like Protein or Sauce.'
    return
  }
  newGroup.saving = true
  error.value = ''
  try {
    const created = await api.createOptionGroup({
      name: newGroup.name.trim(),
      helper: newGroup.helper.trim(),
      min_select: newGroup.min_select,
      max_select: newGroup.max_select,
    })
    Object.assign(newGroup, { open: false, name: '', helper: '', min_select: 1, max_select: 1, saving: false })
    await load()
    openId.value = created.id
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not add the group.'
    newGroup.saving = false
  }
}

async function saveGroup(group: MenuOptionGroup, changes: Record<string, unknown>) {
  error.value = ''
  try {
    const saved = await api.patchOptionGroup(group.id, changes)
    groups.value = groups.value.map((g) => (g.id === saved.id ? { ...saved, used_by: g.used_by } : g))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save the group.'
    await load()
  }
}

async function addItem(group: MenuOptionGroup) {
  const price = toNgwee(newItem.price || '0')
  if (newItem.name.trim().length < 1) {
    error.value = 'Give the choice a name.'
    return
  }
  if (price === null) {
    error.value = 'Enter the extra charge as a number, or leave it empty for no charge.'
    return
  }
  newItem.saving = true
  error.value = ''
  try {
    await api.addOptionItem(group.id, {
      name: newItem.name.trim(),
      price_ngwee: price,
      sort: (group.items.length + 1) * 10,
    })
    Object.assign(newItem, { groupId: group.id, name: '', price: '', saving: false })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not add the choice.'
    newItem.saving = false
  }
}

async function toggleItem(item: MenuOptionItem, field: 'is_available' | 'is_active') {
  error.value = ''
  try {
    await api.patchOptionItem(item.id, {
      name: item.name,
      price_ngwee: item.price_ngwee,
      sort: item.sort,
      is_active: field === 'is_active' ? !item.is_active : item.is_active,
      is_available: field === 'is_available' ? !item.is_available : item.is_available,
    })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change that choice.'
  }
}

async function repriceItem(item: MenuOptionItem) {
  const typed = window.prompt(`Extra charge for ${item.name}, in kwacha`, (item.price_ngwee / 100).toFixed(2))
  if (typed === null) return
  const price = toNgwee(typed)
  if (price === null) {
    error.value = 'That is not a price. Use a number like 15 or 15.50.'
    return
  }
  error.value = ''
  try {
    await api.patchOptionItem(item.id, {
      name: item.name, price_ngwee: price, sort: item.sort,
      is_active: item.is_active, is_available: item.is_available,
    })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change the charge.'
  }
}
</script>

<template>
  <AppShell>
    <h1>Choices</h1>
    <p class="lead">
      The questions an item asks: base, protein, toppings, sauce, size. A group is written once and
      used by as many items as you like, so a new topping reaches every bowl and burrito at once.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="mayEdit" class="toolbar">
      <button class="btn-quiet btn-small" @click="newGroup.open = !newGroup.open">Add a group</button>
    </div>

    <div v-if="newGroup.open" class="panel new-group">
      <label class="field">
        Name
        <input v-model="newGroup.name" type="text" placeholder="Protein" />
      </label>
      <label class="field helper">
        Note shown to the customer
        <input v-model="newGroup.helper" type="text" placeholder="Choose one" />
      </label>
      <label class="field narrow">
        Least
        <input v-model.number="newGroup.min_select" type="text" inputmode="numeric" />
      </label>
      <label class="field narrow">
        Most
        <input v-model.number="newGroup.max_select" type="text" inputmode="numeric" />
      </label>
      <button class="btn-primary btn-small" :disabled="newGroup.saving" @click="addGroup">Add</button>
      <button class="btn-quiet btn-small" @click="newGroup.open = false">Cancel</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <ul v-else class="group-list">
      <li v-for="g in groups" :key="g.id" class="panel" :class="{ inactive: !g.is_active }">
        <header>
          <button class="title" @click="openId = openId === g.id ? '' : g.id">
            <b>{{ g.name }}</b>
            <span class="muted">
              {{ g.min_select === g.max_select ? `pick exactly ${g.max_select}` : `pick ${g.min_select} to ${g.max_select}` }}
              · {{ g.items.length }} choices · used by {{ g.used_by }} item{{ g.used_by === 1 ? '' : 's' }}
            </span>
          </button>
          <div v-if="mayEdit" class="row">
            <button class="btn-quiet btn-small" @click="saveGroup(g, { is_active: !g.is_active })">
              {{ g.is_active ? 'Retire' : 'Bring back' }}
            </button>
          </div>
        </header>

        <div v-if="openId === g.id" class="body">
          <p v-if="g.helper" class="muted helper-line">“{{ g.helper }}”</p>
          <table v-if="g.items.length">
            <thead>
              <tr><th>Choice</th><th>Extra charge</th><th>State</th><th v-if="mayEdit"></th></tr>
            </thead>
            <tbody>
              <tr v-for="item in g.items" :key="item.id" :class="{ retired: !item.is_active }">
                <td><b>{{ item.name }}</b></td>
                <td class="num">{{ item.price_ngwee ? kwacha(item.price_ngwee) : 'no charge' }}</td>
                <td>
                  <span v-if="!item.is_active" class="tag off">Retired</span>
                  <span v-else-if="item.is_available" class="tag">Available</span>
                  <span v-else class="tag off">Sold out</span>
                </td>
                <td v-if="mayEdit" class="actions">
                  <button class="btn-quiet btn-small" @click="repriceItem(item)">Charge</button>
                  <button class="btn-quiet btn-small" @click="toggleItem(item, 'is_available')">
                    {{ item.is_available ? 'Sold out' : 'Available' }}
                  </button>
                  <button class="btn-quiet btn-small" @click="toggleItem(item, 'is_active')">
                    {{ item.is_active ? 'Retire' : 'Bring back' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted">No choices in this group yet.</p>

          <div v-if="mayEdit" class="add-item">
            <label class="field">
              New choice
              <input v-model="newItem.name" type="text" placeholder="Grilled chicken" @focus="newItem.groupId = g.id" />
            </label>
            <label class="field narrow">
              Extra charge
              <input v-model="newItem.price" type="text" inputmode="decimal" placeholder="0.00" />
            </label>
            <button class="btn-quiet btn-small" :disabled="newItem.saving" @click="addItem(g)">Add choice</button>
          </div>
        </div>
      </li>
    </ul>
  </AppShell>
</template>

<style scoped>
.toolbar { margin-bottom: 0.8rem; }
.new-group { display: flex; gap: 0.6rem; align-items: end; flex-wrap: wrap; margin-bottom: 1rem; }
.new-group .helper { flex: 1; min-width: 12rem; }
.narrow input { width: 5.5rem; }
.group-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.6rem; }
.group-list > li { padding: 0.7rem 0.9rem; }
.group-list > li.inactive { opacity: 0.65; }
header { display: flex; justify-content: space-between; align-items: center; gap: 0.8rem; }
.title { background: none; border: 0; text-align: left; padding: 0; font-weight: 400; display: grid; gap: 0.1rem; }
.title span { font-size: 0.82rem; }
.row { display: flex; gap: 0.4rem; }
.body { margin-top: 0.8rem; }
.helper-line { margin: 0 0 0.6rem; }
.add-item { display: flex; gap: 0.6rem; align-items: end; flex-wrap: wrap; margin-top: 0.8rem; }
.num { white-space: nowrap; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }
tr.retired { opacity: 0.6; }
</style>
