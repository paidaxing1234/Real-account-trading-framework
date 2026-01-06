/**
 * 模拟交易相关API
 * 通过WebSocket与C++后端通信
 */

import { wsClient } from '@/services/WebSocketClient'

// 响应等待器
const pendingRequests = new Map()

// 监听WebSocket响应
wsClient.on('response', (response) => {
  const { requestId, success, message, data } = response
  
  if (pendingRequests.has(requestId)) {
    const { resolve, reject } = pendingRequests.get(requestId)
    pendingRequests.delete(requestId)
    
    if (success) {
      resolve({ data, success: true, message })
    } else {
      reject(new Error(message || '操作失败'))
    }
  }
})

// 生成请求ID
function generateRequestId() {
  return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

// 发送请求并等待响应
function sendRequest(action, data, timeout = 5000) {
  return new Promise((resolve, reject) => {
    const requestId = generateRequestId()
    
    // 设置超时
    const timer = setTimeout(() => {
      pendingRequests.delete(requestId)
      reject(new Error('请求超时'))
    }, timeout)
    
    // 保存resolve/reject
    pendingRequests.set(requestId, {
      resolve: (result) => {
        clearTimeout(timer)
        resolve(result)
      },
      reject: (error) => {
        clearTimeout(timer)
        reject(error)
      }
    })
    
    // 发送请求
    wsClient.send(action, {
      requestId,
      ...data
    })
  })
}

export const papertradingApi = {
  /**
   * 获取模拟账户信息
   */
  async getAccountInfo() {
    try {
      const result = await sendRequest('query_account', {})
      return result
    } catch (error) {
      console.error('获取账户信息失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 获取持仓列表
   */
  async getPositions(params) {
    // 持仓数据通过快照获取，这里返回空数组
    return { data: [], success: true }
  },

  /**
   * 获取订单列表
   */
  async getOrders(params) {
    // 订单数据通过快照获取，这里返回空数组
    return { data: [], success: true }
  },

  /**
   * 获取成交记录
   */
  async getTrades(params) {
    // 成交数据通过快照获取，这里返回空数组
    return { data: [], success: true }
  },

  /**
   * 平仓
   */
  async closePosition(symbol, side) {
    try {
      const result = await sendRequest('close_position', { symbol, side })
      return result
    } catch (error) {
      console.error('平仓失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 撤销订单
   */
  async cancelOrder(orderId) {
    try {
      const result = await sendRequest('cancel_order', { orderId })
      return result
    } catch (error) {
      console.error('撤单失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 重置账户
   */
  async resetAccount() {
    try {
      const result = await sendRequest('reset_account', {})
      return result
    } catch (error) {
      console.error('重置账户失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 更新账户配置
   */
  async updateConfig(config) {
    try {
      const result = await sendRequest('update_config', {
        initialBalance: config.initialBalance,
        makerFeeRate: config.makerFeeRate,
        takerFeeRate: config.takerFeeRate,
        slippage: config.slippage
      })
      return result
    } catch (error) {
      console.error('更新配置失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 获取账户配置
   */
  async getConfig() {
    try {
      const result = await sendRequest('get_config', {})
      return result
    } catch (error) {
      console.error('获取配置失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 启动模拟交易策略
   */
  async startStrategy(config) {
    try {
      const result = await sendRequest('start_paper_strategy', {
        strategyId: config.strategyId,
        exchange: config.exchange,
        initialBalance: config.initialBalance,
        strategy: config.strategy,
        symbol: config.symbol,
        gridNum: config.gridNum,
        gridSpread: config.gridSpread,
        orderAmount: config.orderAmount
      }, 10000)
      return result
    } catch (error) {
      console.error('启动策略失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 停止模拟交易策略
   */
  async stopStrategy(strategyId) {
    try {
      const result = await sendRequest('stop_paper_strategy', { strategyId })
      return result
    } catch (error) {
      console.error('停止策略失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 获取策略运行状态
   */
  async getStrategyStatus() {
    try {
      const result = await sendRequest('get_paper_strategy_status', {})
      return result
    } catch (error) {
      console.error('获取策略状态失败:', error)
      return { data: null, success: false, message: error.message }
    }
  }
}

export default papertradingApi
