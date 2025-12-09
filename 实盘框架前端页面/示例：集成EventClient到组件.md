# 如何在Vue组件中使用EventClient

## 🎯 设计思想

**前端EventClient完全模仿C++的Component设计：**

```
C++ Component              →    Vue Component + EventClient
├─ start(engine)          →    onMounted + eventClient.start()
├─ register_listener()    →    eventClient.on('order', callback)
├─ on_order(order)        →    const callback = (order) => {...}
└─ stop()                 →    onUnmounted + eventClient.stop()
```

## 📝 使用示例

### 方式1：使用Composable（推荐）

```vue
<template>
  <div class="order-monitor">
    <div class="connection-status">
      <el-tag :type="connected ? 'success' : 'danger'">
        {{ connected ? '已连接' : '未连接' }}
      </el-tag>
    </div>
    
    <div class="latest-order" v-if="latestOrder">
      <h3>最新订单</h3>
      <p>交易对: {{ latestOrder.symbol }}</p>
      <p>状态: {{ latestOrder.state }}</p>
      <p>延迟: {{ latency }}ms</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useOrderStream } from '@/composables/useEventStream'

const latestOrder = ref(null)
const latency = ref(0)

// 监听订单更新（类似C++的register_listener）
const { connected } = useOrderStream((order) => {
  // 计算延迟
  const now = Date.now()
  const orderTime = new Date(order.timestamp).getTime()
  latency.value = now - orderTime
  
  // 更新显示
  latestOrder.value = order
  
  console.log('收到订单更新，延迟:', latency.value, 'ms')
})
</script>
```

### 方式2：直接使用EventClient

```vue
<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { eventClient } from '@/services/EventClient'
import { useOrderStore } from '@/stores/order'

const orderStore = useOrderStore()
const connected = ref(false)

// 订单更新处理器（类似C++的on_order回调）
const onOrderUpdate = (order) => {
  console.log('📦 收到订单更新:', order)
  
  // 更新Store
  orderStore.updateOrderStatus(order.id, order.state, order)
  
  // 触发通知
  if (order.state === 'FILLED') {
    ElNotification({
      title: '订单成交',
      message: `${order.symbol} ${order.side} 已成交`,
      type: 'success'
    })
  }
}

// 行情更新处理器（类似C++的on_ticker回调）
const onTickerUpdate = (ticker) => {
  console.log('📊 收到行情更新:', ticker.symbol, ticker.last_price)
  // 更新实时价格
}

// 组件启动（类似Component::start）
onMounted(() => {
  // 注册监听器
  eventClient.on('order', onOrderUpdate)
  eventClient.on('ticker', onTickerUpdate)
  eventClient.on('connected', () => connected.value = true)
  eventClient.on('disconnected', () => connected.value = false)
  
  // 启动连接
  if (!eventClient.isConnected()) {
    eventClient.start()
  }
})

// 组件停止（类似Component::stop）
onUnmounted(() => {
  // 取消监听器
  eventClient.off('order', onOrderUpdate)
  eventClient.off('ticker', onTickerUpdate)
})

// 发送命令（类似engine->put(order)）
const handleStartStrategy = async (strategyId) => {
  await eventClient.send('start_strategy', { id: strategyId })
}
</script>
```

### 方式3：在Dashboard中实时监控

