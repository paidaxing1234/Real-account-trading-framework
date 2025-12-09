/**
 * Mock API 服务
 * 在开发环境中使用模拟数据
 */

import {
  mockStrategies,
  mockAccounts,
  mockOrders,
  mockPositions,
  mockApiResponse,
  saveMockData
} from '@/mock'

// 是否使用Mock数据
const USE_MOCK = import.meta.env.DEV || true

// 策略相关Mock
export const mockStrategyApi = {
  async getStrategies() {
    if (!USE_MOCK) return null
    return mockApiResponse(mockStrategies)
  },
  
  async getStrategyDetail(id) {
    if (!USE_MOCK) return null
    const strategy = mockStrategies.find(s => s.id === id)
    return mockApiResponse(strategy)
  },
  
  async startStrategy(id) {
    if (!USE_MOCK) return null
    // 更新策略状态
    const strategy = mockStrategies.find(s => s.id === id)
    if (strategy) {
      strategy.status = 'running'
      saveMockData() // 保存到本地存储
    }
    return mockApiResponse({ success: true })
  },
  
  async stopStrategy(id) {
    if (!USE_MOCK) return null
    // 更新策略状态
    const strategy = mockStrategies.find(s => s.id === id)
    if (strategy) {
      strategy.status = 'stopped'
      saveMockData() // 保存到本地存储
    }
    return mockApiResponse({ success: true })
  },
  
  async createStrategy(data) {
    if (!USE_MOCK) return null
    const newStrategy = {
      id: Date.now(),
      ...data,
      status: data.autoStart ? 'running' : 'pending',
      pnl: 0,
      returnRate: 0,
      trades: 0,
      runTime: '-'
    }
    mockStrategies.push(newStrategy)
    saveMockData() // 保存到本地存储
    return mockApiResponse({ success: true, data: newStrategy })
  },
  
  async deleteStrategy(id) {
    if (!USE_MOCK) return null
    const index = mockStrategies.findIndex(s => s.id === id)
    if (index > -1) {
      mockStrategies.splice(index, 1)
      saveMockData() // 保存到本地存储
    }
    return mockApiResponse({ success: true })
  }
}

// 账户相关Mock
export const mockAccountApi = {
  async getAccounts() {
    if (!USE_MOCK) return null
    return mockApiResponse(mockAccounts)
  },
  
  async getAccountDetail(id) {
    if (!USE_MOCK) return null
    const account = mockAccounts.find(a => a.id === id)
    return mockApiResponse(account)
  },
  
  async getAccountBalance(id) {
    if (!USE_MOCK) return null
    const account = mockAccounts.find(a => a.id === id)
    return mockApiResponse({
      balance: account?.balance || 0,
      availableBalance: account?.availableBalance || 0,
      frozenBalance: account?.frozenBalance || 0
    })
  },
  
  async addAccount(data) {
    if (!USE_MOCK) return null
    const newAccount = {
      id: Date.now(),
      ...data,
      balance: 10000,
      availableBalance: 10000,
      frozenBalance: 0,
      equity: 10000,
      unrealizedPnl: 0,
      realizedPnl: 0,
      returnRate: 0,
      status: 'active',
      lastSyncTime: new Date(),
      createdAt: new Date()
    }
    mockAccounts.push(newAccount)
    saveMockData() // 保存到本地存储
    return mockApiResponse({ success: true, data: newAccount })
  },
  
  async updateAccount(id, data) {
    if (!USE_MOCK) return null
    const account = mockAccounts.find(a => a.id === id)
    if (account) {
      Object.assign(account, data)
      saveMockData() // 保存到本地存储
    }
    return mockApiResponse({ success: true })
  },
  
  async deleteAccount(id) {
    if (!USE_MOCK) return null
    const index = mockAccounts.findIndex(a => a.id === id)
    if (index > -1) {
      mockAccounts.splice(index, 1)
      saveMockData() // 保存到本地存储
    }
    return mockApiResponse({ success: true })
  },
  
  async syncAccount(id) {
    if (!USE_MOCK) return null
    const account = mockAccounts.find(a => a.id === id)
    if (account) {
      account.lastSyncTime = new Date()
      // 模拟数据变化
      account.balance += Math.random() * 100 - 50
      account.equity = account.balance + account.unrealizedPnl
      saveMockData() // 保存到本地存储
    }
    return mockApiResponse({ success: true })
  },
  
  async getAccountEquityCurve(id, timeRange) {
    if (!USE_MOCK) return null
    // 生成模拟曲线数据
    const data = []
    const now = Date.now()
    const dayMs = 24 * 60 * 60 * 1000
    
    let days = 7
    if (timeRange === '1d') days = 1
    else if (timeRange === '30d') days = 30
    else if (timeRange === '90d') days = 90
    
    let value = 10000
    for (let i = days; i >= 0; i--) {
      const time = new Date(now - i * dayMs)
      value += (Math.random() - 0.45) * 200
      data.push({
        timestamp: time.toISOString(),
        equity: value
      })
    }
    
    return mockApiResponse({
      data: data,
      statistics: {
        initialEquity: 10000,
        currentEquity: value,
        totalReturn: value - 10000,
        returnRate: ((value - 10000) / 10000) * 100
      }
    })
  }
}

// 订单相关Mock
export const mockOrderApi = {
  async getOrders() {
    if (!USE_MOCK) return null
    return mockApiResponse(mockOrders)
  },
  
  async getOrderDetail(id) {
    if (!USE_MOCK) return null
    const order = mockOrders.find(o => o.id === id)
    return mockApiResponse(order)
  },
  
  async placeOrder(data) {
    if (!USE_MOCK) return null
    const newOrder = {
      id: Date.now(),
      exchangeOrderId: 'EXG' + Date.now(),
      ...data,
      filledQuantity: 0,
      filledPrice: null,
      state: 'SUBMITTED',
      fee: 0,
      timestamp: new Date(),
      updateTime: new Date(),
      trades: []
    }
    mockOrders.unshift(newOrder)
    saveMockData() // 保存到本地存储
    return mockApiResponse({ success: true, data: newOrder })
  },
  
  async cancelOrder(id) {
    if (!USE_MOCK) return null
    const order = mockOrders.find(o => o.id === id)
    if (order) {
      order.state = 'CANCELLED'
      order.updateTime = new Date()
      saveMockData() // 保存到本地存储
    }
    return mockApiResponse({ success: true })
  },
  
  async batchCancelOrders(ids) {
    if (!USE_MOCK) return null
    ids.forEach(id => {
      const order = mockOrders.find(o => o.id === id)
      if (order) {
        order.state = 'CANCELLED'
        order.updateTime = new Date()
      }
    })
    saveMockData() // 保存到本地存储
    return mockApiResponse({ success: true })
  }
}

// 持仓相关Mock
export const mockPositionApi = {
  async getPositions() {
    if (!USE_MOCK) return null
    return mockApiResponse(mockPositions)
  }
}

