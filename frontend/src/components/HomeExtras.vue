<!--
  Two panels the owner and manager get under the demo's Overview:
  the month so far, and the team today. Each loads only when the account's
  permissions allow it, and simply stays hidden otherwise.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import Spark from './Spark.vue'
import { api } from '../services/api'
import { kwacha, kwachaShort } from '../services/money'
import { stockAmount } from '../services/quantities'
import { session } from '../stores/session'

interface Month {
  month_label: string
  days: number
  sales_ngwee: number
  sales_change: number | null
  orders: number
  orders_change: number | null
  daily_average_ngwee: number
  by_day: number[]
  best_day: { day: string; sales_ngwee: number } | null
  profit: { income_ngwee: number; gross_margin_percent: number; profit_ngwee: number } | null
}
interface Team {
  staff: number
  on: { name: string; job: string; since: string }[]
  done: { name: string; job: string; since: string; until: string }[]
  not_in: { name: string; job: string }[]
  on_leave: { name: string; job: string }[]
  leave_pending: { name: string; kind: string; days: number; from: string; to: string }[]
  leave_pending_count: number
}

interface Store {
  value_ngwee: number; low_count: number; below_zero: number; on_order_count: number
  low: { name: string; unit: string; on_hand_milli: number; reorder_milli: number }[]
}
interface System {
  users_active: number; must_change: number; failed_24h: number; locked: string[]
  backup: { at: string; age_hours: number; count: number } | null
}
const store = ref<Store | null>(null)
const system = ref<System | null>(null)
const showStore = computed(() => session.canAny('inventory.view', 'inventory.adjust', 'purchases.manage'))
const showSystem = computed(() => session.canAny('staff.manage', 'settings.edit'))

const month = ref<Month | null>(null)
const team = ref<Team | null>(null)
const showMonth = computed(() => session.canAny('reports.view', 'books.view'))
const showTeam = computed(() => session.canAny('hr.view', 'attendance.manage'))

onMounted(async () => {
  if (showMonth.value) month.value = await api.get<Month>('/home/month').catch(() => null)
  if (showTeam.value) team.value = await api.get<Team>('/home/team').catch(() => null)
  if (showStore.value) store.value = await api.get<Store>('/home/stock').catch(() => null)
  if (showSystem.value) system.value = await api.get<System>('/home/system').catch(() => null)
})
</script>

