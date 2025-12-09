import dayjs from 'dayjs'

/**
 * 格式化时间
 */
export function formatTime(time, format = 'YYYY-MM-DD HH:mm:ss') {
  if (!time) return '-'
  return dayjs(time).format(format)
}

/**
 * 格式化数字
 */
export function formatNumber(num, decimals = 2) {
  if (num === null || num === undefined) return '-'
  return Number(num).toFixed(decimals)
}

/**
 * 格式化百分比
 */
export function formatPercent(num, decimals = 2) {
  if (num === null || num === undefined) return '-'
  const value = (num * 100).toFixed(decimals)
  return `${value}%`
}

/**
 * 格式化金额
 */
export function formatMoney(amount, currency = 'USDT', decimals = 2) {
  if (amount === null || amount === undefined) return '-'
  const value = Number(amount).toFixed(decimals)
  return `${value} ${currency}`
}

/**
 * 格式化大数字（K, M, B）
 */
export function formatLargeNumber(num) {
  if (num === null || num === undefined) return '-'
  
  const absNum = Math.abs(num)
  const sign = num < 0 ? '-' : ''
  
  if (absNum >= 1e9) {
    return sign + (absNum / 1e9).toFixed(2) + 'B'
  }
  if (absNum >= 1e6) {
    return sign + (absNum / 1e6).toFixed(2) + 'M'
  }
  if (absNum >= 1e3) {
    return sign + (absNum / 1e3).toFixed(2) + 'K'
  }
  return sign + absNum.toFixed(2)
}

/**
 * 格式化订单状态
 */
export function formatOrderState(state) {
  const stateMap = {
    'CREATED': '已创建',
    'SUBMITTED': '已提交',
    'ACCEPTED': '已接受',
    'PARTIALLY_FILLED': '部分成交',
    'FILLED': '完全成交',
    'CANCELLED': '已取消',
    'REJECTED': '已拒绝',
    'EXPIRED': '已过期'
  }
  return stateMap[state] || state
}

/**
 * 格式化策略状态
 */
export function formatStrategyStatus(status) {
  const statusMap = {
    'running': '运行中',
    'stopped': '已停止',
    'pending': '待启动',
    'error': '异常'
  }
  return statusMap[status] || status
}

/**
 * 格式化订单方向
 */
export function formatOrderSide(side) {
  const sideMap = {
    'BUY': '买入',
    'SELL': '卖出',
    'buy': '买入',
    'sell': '卖出'
  }
  return sideMap[side] || side
}

/**
 * 格式化订单类型
 */
export function formatOrderType(type) {
  const typeMap = {
    'LIMIT': '限价',
    'MARKET': '市价',
    'STOP': '止损',
    'STOP_LIMIT': '止损限价'
  }
  return typeMap[type] || type
}

/**
 * 计算收益率
 */
export function calculateReturn(current, initial) {
  if (!initial || initial === 0) return 0
  return ((current - initial) / initial) * 100
}

/**
 * 计算盈亏
 */
export function calculatePnL(entry, current, quantity, side) {
  if (!entry || !current || !quantity) return 0
  
  if (side === 'BUY' || side === 'buy') {
    return (current - entry) * quantity
  } else {
    return (entry - current) * quantity
  }
}