```vue
<template>
  <div class="realtime-dashboard">
    <!-- 连接状态 -->
    <div class="connection-indicator">
      <el-badge :is-dot="true" :type="connected ? 'success' : 'danger'">
        <span>事件流</span>
      </el-badge>
      <span class="latency">延迟: {{ avgLatency }}ms</span>
    </div>
    
    <!-- 实时订单流 -->
    <div class="order-stream">
      <h3>实时订单 (延迟: {{ orderLatency }}ms)</h3>
      <div v-for="order in recentOrders" :key="order.id" class="order-item">
        {{ order.symbol }} - {{ order.state }}
      </div>
    </div>
    
    <!-- 实时行情 -->
    <div class="ticker-stream">
      <h3>实时行情 (延迟: {{ tickerLatency }}ms)</h3>
      <div v-for="ticker in tickers" :key="ticker.symbol">
        {{ ticker.symbol }}: {{ ticker.last_price }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useOrderStream, useTickerStream } from '@/composables/useEventStream'

const recentOrders = ref([])
const tickers = ref([])
const orderLatency = ref(0)
const tickerLatency = ref(0)

// 订单流
const { connected: orderConnected } = useOrderStream((order) => {
  // 计算延迟
  orderLatency.value = Date.now() - new Date(order.timestamp).getTime()
  
  // 添加到列表
  recentOrders.value.unshift(order)
  if (recentOrders.value.length > 10) {
    recentOrders.value.pop()
  }
})

// 行情流
const { connected: tickerConnected } = useTickerStream((ticker) => {
  tickerLatency.value = Date.now() - new Date(ticker.timestamp).getTime()
  
  // 更新行情
  const index = tickers.value.findIndex(t => t.symbol === ticker.symbol)
  if (index > -1) {
    tickers.value[index] = ticker
  } else {
    tickers.value.push(ticker)
  }
})

const connected = computed(() => orderConnected.value || tickerConnected.value)
const avgLatency = computed(() => 
  Math.round((orderLatency.value + tickerLatency.value) / 2)
)
</script>

<style scoped>
.connection-indicator {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
}

.latency {
  font-size: 12px;
  color: #67c23a;
  font-weight: bold;
}

.order-item {
  padding: 5px;
  border-bottom: 1px solid #eee;
  animation: slideIn 0.3s;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(-10px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
```

---

## 🔧 Store集成

### 自动更新Store

```javascript
// src/stores/order.js
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { eventClient } from '@/services/EventClient'

export const useOrderStore = defineStore('order', () => {
  const orders = ref([])
  
  // 初始化时注册事件监听
  function init() {
    // 监听订单更新（类似C++的register_listener）
    eventClient.on('order', (order) => {
      updateOrderStatus(order.id, order.state, order)
    })
    
    // 启动事件流
    if (!eventClient.isConnected()) {
      eventClient.start()
    }
  }
  
  function updateOrderStatus(id, state, data) {
    const order = orders.value.find(o => o.id === id)
    if (order) {
      order.state = state
      Object.assign(order, data)
    } else {
      // 新订单，添加到列表
      orders.value.unshift(data)
    }
  }
  
  return {
    orders,
    init,
    updateOrderStatus
  }
})
```

### 在main.js中自动启动

```javascript
// src/main.js
import { eventClient } from '@/services/EventClient'
import { useOrderStore } from '@/stores/order'
import { useAccountStore } from '@/stores/account'

const app = createApp(App)
app.use(pinia)

// 初始化所有Store
const orderStore = useOrderStore()
const accountStore = useAccountStore()

orderStore.init()
accountStore.init()

// 全局启动事件流
eventClient.start()

app.mount('#app')
```

---

## 📊 性能测试

### 延迟测试方法

```javascript
// 在组件中测试延迟
eventClient.on('order', (order) => {
  const serverTime = new Date(order.timestamp).getTime()
  const clientTime = Date.now()
  const latency = clientTime - serverTime
  
  console.log('订单延迟:', latency, 'ms')
  
  // 统计
  latencies.push(latency)
  if (latencies.length > 100) {
    const avg = latencies.reduce((a, b) => a + b) / latencies.length
    console.log('平均延迟:', avg, 'ms')
  }
})
```

### 预期性能

```
本地开发环境:
- 平均延迟: 2-5ms
- P99延迟: 8-10ms
- 吞吐量: 1000+ events/s

生产环境:
- 平均延迟: 5-15ms  
- P99延迟: 20-30ms
- 吞吐量: 500+ events/s
```

---

## 🚀 快速开始

### 1. 安装EventClient

文件已创建在：`src/services/EventClient.js`

### 2. 在main.js中启动

```javascript
import EventClientPlugin, { eventClient } from '@/services/EventClient'

app.use(EventClientPlugin)

// 全局启动
eventClient.start()
```

### 3. 在组件中使用

```vue
<script setup>
import { useOrderStream } from '@/composables/useEventStream'

// 自动监听订单更新
useOrderStream((order) => {
  console.log('新订单:', order)
})
</script>
```

---

**完成！前端EventClient已经准备好，完全模仿C++的Component设计！** ✨

