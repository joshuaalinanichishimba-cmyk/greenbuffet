<!--
  Where a customer lands after ordering, and the link they keep.

  The page refreshes itself every twenty seconds. That is often enough that
  somebody waiting for food sees it move, and rare enough that a hundred
  people watching at lunchtime do not trouble the till.
-->
<template>
  <div class="shop">
    <header class="shop-bar">
      <div class="mark">GB</div>
      <div class="who">
        <strong>The Green Buffet</strong>
        <span>Your order</span>
      </div>
      <router-link class="call" to="/order">Order again</router-link>
    </header>

    <div class="shop-body" style="padding-top: 1.6rem; padding-bottom: 3rem">
      <p v-if="error" class="error">{{ error }}</p>
      <p v-else-if="!order" class="muted">Finding your order…</p>

      <template v-else>
        <h1 style="margin: 0 0 0.2rem; font-size: 1.6rem">{{ headline }}</h1>
        <p class="muted" style="margin: 0 0 0.4rem">
          Order {{ order.number }} · placed {{ placedAt }}
        </p>

        <div v-if="order.status === 'rejected'" class="error">
          {{ order.reject_reason || 'The restaurant could not take this order.' }}
        </div>

        <div v-else class="track-steps">
          <div
            v-for="step in steps"
            :key="step.key"
            class="track-step"
            :class="{ done: stepState(step.key) === 'done', now: stepState(step.key) === 'now' }"
          >
            <span class="dot">{{ stepState(step.key) === 'done' ? '✓' : '' }}</span>
            <div>
              <strong>{{ step.title }}</strong>
              <div class="muted">{{ step.detail }}</div>
            </div>
          </div>
        </div>

        <div class="panel" style="margin-top: 1.2rem">
          <h2 style="margin: 0 0 0.6rem; font-size: 1rem">What you ordered</h2>
          <div v-for="(line, index) in order.lines" :key="index" class="basket-line">
            <div class="what"><strong>{{ line }}</strong></div>
          </div>
          <div class="totals">
            <div v-if="order.delivery_fee_ngwee">
              <span>Includes delivery{{ order.zone_name ? ` to ${order.zone_name}` : '' }}</span>
              <span>{{ kwacha(order.delivery_fee_ngwee) }}</span>
            </div>
            <div class="sum">
              <span>{{ order.paid ? 'Paid' : 'To pay' }}</span>
              <span>{{ kwacha(order.total_ngwee) }}</span>
            </div>
          </div>
          <p v-if="order.address" class="muted">Delivering to {{ order.address }}</p>
          <p v-if="!order.paid" class="muted">
            Pay when you {{ order.fulfilment === 'delivery' ? 'receive the food' : 'collect' }}.
          </p>
        </div>

        <p class="muted" style="margin-top: 1rem">
          Keep this page. It is the only link to this order, and it updates by itself.
        </p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { kwacha } from '../services/money'
import { publicApi, type TrackedOrder } from '../services/publicApi'

const route = useRoute()
const order = ref<TrackedOrder | null>(null)
const error = ref('')
let timer: number | undefined

const ORDER: string[] = ['placed', 'accepted', 'cooking', 'ready', 'on_the_way', 'completed']

const steps = computed(() => {
  const delivery = order.value?.fulfilment === 'delivery'
  const minutes = order.value?.minutes ?? 15
  const list = [
    { key: 'placed', title: 'Order sent', detail: 'We have it. Someone is looking at it now.' },
    { key: 'cooking', title: 'Being cooked', detail: `About ${minutes} minutes.` },
    {
      key: 'ready',
      title: delivery ? 'Ready for the rider' : 'Ready for collection',
      detail: delivery ? 'Packed and waiting to go out.' : 'Come to the counter at Liberty Mall.',
    },
  ]
  if (delivery) {
    list.push({ key: 'on_the_way', title: 'On the way', detail: 'The rider is bringing it to you.' })
  }
  list.push({
    key: 'completed',
    title: delivery ? 'Delivered' : 'Collected',
    detail: 'Enjoy it. Thank you for ordering.',
  })
  return list
})

const headline = computed(() => {
  switch (order.value?.status) {
    case 'placed':
      return 'We have your order'
    case 'accepted':
    case 'cooking':
      return 'Your food is being cooked'
    case 'ready':
      return order.value?.fulfilment === 'delivery' ? 'Ready to go out' : 'Ready for collection'
    case 'on_the_way':
      return 'On the way to you'
    case 'completed':
      return 'All done'
    case 'rejected':
      return 'We could not take this one'
    default:
      return 'Your order'
  }
})

const placedAt = computed(() => {
  if (!order.value?.placed_at) return ''
  const when = new Date(order.value.placed_at)
  return when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
})

function stepState(key: string): 'done' | 'now' | 'later' {
  const current = order.value?.status ?? 'placed'
  // 'accepted' and 'cooking' are the same thing to a customer waiting.
  const normalised = current === 'accepted' ? 'cooking' : current
  const at = ORDER.indexOf(normalised)
  const mine = ORDER.indexOf(key)
  if (mine < at) return 'done'
  if (mine === at) return 'now'
  return 'later'
}

async function load() {
  try {
    order.value = await publicApi.track(String(route.params.token ?? ''))
    error.value = ''
  } catch (problem) {
    error.value = problem instanceof Error ? problem.message : 'That order could not be found.'
  }
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 20000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>
