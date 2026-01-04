/**
 * 账户相关API
 * 通过 WebSocket 与后端通信
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

    const timer = setTimeout(() => {
      pendingRequests.delete(requestId)
      reject(new Error('请求超时'))
    }, timeout)

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

    wsClient.send(action, {
      requestId,
      ...data
    })
  })
}

export const accountApi = {
  /**
   * 获取账户列表
   */
  async getAccounts(params) {
    return { data: [], success: true }
  },

  /**
   * 获取账户详情
   */
  async getAccountDetail(id) {
    return { data: null, success: true }
  },

  /**
   * 获取账户余额
   */
  async getAccountBalance(id, currency) {
    return { data: null, success: true }
  },

  /**
   * 获取账户持仓
   */
  async getAccountPositions(id, params) {
    return { data: [], success: true }
  },

  /**
   * 获取账户净值曲线
   */
  async getAccountEquityCurve(id, timeRange) {
    return { data: [], success: true }
  },

  /**
   * 注册账户
   */
  async addAccount(data) {
    try {
      const result = await sendRequest('register_account', {
        strategy_id: data.strategyId || '',
        exchange: data.exchange,
        api_key: data.apiKey,
        secret_key: data.secretKey,
        passphrase: data.passphrase || '',
        is_testnet: data.isTestnet
      })
      return result
    } catch (error) {
      console.error('Account registration failed:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 更新账户
   */
  async updateAccount(id, data) {
    console.log('Update account:', id, data)
    return { data: null, success: true }
  },

  /**
   * 注销账户
   */
  async deleteAccount(id) {
    try {
      const result = await sendRequest('unregister_account', {
        strategy_id: id
      })
      return result
    } catch (error) {
      console.error('Account unregistration failed:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /**
   * 同步账户
   */
  async syncAccount(id) {
    console.log('Sync account:', id)
    return { data: null, success: true }
  },

  /**
   * 列出所有账户
   */
  async listAccounts() {
    try {
      const result = await sendRequest('list_accounts', {})
      return result
    } catch (error) {
      console.error('List accounts failed:', error)
      return { data: null, success: false, message: error.message }
    }
  }
}

export default accountApi



