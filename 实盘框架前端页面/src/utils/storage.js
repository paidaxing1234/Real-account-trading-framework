/**
 * 本地存储工具
 * 用于Mock模式下的数据持久化
 */

const STORAGE_PREFIX = 'trading_system_'

export const storage = {
  /**
   * 保存数据
   */
  set(key, value) {
    try {
      const data = JSON.stringify(value)
      localStorage.setItem(STORAGE_PREFIX + key, data)
      return true
    } catch (error) {
      console.error('保存数据失败:', error)
      return false
    }
  },
  
  /**
   * 获取数据
   */
  get(key, defaultValue = null) {
    try {
      const data = localStorage.getItem(STORAGE_PREFIX + key)
      return data ? JSON.parse(data) : defaultValue
    } catch (error) {
      console.error('读取数据失败:', error)
      return defaultValue
    }
  },
  
  /**
   * 删除数据
   */
  remove(key) {
    try {
      localStorage.removeItem(STORAGE_PREFIX + key)
      return true
    } catch (error) {
      console.error('删除数据失败:', error)
      return false
    }
  },
  
  /**
   * 清空所有数据
   */
  clear() {
    try {
      const keys = Object.keys(localStorage)
      keys.forEach(key => {
        if (key.startsWith(STORAGE_PREFIX)) {
          localStorage.removeItem(key)
        }
      })
      return true
    } catch (error) {
      console.error('清空数据失败:', error)
      return false
    }
  }
}

/**
 * 策略数据持久化
 */
export const strategyStorage = {
  save(strategies) {
    return storage.set('strategies', strategies)
  },
  
  load(defaultValue) {
    return storage.get('strategies', defaultValue)
  }
}

/**
 * 账户数据持久化
 */
export const accountStorage = {
  save(accounts) {
    return storage.set('accounts', accounts)
  },
  
  load(defaultValue) {
    return storage.get('accounts', defaultValue)
  }
}

/**
 * 订单数据持久化
 */
export const orderStorage = {
  save(orders) {
    return storage.set('orders', orders)
  },
  
  load(defaultValue) {
    return storage.get('orders', defaultValue)
  }
}

/**
 * 持仓数据持久化
 */
export const positionStorage = {
  save(positions) {
    return storage.set('positions', positions)
  },
  
  load(defaultValue) {
    return storage.get('positions', defaultValue)
  }
}