<template>
  <div v-if="month || team || store || system" class="extras">
    <section v-if="month" class="card">
      <div class="card-head">
        <div>
          <h3>{{ month.month_label }} so far</h3>
          <p class="muted small">{{ month.days }} day{{ month.days === 1 ? '' : 's' }}, against the same days last month</p>
        </div>
        <RouterLink to="/reports">Analytics</RouterLink>
      </div>
      <div class="month-top">
        <div>
          <span class="month-big">{{ kwachaShort(month.sales_ngwee) }}</span>
          <span v-if="month.sales_change !== null" class="delta" :class="{ down: month.sales_change < 0 }">
            <Icon :name="month.sales_change < 0 ? 'down' : 'up'" />{{ Math.abs(month.sales_change) }}%
          </span>
        </div>
        <div class="month-spark"><Spark :values="month.by_day" /></div>
      </div>
      <ul class="home-list">
        <li><span>Paid orders</span><b class="num">{{ month.orders }}</b></li>
        <li><span>Average day</span><b class="num">{{ kwacha(month.daily_average_ngwee) }}</b></li>
        <li v-if="month.best_day"><span>Best day · {{ month.best_day.day }}</span><b class="num">{{ kwacha(month.best_day.sales_ngwee) }}</b></li>
        <li v-if="month.profit">
          <span>Profit in the books · {{ month.profit.gross_margin_percent }}% margin</span>
          <b class="num" :class="month.profit.profit_ngwee < 0 ? 'bad' : 'good'">{{ kwacha(month.profit.profit_ngwee) }}</b>
        </li>
      </ul>
    </section>

    <section v-if="team" class="card">
      <div class="card-head">
        <div>
          <h3>The team today</h3>
          <p class="muted small">{{ team.on.length }} of {{ team.staff }} clocked in</p>
        </div>
        <RouterLink to="/people">People</RouterLink>
      </div>
      <p v-if="!team.staff" class="home-empty">No staff on the list yet. Add them under People.</p>
      <ul class="home-list">
        <li v-for="p in team.on" :key="'on' + p.name" class="with-icon">
          <span class="home-dot" />
          <div><b>{{ p.name }}</b> <span class="muted">· {{ p.job }}</span></div>
          <span class="muted">since {{ p.since }}</span>
        </li>
        <li v-for="p in team.done" :key="'done' + p.name" class="with-icon">
          <span class="home-dot off" />
          <div>{{ p.name }} <span class="muted">· {{ p.job }}</span></div>
          <span class="muted">{{ p.since }}–{{ p.until }}</span>
        </li>
        <li v-for="p in team.on_leave" :key="'leave' + p.name" class="with-icon">
          <span class="home-dot off" />
          <div>{{ p.name }} <span class="muted">· {{ p.job }}</span></div>
          <span class="tag">On leave</span>
        </li>
        <li v-for="p in team.not_in" :key="'off' + p.name" class="with-icon">
          <span class="home-dot off" />
          <div class="muted">{{ p.name }} · {{ p.job }}</div>
          <span class="muted">not in</span>
        </li>
      </ul>
      <p v-if="team.leave_pending_count" class="info-note pending">
        {{ team.leave_pending_count }} leave request{{ team.leave_pending_count === 1 ? '' : 's' }} waiting:
        {{ team.leave_pending.map((l) => `${l.name}, ${l.from}${l.from !== l.to ? '–' + l.to : ''}`).join('; ') }}.
        <RouterLink to="/people">Decide</RouterLink>
      </p>
    </section>
    <section v-if="store" class="card">
      <div class="card-head">
        <div>
          <h3>Store room</h3>
          <p class="muted small">{{ kwachaShort(store.value_ngwee) }} of stock · {{ store.on_order_count }} order{{ store.on_order_count === 1 ? '' : 's' }} waiting to arrive</p>
        </div>
        <RouterLink to="/stock">Inventory</RouterLink>
      </div>
      <p v-if="store.below_zero" class="info-note">{{ store.below_zero }} item{{ store.below_zero === 1 ? ' shows' : 's show' }} less than nothing: a count puts it right.</p>
      <p v-if="!store.low.length" class="home-empty">Everything is above its reorder level.</p>
      <ul class="home-list">
        <li v-for="r in store.low.slice(0, 5)" :key="r.name">
          <span>{{ r.name }}</span>
          <b class="num" :class="{ bad: r.on_hand_milli <= 0 }">{{ stockAmount(r.unit, r.on_hand_milli) }} <span class="muted">of {{ stockAmount(r.unit, r.reorder_milli) }}</span></b>
        </li>
      </ul>
      <p v-if="store.low_count > 5" class="muted small">and {{ store.low_count - 5 }} more on the shopping list.</p>
    </section>

    <section v-if="system" class="card">
      <div class="card-head">
        <div>
          <h3>System</h3>
          <p class="muted small">{{ system.users_active }} active accounts</p>
        </div>
        <RouterLink to="/activity">Activity log</RouterLink>
      </div>
      <ul class="home-list">
        <li>
          <span>Last backup</span>
          <b class="num" :class="{ bad: !system.backup || system.backup.age_hours > 26 }">{{ system.backup ? system.backup.at : 'None yet' }}</b>
        </li>
        <li><span>Wrong passwords, last 24 hours</span><b class="num" :class="{ bad: system.failed_24h > 10 }">{{ system.failed_24h }}</b></li>
        <li><span>Still on a temporary password</span><b class="num" :class="{ bad: system.must_change }">{{ system.must_change }}</b></li>
      </ul>
      <p v-if="system.locked.length" class="info-note">Locked out for 15 minutes: {{ system.locked.join(', ') }}</p>
      <p v-if="!system.backup || system.backup.age_hours > 26" class="info-note">Take a backup from Settings, and check the nightly one is scheduled.</p>
    </section>
  </div>
</template>

<style scoped>
.extras { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); margin-top: 1rem; align-items: start; }
.month-top { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: .4rem; }
.month-big { font-family: var(--display); font-weight: 900; font-size: 1.9rem; margin-right: .5rem; }
.month-spark { width: 160px; max-width: 45%; overflow: hidden; }
.month-spark :deep(svg) { width: 100%; display: block; }
.pending { margin: .8rem 0 0; }
</style>
