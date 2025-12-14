/**
 * 账户相关API
 * 通过WebSocket获取数据，这里提供的是占位API
 */

// 由于采用WebSocket架构，实际数据通过WebSocket推送
// 这里提供的API主要用于兼容性和初始化

export const accountApi = {
  /**
   * 获取账户列表
   */
  async getAccounts(params) {
    // 返回空数据，实际通过WebSocket
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
   * 添加账户
   */
  async addAccount(data) {
    console.log('Add account (WebSocket):', data)
    return { data: null, success: true }
  },

  /**
   * 更新账户
   */
  async updateAccount(id, data) {
    console.log('Update account (WebSocket):', id, data)
    return { data: null, success: true }
  },

  /**
   * 删除账户
   */
  async deleteAccount(id) {
    console.log('Delete account (WebSocket):', id)
    return { data: null, success: true }
  },

  /**
   * 同步账户
   */
  async syncAccount(id) {
    console.log('Sync account (WebSocket):', id)
    return { data: null, success: true }
  }
}

export default accountApi

