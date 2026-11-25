<!--
  A round profile picture, or the person's initials when there is none, with
  an optional small status dot: green online, amber away, grey offline.
  Red is kept for a suspended account.
-->
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { getToken, type PresenceStatus } from '../services/api'

const props = withDefaults(defineProps<{
  userId?: string
  name: string
  photoId?: string | null
  size?: number
  status?: PresenceStatus | null
  suspended?: boolean
}>(), { size: 36, status: null, photoId: null, userId: '', suspended: false })

const url = ref('')
const cache = (window as unknown as { __gbPhotos?: Map<string, string> })
cache.__gbPhotos ??= new Map()

async function load() {
  url.value = ''
  if (!props.photoId || !props.userId) return
  const key = `${props.userId}:${props.photoId}`
  const held = cache.__gbPhotos!.get(key)
  if (held) {
    url.value = held
    return
  }
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
  try {
    const r = await fetch(`${base}/profile/photo/${props.userId}`, { headers: { Authorization: `Bearer ${getToken()}` } })
    if (!r.ok) return
    const made = URL.createObjectURL(await r.blob())
    cache.__gbPhotos!.set(key, made)
    url.value = made
  } catch {
    /* initials stay */
  }
}

const initials = () => (props.name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('')

onMounted(load)
watch(() => [props.userId, props.photoId], load)
</script>

<template>
  <span class="av" :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.38)}px` }">
    <img v-if="url" :src="url" alt="" />
    <span v-else>{{ initials() }}</span>
    <i
      v-if="status || suspended"
      class="dot"
      :class="suspended ? 'blocked' : status"
      :style="{ width: `${Math.max(8, Math.round(size * 0.28))}px`, height: `${Math.max(8, Math.round(size * 0.28))}px` }"
      :title="suspended ? 'Suspended' : status ?? ''"
    />
  </span>
</template>

<style scoped>
.av {
  position: relative; flex: none; display: inline-grid; place-items: center; border-radius: 50%;
  background: var(--leaf); color: var(--green-deep); font-weight: 800;
  font-family: var(--display); letter-spacing: .02em;
}
.av img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.dot {
  position: absolute; right: -1px; bottom: -1px; border-radius: 50%;
  border: 2px solid var(--paper); background: #9aa09b;
}
.dot.online { background: var(--green); }
.dot.away { background: #e0a100; }
.dot.lost { background: transparent; border-color: #e0a100; }
.dot.offline, .dot.unknown { background: #9aa09b; }
.dot.blocked { background: var(--danger); }
</style>
