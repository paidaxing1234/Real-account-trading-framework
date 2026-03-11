import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { wsClient } from '@/services/WebSocketClient'
import { strategyApi } from '@/api/strategy'

export const useStrategyStore = defineStore('strategy', () => {
  // 状态
  const strategies = ref([])
  const currentStrategy = ref(null)
  const loading = ref(false)
  const strategyLogFiles = ref([])
  const strategyLogs = ref([])
  const logsLoading = ref(false)
  const currentLogFilename = ref('')

  // WebSocket 连接后自动获取策略列表
  if (typeof window !== 'undefined') {
    wsClient.on('connected', () => {
      // 延迟获取，等待认证完成
      setTimeout(() => fetchStrategies(), 2000)
    })

    // 定时刷新策略列表（每10秒）
    setInterval(() => {
      if (wsClient.connected) {
        fetchStrategies()
      }
    }, 10000)
  }

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
      // 后端返回 strategy_id，前端使用 id
      const rawData = res.data || []
      strategies.value = rawData.map(s => ({
        ...s,
        id: s.strategy_id || s.id,
        name: s.strategy_id || s.name || '',
        account: s.account_id || '',
        type: s.exchange || 'unknown'
      }))
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
    return await strategyApi.startStrategy(id, config)
  }

  async function stopStrategy(id) {
    return await strategyApi.stopStrategy(id)
  }

  async function createStrategy(data) {
    const res = await strategyApi.createStrategy(data)
    await fetchStrategies()
    return res
  }

  async function fetchStrategyConfigs() {
    try {
      return await strategyApi.listStrategyConfigs()
    } catch (error) {
      console.error('获取策略配置列表失败:', error)
      return { data: [], success: false }
    }
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

  // 策略日志相关
  async function fetchStrategyLogFiles(strategyId = '') {
    logsLoading.value = true
    try {
      const res = await strategyApi.getStrategyLogFiles(strategyId)
      strategyLogFiles.value = res.data || []
      return res
    } finally {
      logsLoading.value = false
    }
  }

  async function fetchStrategyLogs(filename, tailLines = 200) {
    logsLoading.value = true
    currentLogFilename.value = filename
    try {
      const res = await strategyApi.getStrategyLogs(filename, tailLines)
      if (res.success && res.data) {
        strategyLogs.value = res.data.lines || []
      }
      return res
    } finally {
      logsLoading.value = false
    }
  }

  // 刷新当前日志
  async function refreshCurrentLogs(tailLines = 200) {
    if (currentLogFilename.value) {
      return await fetchStrategyLogs(currentLogFilename.value, tailLines)
    }
  }

  return {
    // 状态
    strategies,
    currentStrategy,
    loading,
    strategyLogFiles,
    strategyLogs,
    logsLoading,
    currentLogFilename,

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
    updateStrategyStatus,
    fetchStrategyConfigs,
    fetchStrategyLogFiles,
    fetchStrategyLogs,
    refreshCurrentLogs
  }
})

