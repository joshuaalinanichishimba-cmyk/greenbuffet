<!--
  The store room's home: what is running out, what is on order, what moved.

  Inventory staff do not need the day's sales. They need the shopping list
  before the supplier calls, the deliveries still to arrive, and a running
  view of what left the shelves, so a wrong count is caught the same day.
-->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import Icon from '../components/Icon.vue'
import { api } from '../services/api'
import { kwacha, kwachaShort } from '../services/money'
import { stockAmount } from '../services/quantities'
import { firstName, greeting, problemText } from '../services/home'
import { session } from '../stores/session'

interface StockHome {
  value_ngwee: number
  ingredients: number
  low_count: number
  below_zero: number
  low: { name: string; unit: string; on_hand_milli: number; reorder_milli: number }[]
  on_order: { id: string; number: string; supplier: string; total_ngwee: number; lines: number; days: number }[]
  on_order_count: number
  received_week: number
  moves: { name: string; unit: string; kind: string; quantity_milli: number; at: string; by: string }[]
  owed_ngwee: number
  overdue_ngwee: number
}

const data = ref<StockHome | null>(null)
const error = ref('')
let timer: number | undefined

async function load() {
  try {
    data.value = await api.get<StockHome>('/home/stock')
    error.value = ''
  } catch (problem) {
    error.value = problemText(problem, 'Could not load the store room.')
  }
}

const KIND: Record<string, string> = {
  sale: 'Sold', purchase: 'Delivered', adjustment: 'Adjusted', count: 'Counted',
  waste: 'Wasted', return: 'Returned', refund: 'Refund', cancel: 'Cancelled sale',
}

function fill(on: number, reorder: number) {
  return `${Math.max(4, Math.min(100, (on / reorder) * 100))}%`
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 60000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <AppShell>
    <div class="home-head">
      <div>
        <h1>{{ greeting() }}, {{ firstName(session.user.value?.name) }}</h1>
        <p class="lead">The store room: what is short, what is coming, what moved.</p>
      </div>
      <div class="actions">
        <RouterLink to="/purchases" class="btn-outline"><Icon name="truck" :size="18" /> Buying in</RouterLink>
        <RouterLink to="/stock" class="btn-primary"><Icon name="box" :size="18" /> Inventory</RouterLink>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="data">
      <section v-if="data.below_zero" class="card home-banner warn">
        <Icon name="alert" :size="22" />
        <div class="text">
          <b>{{ data.below_zero }} item{{ data.below_zero === 1 ? ' shows' : 's show' }} less than nothing</b>
          <span>More was sold than was ever counted in. A count puts the figure right.</span>
        </div>
        <RouterLink to="/stock" class="btn-outline">Count now</RouterLink>
      </section>

      <div class="kpis">
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="box" :size="18" /></span><span class="kpi-label">Stock value</span></div>
          <span class="kpi-value">{{ kwachaShort(data.value_ngwee) }}</span>
          <span class="kpi-sub">{{ data.ingredients }} ingredients, at cost</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon amber"><Icon name="alert" :size="18" /></span><span class="kpi-label">Below reorder level</span></div>
          <span class="kpi-value">{{ data.low_count }}</span>
          <span class="kpi-sub">{{ data.low_count ? 'On the shopping list' : 'Nothing to order' }}</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon brown"><Icon name="truck" :size="18" /></span><span class="kpi-label">On order</span></div>
          <span class="kpi-value">{{ data.on_order_count }}</span>
          <span class="kpi-sub">{{ data.received_week }} delivered this week</span>
        </div>
        <div class="kpi">
          <div class="kpi-top"><span class="kpi-icon"><Icon name="wallet" :size="18" /></span><span class="kpi-label">Owed to suppliers</span></div>
          <span class="kpi-value">{{ kwachaShort(data.owed_ngwee) }}</span>
          <span class="kpi-sub" :class="{ bad: data.overdue_ngwee }">{{ data.overdue_ngwee ? `${kwacha(data.overdue_ngwee)} over 30 days` : 'Nothing overdue' }}</span>
        </div>
      </div>

      <div class="split">
        <div class="col">
          <section class="card">
            <div class="card-head">
              <h3>Running low</h3>
              <RouterLink to="/stock">Shopping list</RouterLink>
            </div>
            <p v-if="!data.low.length" class="home-empty">Everything is above its reorder level.</p>
            <ul class="home-list">
              <li v-for="r in data.low" :key="r.name" class="low">
                <div>
                  <b>{{ r.name }}</b>
                  <div class="bar amber"><span :style="{ width: fill(r.on_hand_milli, r.reorder_milli) }" /></div>
                </div>
                <span class="num-pair">
                  <b class="num" :class="{ bad: r.on_hand_milli <= 0 }">{{ stockAmount(r.unit, r.on_hand_milli) }}</b>
                  <span class="muted"> of {{ stockAmount(r.unit, r.reorder_milli) }}</span>
                </span>
              </li>
            </ul>
          </section>

          <section class="card">
            <div class="card-head"><h3>What moved lately</h3><RouterLink to="/stock">Movements</RouterLink></div>
            <p v-if="!data.moves.length" class="home-empty">No movements yet.</p>
            <ul class="home-list">
              <li v-for="(m, i) in data.moves" :key="i">
                <div>
                  <b>{{ m.name }}</b> <span class="muted">· {{ KIND[m.kind] ?? m.kind }}</span>
                  <p class="sub">{{ m.at }}<template v-if="m.by"> · {{ m.by }}</template></p>
                </div>
                <b class="num" :class="m.quantity_milli < 0 ? 'bad' : 'good'">
                  {{ m.quantity_milli > 0 ? '+' : '' }}{{ stockAmount(m.unit, m.quantity_milli) }}
                </b>
              </li>
            </ul>
          </section>
        </div>

        <div class="col">
          <section class="card">
            <div class="card-head"><h3>Waiting to arrive</h3><RouterLink to="/purchases">Buying in</RouterLink></div>
            <p v-if="!data.on_order.length" class="home-empty">No orders out with suppliers.</p>
            <ul class="home-list">
              <li v-for="p in data.on_order" :key="p.id">
                <div>
                  <b>{{ p.number }}</b> <span class="muted">· {{ p.supplier }}</span>
                  <p class="sub">{{ p.lines }} line{{ p.lines === 1 ? '' : 's' }} · {{ p.days === 0 ? 'ordered today' : `${p.days} day${p.days === 1 ? '' : 's'} ago` }}</p>
                </div>
                <b class="num">{{ kwachaShort(p.total_ngwee) }}</b>
              </li>
            </ul>
          </section>

          <section class="card">
            <div class="card-head"><h3>Quick links</h3></div>
            <ul class="home-list">
              <li class="with-icon"><Icon name="package" /><RouterLink to="/purchases">Receive a delivery</RouterLink><span /></li>
              <li class="with-icon"><Icon name="sliders" /><RouterLink to="/stock">Count or adjust stock</RouterLink><span /></li>
              <li class="with-icon"><Icon name="menu" /><RouterLink to="/menu/ingredients">Ingredients and recipes</RouterLink><span /></li>
            </ul>
          </section>
        </div>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.low .bar { margin-top: .4rem; max-width: 260px; }
.num-pair { text-align: right; white-space: nowrap; }
.kpi-sub.bad { color: var(--danger); }
</style>
