<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { ApiError, api, type PermissionInfo, type Role } from '../services/api'

const roles = ref<Role[]>([])
const permissions = ref<PermissionInfo[]>([])
const selectedId = ref('')
const draft = ref<Set<string>>(new Set())
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref('')

const newRole = reactive({ label: '', open: false, saving: false })

const selected = computed(() => roles.value.find((r) => r.id === selectedId.value) ?? null)

const areas = computed(() => {
  const groups = new Map<string, PermissionInfo[]>()
  for (const p of permissions.value) {
    const list = groups.get(p.area) ?? []
    list.push(p)
    groups.set(p.area, list)
  }
  return [...groups.entries()].map(([area, items]) => ({ area, items }))
})

const changed = computed(() => {
  if (!selected.value) return false
  const before = [...selected.value.permissions].sort().join(',')
  const after = [...draft.value].sort().join(',')
  return before !== after
})

async function load() {
  loading.value = true
  try {
    const [r, p] = await Promise.all([api.roles(), api.permissions()])
    roles.value = r
    permissions.value = p
    if (!selectedId.value) select(r[0]?.id ?? '')
    else select(selectedId.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load roles.'
  } finally {
    loading.value = false
  }
}
onMounted(load)

function select(id: string) {
  selectedId.value = id
  saved.value = ''
  const role = roles.value.find((r) => r.id === id)
  draft.value = new Set(role?.permissions ?? [])
}

function toggle(code: string) {
  const next = new Set(draft.value)
  next.has(code) ? next.delete(code) : next.add(code)
  draft.value = next
  saved.value = ''
}

function toggleArea(items: PermissionInfo[], on: boolean) {
  const next = new Set(draft.value)
  for (const item of items) on ? next.add(item.code) : next.delete(item.code)
  draft.value = next
  saved.value = ''
}

async function save() {
  if (!selected.value) return
  error.value = ''
  saving.value = true
  try {
    const updated = await api.saveRole(selected.value.id, [...draft.value])
    roles.value = roles.value.map((r) => (r.id === updated.id ? updated : r))
    draft.value = new Set(updated.permissions)
    saved.value = `${updated.label} saved. Staff on this role see the change next time they sign in.`
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not save the role.'
  } finally {
    saving.value = false
  }
}

async function createRole() {
  error.value = ''
  if (newRole.label.trim().length < 3) {
    error.value = 'Give the new role a name of at least three letters.'
    return
  }
  newRole.saving = true
  try {
    const created = await api.createRole(newRole.label.trim(), '', [])
    newRole.label = ''
    newRole.open = false
    await load()
    select(created.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not create the role.'
  } finally {
    newRole.saving = false
  }
}
</script>

<template>
  <AppShell>
    <h1>Roles</h1>
    <p class="lead">
      A role is a set of permissions. Change a role and everyone on it is affected, so the quickest
      way to give one person extra access is usually a role of their own.
    </p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="saved" class="notice">{{ saved }}</p>
    <p v-if="loading" class="muted">Loading…</p>

    <div v-else class="layout">
      <aside>
        <ul class="role-list">
          <li v-for="r in roles" :key="r.id">
            <button
              class="role-button"
              :class="{ current: r.id === selectedId }"
              @click="select(r.id)"
            >
              <b>{{ r.label }}</b>
              <span class="muted">{{ r.permissions.length }} permissions</span>
            </button>
          </li>
        </ul>

        <div v-if="newRole.open" class="new-role">
          <label class="field">
            New role name
            <input v-model="newRole.label" type="text" placeholder="Supervisor" />
          </label>
          <div class="row">
            <button class="btn-primary btn-small" :disabled="newRole.saving" @click="createRole">Create</button>
            <button class="btn-quiet btn-small" @click="newRole.open = false">Cancel</button>
          </div>
        </div>
        <button v-else class="btn-quiet btn-small" @click="newRole.open = true">Add a role</button>
      </aside>

      <section v-if="selected" class="panel editor">
        <header class="editor-head">
          <div>
            <b>{{ selected.label }}</b>
            <p class="muted">{{ selected.description || 'No description' }}</p>
          </div>
          <button class="btn-primary" :disabled="!changed || saving" @click="save">
            {{ saving ? 'Saving…' : changed ? 'Save changes' : 'Saved' }}
          </button>
        </header>

        <div v-for="group in areas" :key="group.area" class="area">
          <div class="area-head">
            <b>{{ group.area }}</b>
            <span class="row">
              <button class="btn-quiet btn-small" @click="toggleArea(group.items, true)">All</button>
              <button class="btn-quiet btn-small" @click="toggleArea(group.items, false)">None</button>
            </span>
          </div>
          <ul class="perms">
            <li v-for="p in group.items" :key="p.code">
              <label>
                <input type="checkbox" :checked="draft.has(p.code)" @change="toggle(p.code)" />
                <span>{{ p.label }}</span>
              </label>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.layout { display: grid; gap: 1rem; grid-template-columns: 1fr; align-items: start; }
.role-list { list-style: none; margin: 0 0 0.7rem; padding: 0; display: grid; gap: 0.35rem; }
.role-button {
  width: 100%;
  text-align: left;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.55rem 0.75rem;
  display: grid;
  gap: 0.1rem;
  font-weight: 400;
}
.role-button b { display: block; }
.role-button.current { border-color: var(--green-mid); box-shadow: inset 3px 0 0 var(--green-mid); }
.new-role { display: grid; gap: 0.5rem; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 0.7rem; }
.row { display: flex; gap: 0.4rem; flex-wrap: wrap; }
.editor-head { display: flex; gap: 1rem; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.editor-head p { margin: 0.1rem 0 0; }
.area { border-top: 1px solid var(--line); margin-top: 1rem; padding-top: 0.8rem; }
.area-head { display: flex; justify-content: space-between; align-items: center; gap: 0.6rem; }
.perms { list-style: none; margin: 0.6rem 0 0; padding: 0; display: grid; gap: 0.35rem; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }
.perms label { display: flex; gap: 0.5rem; align-items: center; font-size: 0.9rem; }
.perms input { width: 17px; height: 17px; accent-color: var(--green-mid); }

@media (min-width: 860px) {
  .layout { grid-template-columns: 230px 1fr; }
}
</style>
