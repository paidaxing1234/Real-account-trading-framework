import request from '@/utils/request'

/**
 * 获取市场行情
 */
export function getTickers(symbols) {
  return request({
    url: '/market/tickers',
    method: 'get',
    params: { symbols }
  })
}

/**
 * 获取K线数据
 */
export function getKlines(symbol, interval, params) {
  return request({
    url: '/market/klines',
    method: 'get',
    params: { symbol, interval, ...params }
  })
}

/**
 * 获取深度数据
 */
export function getDepth(symbol, limit = 20) {
  return request({
    url: '/market/depth',
    method: 'get',
    params: { symbol, limit }
  })
}

/**
 * 获取最新成交
 */
export function getRecentTrades(symbol, limit = 50) {
  return request({
    url: '/market/trades',
    method: 'get',
    params: { symbol, limit }
  })
}

/**
 * 获取24小时统计
 */
export function get24hrStats(symbol) {
  return request({
    url: '/market/24hr',
    method: 'get',
    params: { symbol }
  })
}

