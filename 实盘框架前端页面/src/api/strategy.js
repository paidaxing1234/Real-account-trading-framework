/**
 * 策略相关API
 * 通过WebSocket获取数据，这里提供的是占位API
 */

export const strategyApi = {
  /**
   * 获取策略列表
   */
  async getStrategies(params) {
    return { data: [], success: true }
  },

  /**
   * 获取策略详情
   */
  async getStrategyDetail(id) {
    return { data: null, success: true }
  },

  /**
   * 启动策略
   */
  async startStrategy(id, config) {
    console.log('Start strategy (WebSocket):', id, config)
    return { data: null, success: true }
  },

  /**
   * 停止策略
   */
  async stopStrategy(id) {
    console.log('Stop strategy (WebSocket):', id)
    return { data: null, success: true }
  },

  /**
   * 创建策略
   */
  async createStrategy(data) {
    console.log('Create strategy (WebSocket):', data)
    return { data: null, success: true }
  },

  /**
   * 更新策略
   */
  async updateStrategy(id, data) {
    console.log('Update strategy (WebSocket):', id, data)
    return { data: null, success: true }
  },

  /**
   * 删除策略
   */
  async deleteStrategy(id) {
    console.log('Delete strategy (WebSocket):', id)
    return { data: null, success: true }
  },

  /**
   * 获取策略性能
   */
  async fetchStrategyPerformance(id, timeRange) {
    return { data: null, success: true }
  }
}

export default strategyApi

