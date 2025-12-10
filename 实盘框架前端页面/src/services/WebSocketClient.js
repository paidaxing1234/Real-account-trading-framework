/**
 * WebSocket客户端 - 符合Kungfu架构
 * 直接连接C++ UI服务器，接收共享内存快照
 * 
 * 性能：
 * - 快照频率：100ms
 * - 延迟：1-4ms
 * - 比HTTP/SSE快5-10倍
 */

import { ElMessage, ElNotification } from 'element-plus'

class WebSocketClient {
  constructor() {
    this.ws = null
    this.connected = false
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 10
    this.reconnectDelay = 1000
    this.listeners = new Map()
    
    // 性能监控
    this.lastSnapshotTime = 0
    this.snapshotCount = 0
    this.avgLatency = 0
  }
  
  /**
   * 连接C++ UI服务器
   */
  connect() {
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8001'
    
    console.log('🔌 连接C++ UI服务器:', wsUrl)
    
    try {
      this.ws = new WebSocket(wsUrl)
      
      // 连接打开
      this.ws.onopen = () => {
        console.log('✅ WebSocket连接已建立')
        this.connected = true
        this.reconnectAttempts = 0
        
        ElNotification({
          title: '连接成功',
          message: 'C++ UI服务器已连接',
          type: 'success',
          duration: 2000
        })
        
        this.emit('connected', { timestamp: Date.now() })
        
        // 发送认证（如果需要）
        const token = localStorage.getItem('token')
        if (token) {
          this.send('auth', { token })
        }
      }
      
      // 接收消息
      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('消息解析失败:', error)
        }
      }
      
      // 连接关闭
      this.ws.onclose = () => {
        console.log('🔌 WebSocket连接关闭')
        this.connected = false
        this.emit('disconnected', { timestamp: Date.now() })
        
        // 自动重连
        this.handleReconnect()
      }
      
      // 连接错误
      this.ws.onerror = (error) => {
        console.error('❌ WebSocket错误:', error)
      }
      
    } catch (error) {
      console.error('创建WebSocket失败:', error)
      this.handleReconnect()
    }
  }
  
  /**
   * 处理消息
   */
  handleMessage(message) {
    const { type, timestamp } = message
    
    // 计算延迟
    const now = Date.now()
    const latency = now - timestamp
    this.updateLatency(latency)
    
    if (type === 'snapshot') {
      // 完整快照（100ms一次）
      this.handleSnapshot(message.data, latency)
    } else if (type === 'event') {
      // 增量事件（立即推送）
      this.handleEvent(message.event_type, message.data, latency)
    } else if (type === 'response') {
      // 命令响应
      this.handleResponse(message)
    }
  }
  
  /**
   * 处理快照（批量更新）
   */
  handleSnapshot(data, latency) {
    this.snapshotCount++
    this.lastSnapshotTime = Date.now()
    
    // 触发快照事件（Store会监听）
    this.emit('snapshot', {
      data,
      latency,
      timestamp: this.lastSnapshotTime
    })
    
    // 如果延迟过高，警告
    if (latency > 50) {
      console.warn(`⚠️ 快照延迟过高: ${latency}ms`)
    }
  }
  
  /**
   * 处理增量事件
   */
  handleEvent(eventType, data, latency) {
    console.log(`📨 收到事件 [${eventType}], 延迟: ${latency}ms`)
    
    // 触发特定事件
    this.emit(eventType, {
      data,
      latency,
      timestamp: Date.now()
    })
    
    // 关键事件通知用户
    if (eventType === 'order_filled') {
      ElNotification({
        title: '订单成交',
        message: `${data.symbol} ${data.side} 已成交`,
        type: 'success'
      })
    }
  }
  
  /**
   * 处理命令响应
   */
  handleResponse(message) {
    const { success, message: msg } = message.data
    
    if (success) {
      ElMessage.success(msg || '操作成功')
    } else {
      ElMessage.error(msg || '操作失败')
    }
  }
  
  /**
   * 发送命令到C++
   */
  send(action, data) {
    if (!this.connected) {
      ElMessage.error('未连接到服务器')
      return false
    }
    
    const message = {
      action,
      data,
      timestamp: Date.now()
    }
    
    try {
      this.ws.send(JSON.stringify(message))
      return true
    } catch (error) {
      console.error('发送命令失败:', error)
      ElMessage.error('发送命令失败')
      return false
    }
  }
  
  /**
   * 注册监听器
   */
  on(eventType, callback) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, [])
    }
    this.listeners.get(eventType).push(callback)
  }
  
  /**
   * 取消监听
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
   * 触发事件
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
   * 处理重连
   */
  handleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('❌ 达到最大重连次数')
      ElMessage.error('无法连接到C++服务器，请检查服务是否启动')
      return
    }
    
    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
    
    console.log(`⏳ ${delay/1000}秒后重连... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
    
    setTimeout(() => {
      this.connect()
    }, delay)
  }
  
  /**
   * 更新延迟统计
   */
  updateLatency(latency) {
    // 移动平均
    this.avgLatency = this.avgLatency * 0.9 + latency * 0.1
  }
  
  /**
   * 获取统计信息
   */
  getStats() {
    return {
      connected: this.connected,
      snapshotCount: this.snapshotCount,
      avgLatency: this.avgLatency.toFixed(2),
      lastSnapshotTime: this.lastSnapshotTime
    }
  }
  
  /**
   * 断开连接
   */
  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.connected = false
  }
}

// 全局单例
export const wsClient = new WebSocketClient()

// Vue插件
export default {
  install(app) {
    app.config.globalProperties.$ws = wsClient
    app.provide('wsClient', wsClient)
  }
}

