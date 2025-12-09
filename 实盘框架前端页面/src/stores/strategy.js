import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as strategyApi from '@/api/strategy'

export const useStrategyStore = defineStore('strategy', () => {
  // 状态
  const strategies = ref([])
  const currentStrategy = ref(null)
  const loading = ref(false)
  
  // 计算属性
  const runningStrategies = computed(() => 
    strategies.value.filter(s => s.status === 'running')
  )
  
  const stoppedStrategies = computed(() => 
    strategies.value.filter(s => s.status === 'stopped')
  )
  
  const pendingStrategies = computed(() => 
    strategies.value.filter(s => s.status === 'pending')
  )
  
  const errorStrategies = computed(() => 
    strategies.value.filter(s => s.status === 'error')
  )
  
  // 操作
  async function fetchStrategies(params) {
    loading.value = true
    try {
      const res = await strategyApi.getStrategies(params)
      strategies.value = res.data || []
      return res
    } finally {
      loading.value = false
    }
  }
  
  async function fetchStrategyDetail(id) {
    loading.value = true
    try {
      const res = await strategyApi.getStrategyDetail(id)
      currentStrategy.value = res.data
      return res
    } finally {
      loading.value = false
    }
  }
  
  async function startStrategy(id, config) {
    const res = await strategyApi.startStrategy(id, config)
    // 更新本地状态
    const strategy = strategies.value.find(s => s.id === id)
    if (strategy) {
      strategy.status = 'running'
    }
    return res
  }
  
  async function stopStrategy(id) {
    const res = await strategyApi.stopStrategy(id)
    // 更新本地状态
    const strategy = strategies.value.find(s => s.id === id)
    if (strategy) {
      strategy.status = 'stopped'
    }
    return res
  }
  
  async function createStrategy(data) {
    const res = await strategyApi.createStrategy(data)
    await fetchStrategies()
    return res
  }
  
  async function deleteStrategy(id) {
    const res = await strategyApi.deleteStrategy(id)
    strategies.value = strategies.value.filter(s => s.id !== id)
    return res
  }
  
  function updateStrategyStatus(id, status) {
    const strategy = strategies.value.find(s => s.id === id)
    if (strategy) {
      strategy.status = status
    }
  }
  
  return {
    // 状态
    strategies,
    currentStrategy,
    loading,
    
    // 计算属性
    runningStrategies,
    stoppedStrategies,
    pendingStrategies,
    errorStrategies,
    
    // 操作
    fetchStrategies,
    fetchStrategyDetail,
    startStrategy,
    stopStrategy,
    createStrategy,
    deleteStrategy,
    updateStrategyStatus
  }
})

