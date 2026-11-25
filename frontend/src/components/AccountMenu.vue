<!--
  Top right of every screen: the notices bell and the person's avatar.

  The avatar opens the profile menu: who is signed in, their status, and the
  ways into their profile, security, notices and activity, the lock screen
  and signing out. The bell shows unread account and security notices; the
  heartbeat keeps its count fresh without polling of its own.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Avatar from './Avatar.vue'
import Icon from './Icon.vue'
import { api, type Notice } from '../services/api'
import { ago, lockNow } from '../services/presence'
import { session } from '../stores/session'

const props = withDefaults(defineProps<{ dark?: boolean }>(), { dark: false })

const router = useRouter()
const open = ref<'' | 'me' | 'bell'>('')
const notices = ref<Notice[]>([])
const root = ref<HTMLElement | null>(null)

const me = computed(() => session.user.value)
const status = computed(() => (session.connected.value ? 'online' : 'lost'))
const statusLabel = computed(() => (session.connected.value ? 'Online' : 'Reconnecting…'))

async function toggleBell() {
  open.value = open.value === 'bell' ? '' : 'bell'
  if (open.value === 'bell') {
    try {
      notices.value = await api.get<Notice[]>('/notifications?limit=8')
    } catch {
      notices.value = []
    }
  }
}

async function readAll() {
  await api.post('/notifications/read', { all: true })
  session.unread.value = 0
  notices.value = notices.value.map((n) => ({ ...n, read: true }))
}

async function openNotice(n: Notice) {
  if (!n.read) {
    await api.post('/notifications/read', { ids: [n.id] }).catch(() => undefined)
    session.unread.value = Math.max(0, session.unread.value - 1)
  }
  open.value = ''
  if (n.link) router.push(n.link)
}

function go(to: string) {
  open.value = ''
  router.push(to)
}

async function lock() {
  open.value = ''
  await lockNow()
}

async function signOut() {
  open.value = ''
  await session.signOutEverywhere()
  router.replace('/login')
}

