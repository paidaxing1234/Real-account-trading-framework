/**
 * 事件流Composable
 * 在Vue组件中使用事件流的便捷方法
 */

import { onMounted, onUnmounted, ref } from 'vue'
import { eventClient } from '@/services/EventClient'

/**
 * 使用事件流
 * @param {string} eventType - 事件类型
 * @param {Function} callback - 回调函数
 */
export function useEventStream(eventType, callback) {
  const connected = ref(false)
  
  onMounted(() => {
    // 注册监听器
    eventClient.on(eventType, callback)
    
    // 监听连接状态
    eventClient.on('connected', () => {
      connected.value = true
    })
    
    eventClient.on('disconnected', () => {
      connected.value = false
    })
    
    // 确保已连接
    if (!eventClient.isConnected()) {
      eventClient.start()
    }
  })
  
  onUnmounted(() => {
    // 取消监听器
    eventClient.off(eventType, callback)
  })
  
  return {
    connected
  }
}

/**
 * 监听订单更新
 */
export function useOrderStream(callback) {
  return useEventStream('order', callback)
}

/**
 * 监听行情更新
 */
export function useTickerStream(callback) {
  return useEventStream('ticker', callback)
}

/**
 * 监听持仓更新
 */
export function usePositionStream(callback) {
  return useEventStream('position', callback)
}

/**
 * 监听账户更新
 */
export function useAccountStream(callback) {
  return useEventStream('account', callback)
}

/**
 * 监听策略更新
 */
export function useStrategyStream(callback) {
  return useEventStream('strategy', callback)
}

/**
 * 发送命令
 */
export function useCommand() {
  const loading = ref(false)
  const error = ref(null)
  
  const send = async (action, data) => {
    loading.value = true
    error.value = null
    
    try {
      const result = await eventClient.send(action, data)
      return result
    } catch (e) {
      error.value = e
      throw e
    } finally {
      loading.value = false
    }
  }
  
  return {
    send,
    loading,
    error
  }
}

