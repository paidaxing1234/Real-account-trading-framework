/**
 * 事件流客户端
 * 类似C++ Component的设计，使用SSE实现低延迟实时通信
 * 延迟：3-10ms
 */

import { ElMessage } from 'element-plus'

class EventClient {
  constructor() {
    this.eventSource = null
    this.listeners = new Map()  // 类似C++的监听器映射
    this.connected = false
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 10
    this.reconnectDelay = 1000
  }
  
  /**
   * 启动客户端（类似Component::start）
   */
  start() {
    console.log('🚀 启动事件流客户端...')
    this.connect()
  }
  
  /**
   * 连接SSE流
   */
  connect() {
    try {
      // 创建EventSource连接
      this.eventSource = new EventSource('/api/events/stream', {
        withCredentials: true
      })
      
      // 连接打开
      this.eventSource.onopen = () => {
        console.log('✅ SSE连接已建立')
        this.connected = true
        this.reconnectAttempts = 0
        this.emit('connected', { timestamp: Date.now() })
      }
      
      // 监听订单事件
      this.eventSource.addEventListener('order', (e) => {
        const order = JSON.parse(e.data)
        this.emit('order', order)
      })
      
      // 监听行情事件
      this.eventSource.addEventListener('ticker', (e) => {
        const ticker = JSON.parse(e.data)
        this.emit('ticker', ticker)
      })
      
      // 监听持仓事件
      this.eventSource.addEventListener('position', (e) => {
        const position = JSON.parse(e.data)
        this.emit('position', position)
      })
      
      // 监听账户事件
      this.eventSource.addEventListener('account', (e) => {
        const account = JSON.parse(e.data)
        this.emit('account', account)
      })
      
      // 监听策略事件
      this.eventSource.addEventListener('strategy', (e) => {
        const strategy = JSON.parse(e.data)
        this.emit('strategy', strategy)
      })
      
      // 监听系统事件
      this.eventSource.addEventListener('system', (e) => {
        const data = JSON.parse(e.data)
        this.emit('system', data)
      })
      
      // 连接错误
      this.eventSource.onerror = (error) => {
        console.error('❌ SSE连接错误:', error)
        this.connected = false
        this.emit('disconnected', { timestamp: Date.now() })
        
        // 自动重连
        this.handleReconnect()
      }
      
    } catch (error) {
      console.error('创建SSE连接失败:', error)
      this.handleReconnect()
    }
  }
  
  /**
   * 注册事件监听器（类似EventEngine::register_listener）
   * @param {string} eventType - 事件类型
   * @param {Function} callback - 回调函数
   */
  on(eventType, callback) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, [])
    }
    this.listeners.get(eventType).push(callback)
  }
  
  /**
   * 取消监听器
   */
  off(eventType, callback) {
    if (!this.listeners.has(eventType)) return
    
    const callbacks = this.listeners.get(eventType)
    const index = callbacks.indexOf(callback)
    if (index > -1) {
      callbacks.splice(index, 1)
    }
  }
  
  /**
   * 发送事件给所有监听器（类似EventEngine::put）
   */
  emit(eventType, data) {
    const callbacks = this.listeners.get(eventType) || []
    callbacks.forEach(callback => {
      try {
        callback(data)
      } catch (error) {
        console.error(`事件处理错误 [${eventType}]:`, error)
      }
    })
  }
  
  /**
   * 发送命令到服务器（类似发送Order事件）
   */
  async send(action, data) {
    try {
      const response = await fetch('/api/command', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ action, data })
      })
      
      return await response.json()
    } catch (error) {
      console.error('发送命令失败:', error)
      throw error
    }
  }
  
  /**
   * 处理重连
   */
  handleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('❌ 达到最大重连次数，停止重连')
      ElMessage.error('无法连接到服务器，请刷新页面')
      return
    }
    
    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
    
    console.log(`⏳ ${delay/1000}秒后尝试重连... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
    
    setTimeout(() => {
      this.connect()
    }, delay)
  }
  
  /**
   * 停止客户端（类似Component::stop）
   */
  stop() {
    console.log('🛑 停止事件流客户端...')
    
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
    
    this.connected = false
    this.listeners.clear()
    console.log('✅ 事件流客户端已停止')
  }
  
  /**
   * 获取连接状态
   */
  isConnected() {
    return this.connected
  }
}

// 单例模式
export const eventClient = new EventClient()

// Vue插件形式
export default {
  install(app) {
    app.config.globalProperties.$eventClient = eventClient
    app.provide('eventClient', eventClient)
  }
}

