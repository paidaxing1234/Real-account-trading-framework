import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { wsClient } from '@/services/WebSocketClient'
import { accountApi } from '@/api/account'

export const useAccountStore = defineStore('account', () => {
  // 状态
  const accounts = ref([])
  const currentAccount = ref(null)
  const loading = ref(false)
  
  // 监听WebSocket快照
  if (typeof window !== 'undefined') {
    wsClient.on('snapshot', ({ data }) => {
      if (data.accounts) {
        accounts.value = data.accounts
      }
    })
  }
  
  // 计算属性
  const totalEquity = computed(() => 
    accounts.value.reduce((sum, acc) => sum + (acc.equity || 0), 0)
  )
  
  const totalPnL = computed(() => 
    accounts.value.reduce((sum, acc) => sum + (acc.unrealizedPnl || 0), 0)
  )
  
  const activeAccounts = computed(() => 
    accounts.value.filter(acc => acc.status === 'active')
  )
  
  // 操作
  async function fetchAccounts(params) {
    loading.value = true
    try {
      const res = await accountApi.getAccounts(params)
      accounts.value = res.data || []
      return res
    } finally {
      loading.value = false
    }
  }
  
  async function fetchAccountDetail(id) {
    loading.value = true
    try {
      const res = await accountApi.getAccountDetail(id)
      currentAccount.value = res.data
      return res
    } finally {
      loading.value = false
    }
  }
  
  async function fetchAccountBalance(id, currency) {
    const res = await accountApi.getAccountBalance(id, currency)
    // 更新本地账户余额
    const account = accounts.value.find(acc => acc.id === id)
    if (account && res.data) {
      account.balance = res.data
    }
    return res
  }
  
  async function fetchAccountPositions(id, params) {
    const res = await accountApi.getAccountPositions(id, params)
    return res
  }
  
  async function fetchAccountEquityCurve(id, timeRange) {
    const res = await accountApi.getAccountEquityCurve(id, timeRange)
    return res
  }
  
  async function addAccount(data) {
    const res = await accountApi.addAccount(data)
    await fetchAccounts()
    return res
  }
  
  async function updateAccount(id, data) {
    const res = await accountApi.updateAccount(id, data)
    // 更新本地状态
    const index = accounts.value.findIndex(acc => acc.id === id)
    if (index !== -1) {
      accounts.value[index] = { ...accounts.value[index], ...data }
    }
    return res
  }
  
  async function deleteAccount(id) {
    const res = await accountApi.deleteAccount(id)
    accounts.value = accounts.value.filter(acc => acc.id !== id)
    return res
  }
  
  async function syncAccount(id) {
    const res = await accountApi.syncAccount(id)
    await fetchAccountDetail(id)
    return res
  }
  
  function updateAccountData(id, data) {
    const account = accounts.value.find(acc => acc.id === id)
    if (account) {
      Object.assign(account, data)
    }
  }
  
  return {
    // 状态
    accounts,
    currentAccount,
    loading,
    
    // 计算属性
    totalEquity,
    totalPnL,
    activeAccounts,
    
    // 操作
    fetchAccounts,
    fetchAccountDetail,
    fetchAccountBalance,
    fetchAccountPositions,
    fetchAccountEquityCurve,
    addAccount,
    updateAccount,
    deleteAccount,
    syncAccount,
    updateAccountData
  }
})

