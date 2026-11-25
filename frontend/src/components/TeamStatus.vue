<!--
  The owner's Team status card: who is registered, connected, on duty, on
  leave or suspended, from real records, with the people connected now.
  Connected comes from the heartbeat; on duty from clocking only.
-->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Avatar from './Avatar.vue'
import { api, type TeamCard } from '../services/api'

interface Summary {
  registered: number; online: number; away: number; lost: number; offline: number
  on_duty: number; on_leave: number; suspended: number; connected: TeamCard[]
}

const data = ref<Summary | null>(null)
let timer: number | undefined

async function load() {
  try {
    data.value = await api.get<Summary>('/team/summary')
  } catch {
    data.value = null
  }
}
onMounted(() => {
  load()
  timer = window.setInterval(load, 30000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <section v-if="data" class="card team-status">
    <div class="card-head">
      <div>
        <h3>Team status</h3>
        <p class="muted small">{{ data.registered }} active accounts</p>
      </div>
      <RouterLink to="/team">Team directory</RouterLink>
    </div>
    <div class="counts">
      <RouterLink to="/team" class="c"><b>{{ data.online }}</b><span><i class="d online" />Online</span></RouterLink>
      <RouterLink to="/team" class="c"><b>{{ data.away + data.lost }}</b><span><i class="d away" />Away</span></RouterLink>
      <RouterLink to="/team" class="c"><b>{{ data.offline }}</b><span><i class="d off" />Offline</span></RouterLink>
      <RouterLink to="/people" class="c"><b>{{ data.on_duty }}</b><span>On duty</span></RouterLink>
      <RouterLink to="/people" class="c"><b>{{ data.on_leave }}</b><span>On leave</span></RouterLink>
      <RouterLink to="/team" class="c" :class="{ bad: data.suspended }"><b>{{ data.suspended }}</b><span>Suspended</span></RouterLink>
    </div>
    <p v-if="!data.connected.length" class="home-empty">Nobody is connected right now.</p>
    <ul class="people">
      <li v-for="p in data.connected" :key="p.id">
        <RouterLink :to="`/team/${p.id}`">
          <Avatar :user-id="p.id" :name="p.name" :photo-id="p.photo_id" :size="34" :status="p.presence.status" />
          <span class="t"><b>{{ p.name }}</b><small>{{ p.role_label }} · {{ p.presence.label }}{{ p.duty.on_duty ? ' · on duty' : '' }}</small></span>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.counts { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: .5rem; margin: .25rem 0 1rem; }
.c {
  display: grid; gap: .1rem; padding: .6rem .7rem; border-radius: 12px; background: var(--leaf-soft);
  text-decoration: none; color: inherit;
}
.c b { font-family: var(--display); font-size: 1.45rem; color: var(--brown); line-height: 1.1; }
.c span { display: flex; align-items: center; gap: .3rem; color: var(--muted); font-size: .8rem; font-weight: 700; }
.c.bad b { color: var(--danger); }
.d { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.d.online { background: var(--green); }
.d.away { background: #e0a100; }
.d.off { background: #9aa09b; }
.people { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 220px), 1fr)); gap: .4rem; }
.people a { display: flex; align-items: center; gap: .6rem; padding: .4rem; border-radius: 10px; text-decoration: none; color: inherit; }
.people a:hover { background: var(--leaf-soft); }
.t { display: grid; min-width: 0; line-height: 1.25; }
.t b { font-size: .92rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t small { color: var(--muted); font-size: .78rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 700px) { .counts { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
</style>