function outside(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = ''
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = ''
}
onMounted(() => {
  document.addEventListener('click', outside)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', outside)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div ref="root" class="acct" :class="{ dark: props.dark }">
    <button class="bell" :aria-label="`Notices${session.unread.value ? `, ${session.unread.value} unread` : ''}`"
            :aria-expanded="open === 'bell'" @click.stop="toggleBell">
      <Icon name="bell" :size="20" />
      <b v-if="session.unread.value" class="count">{{ session.unread.value > 9 ? '9+' : session.unread.value }}</b>
    </button>
    <button class="me" :aria-expanded="open === 'me'" aria-label="Your account" @click.stop="open = open === 'me' ? '' : 'me'">
      <Avatar v-if="me" :user-id="me.id" :name="me.name" :photo-id="me.photo_id" :size="36" :status="status" />
    </button>

    <div v-if="open === 'bell'" class="drop bell-drop" role="dialog" aria-label="Notices">
      <div class="drop-head">
        <b>Notices</b>
        <button v-if="notices.some((n) => !n.read)" class="link" @click="readAll">Mark all read</button>
      </div>
      <p v-if="!notices.length" class="empty">No notices. Account and security events appear here.</p>
      <button v-for="n in notices" :key="n.id" class="notice" :class="{ unread: !n.read, warn: n.level === 'warn' }" @click="openNotice(n)">
        <b>{{ n.title }}</b>
        <span v-if="n.body">{{ n.body }}</span>
        <small>{{ ago(n.at) }}</small>
      </button>
      <button class="all" @click="go('/profile/notifications')">All notices and preferences</button>
    </div>

    <div v-if="open === 'me' && me" class="drop me-drop" role="menu" aria-label="Your account">
      <div class="who">
        <Avatar :user-id="me.id" :name="me.name" :photo-id="me.photo_id" :size="48" :status="status" />
        <div>
          <b>{{ me.name }}</b>
          <span>{{ me.role_label }}</span>
          <span class="state" :class="status">{{ statusLabel }}</span>
        </div>
      </div>
      <button role="menuitem" @click="go('/profile')"><Icon name="user" :size="18" /> My profile</button>
      <button role="menuitem" @click="go('/profile/overview?edit=1')"><Icon name="settings" :size="18" /> Account settings</button>
      <button role="menuitem" @click="go('/profile/security')"><Icon name="lock" :size="18" /> Security settings</button>
      <button role="menuitem" @click="go('/profile/notifications')"><Icon name="bell" :size="18" /> Notification preferences</button>
      <button role="menuitem" @click="go('/profile/activity')"><Icon name="chart" :size="18" /> My activity</button>
      <hr />
      <button role="menuitem" @click="lock"><Icon name="lock" :size="18" /> Lock screen</button>
      <button role="menuitem" class="out" @click="signOut"><Icon name="logout" :size="18" /> Sign out</button>
    </div>
  </div>
</template>

<style scoped>
.acct { position: relative; display: flex; align-items: center; gap: .35rem; }
.bell, .me {
  position: relative; display: grid; place-items: center; border: 0; background: transparent; cursor: pointer;
  border-radius: 999px; padding: 3px; color: var(--ink);
}
.bell { width: 42px; height: 42px; }
.bell:hover, .me:hover { background: var(--leaf-soft); }
.dark .bell { color: #fff; }
.dark .bell:hover, .dark .me:hover { background: #ffffff1f; }
.count {
  position: absolute; top: 3px; right: 2px; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 999px;
  background: var(--danger); color: #fff; font-size: .7rem; line-height: 18px; text-align: center;
}
.drop {
  position: absolute; top: calc(100% + 8px); right: 0; z-index: 60; width: min(320px, calc(100vw - 24px));
  background: var(--paper); color: var(--ink); border: 1px solid var(--line); border-radius: 14px;
  box-shadow: var(--shadow); padding: .5rem; display: grid; gap: 2px;
}
.who { display: flex; gap: .75rem; align-items: center; padding: .5rem .5rem .75rem; border-bottom: 1px solid var(--line); margin-bottom: .35rem; }
.who div { display: grid; line-height: 1.3; min-width: 0; }
.who b { font-family: var(--display); color: var(--brown); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.who span { color: var(--muted); font-size: .88rem; }
.state { display: inline-flex; align-items: center; gap: .35rem; font-weight: 700; }
.state::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--green); }
.state.lost::before { background: #e0a100; }
.me-drop button, .all {
  display: flex; align-items: center; gap: .65rem; width: 100%; min-height: 42px; padding: .45rem .6rem;
  border: 0; border-radius: 10px; background: transparent; cursor: pointer; text-align: left; font-weight: 600;
}
.me-drop button:hover, .all:hover { background: var(--leaf-soft); }
.me-drop .out { color: var(--danger); }
hr { border: 0; border-top: 1px solid var(--line); margin: .3rem 0; width: 100%; }
.drop-head { display: flex; justify-content: space-between; align-items: center; padding: .35rem .5rem .5rem; }
.drop-head b { font-family: var(--display); color: var(--brown); }
.link { border: 0; background: none; color: var(--green-deep); font-weight: 700; cursor: pointer; }
.empty { color: var(--muted); padding: .5rem; font-size: .9rem; }
.notice {
  display: grid; gap: .1rem; text-align: left; border: 0; background: transparent; border-radius: 10px;
  padding: .55rem .6rem; cursor: pointer; border-left: 3px solid transparent;
}
.notice:hover { background: var(--leaf-soft); }
.notice.unread { border-left-color: var(--green); background: color-mix(in srgb, var(--leaf-soft) 60%, transparent); }
.notice.warn.unread { border-left-color: #e0a100; }
.notice span { color: var(--muted); font-size: .86rem; }
.notice small { color: var(--muted); font-size: .76rem; }
.all { justify-content: center; color: var(--green-deep); border-top: 1px solid var(--line); border-radius: 0 0 10px 10px; margin-top: .25rem; }
</style>
