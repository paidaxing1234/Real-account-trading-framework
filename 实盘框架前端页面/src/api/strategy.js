/**
 * 策略相关API
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
  return `strategy_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

// 发送请求并等待响应
function sendRequest(action, data = {}, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const requestId = generateRequestId()
    const timer = setTimeout(() => {
      pendingRequests.delete(requestId)
      reject(new Error('请求超时'))
    }, timeout)

    pendingRequests.set(requestId, {
      resolve: (result) => { clearTimeout(timer); resolve(result) },
      reject: (error) => { clearTimeout(timer); reject(error) }
    })

    wsClient.send(action, { requestId, ...data })
  })
}

export const strategyApi = {
  /** 获取策略列表 */
  async getStrategies(params) {
    return { data: [], success: true }
  },

  /** 获取策略详情 */
  async getStrategyDetail(id) {
    return { data: null, success: true }
  },

  /** 启动策略 */
  async startStrategy(id, config) {
    try {
      return await sendRequest('start_strategy', { id, config })
    } catch (error) {
      console.error('启动策略失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /** 停止策略 */
  async stopStrategy(id) {
    try {
      return await sendRequest('stop_strategy', { id })
    } catch (error) {
      console.error('停止策略失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /** 获取策略日志文件列表 */
  async getStrategyLogFiles(strategyId = '') {
    try {
      return await sendRequest('get_strategy_log_files', { strategyId })
    } catch (error) {
      console.error('获取策略日志文件列表失败:', error)
      return { data: [], success: false, message: error.message }
    }
  },

  /** 获取策略日志内容 */
  async getStrategyLogs(filename, tailLines = 200) {
    try {
      return await sendRequest('get_strategy_logs', { filename, tailLines }, 15000)
    } catch (error) {
      console.error('获取策略日志失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /** 创建策略 */
  async createStrategy(data) {
    console.log('Create strategy (WebSocket):', data)
    return { data: null, success: true }
  },

  /** 更新策略 */
  async updateStrategy(id, data) {
    console.log('Update strategy (WebSocket):', id, data)
    return { data: null, success: true }
  },

  /** 删除策略 */
  async deleteStrategy(id) {
    console.log('Delete strategy (WebSocket):', id)
    return { data: null, success: true }
  },

  /** 获取策略性能 */
  async fetchStrategyPerformance(id, timeRange) {
    return { data: null, success: true }
  },

  /** 列出策略源代码文件 */
  async listStrategyFiles() {
    try {
      return await sendRequest('list_strategy_files', {})
    } catch (error) {
      console.error('获取策略文件列表失败:', error)
      return { data: [], success: false, message: error.message }
    }
  },

  /** 获取策略源代码 */
  async getStrategySource(filename) {
    try {
      return await sendRequest('get_strategy_source', { filename }, 15000)
    } catch (error) {
      console.error('获取策略源代码失败:', error)
      return { data: null, success: false, message: error.message }
    }
  },

  /** 保存策略源代码 */
  async saveStrategySource(filename, content) {
    try {
      return await sendRequest('save_strategy_source', { filename, content }, 15000)
    } catch (error) {
      console.error('保存策略源代码失败:', error)
      return { data: null, success: false, message: error.message }
    }
  }
}

export default strategyApi

