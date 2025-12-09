import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as orderApi from '@/api/order'

export const useOrderStore = defineStore('order', () => {
  // 状态
  const orders = ref([])
  const trades = ref([])
  const positions = ref([])
  const loading = ref(false)
  
  // 计算属性
  const activeOrders = computed(() => 
    orders.value.filter(o => 
      ['SUBMITTED', 'ACCEPTED', 'PARTIALLY_FILLED'].includes(o.state)
    )
  )
  
  const filledOrders = computed(() => 
    orders.value.filter(o => o.state === 'FILLED')
  )
  
  const cancelledOrders = computed(() => 
    orders.value.filter(o => o.state === 'CANCELLED')
  )
  
  const totalPositionValue = computed(() => 
    positions.value.reduce((sum, pos) => 
      sum + (pos.notionalValue || 0), 0
    )
  )
  
  const totalUnrealizedPnL = computed(() => 
    positions.value.reduce((sum, pos) => 
      sum + (pos.unrealizedPnl || 0), 0
    )
  )
  
  // 操作
  async function fetchOrders(params) {
    loading.value = true
    try {
      const res = await orderApi.getOrders(params)
      orders.value = res.data || []
      return res
    } finally {
      loading.value = false
    }
  }
  
  async function fetchOrderDetail(id) {
    const res = await orderApi.getOrderDetail(id)
    return res
  }
  
  async function fetchTrades(params) {
    loading.value = true
    try {
      const res = await orderApi.getTrades(params)
      trades.value = res.data || []
      return res
    } finally {
      loading.value = false
    }
  }
  
  async function fetchPositions(params) {
    loading.value = true
    try {
      const res = await orderApi.getPositions(params)
      positions.value = res.data || []
      return res
    } finally {
      loading.value = false
    }
  }
  
  async function placeOrder(data) {
    const res = await orderApi.placeOrder(data)
    // 添加到订单列表
    if (res.data) {
      orders.value.unshift(res.data)
    }
    return res
  }
  
  async function cancelOrder(id) {
    const res = await orderApi.cancelOrder(id)
    // 更新订单状态
    const order = orders.value.find(o => o.id === id)
    if (order) {
      order.state = 'CANCELLED'
    }
    return res
  }
  
  async function batchCancelOrders(ids) {
    const res = await orderApi.batchCancelOrders(ids)
    // 批量更新订单状态
    ids.forEach(id => {
      const order = orders.value.find(o => o.id === id)
      if (order) {
        order.state = 'CANCELLED'
      }
    })
    return res
  }
  
  function updateOrderStatus(id, state, data = {}) {
    const order = orders.value.find(o => o.id === id)
    if (order) {
      order.state = state
      Object.assign(order, data)
    }
  }
  
  function addOrder(order) {
    orders.value.unshift(order)
  }
  
  function addTrade(trade) {
    trades.value.unshift(trade)
  }
  
  function updatePosition(symbol, data) {
    const position = positions.value.find(p => p.symbol === symbol)
    if (position) {
      Object.assign(position, data)
    } else {
      positions.value.push(data)
    }
  }
  
  return {
    // 状态
    orders,
    trades,
    positions,
    loading,
    
    // 计算属性
    activeOrders,
    filledOrders,
    cancelledOrders,
    totalPositionValue,
    totalUnrealizedPnL,
    
    // 操作
    fetchOrders,
    fetchOrderDetail,
    fetchTrades,
    fetchPositions,
    placeOrder,
    cancelOrder,
    batchCancelOrders,
    updateOrderStatus,
    addOrder,
    addTrade,
    updatePosition
  }
})

