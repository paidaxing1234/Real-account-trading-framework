import request from '@/utils/request'
import { mockOrderApi, mockPositionApi } from './mock'

/**
 * 获取订单列表
 */
export async function getOrders(params) {
  const mockResult = await mockOrderApi.getOrders(params)
  if (mockResult) return mockResult
  
  return request({
    url: '/orders',
    method: 'get',
    params
  })
}

/**
 * 获取订单详情
 */
export function getOrderDetail(id) {
  return request({
    url: `/orders/${id}`,
    method: 'get'
  })
}

/**
 * 获取成交记录
 */
export function getTrades(params) {
  return request({
    url: '/trades',
    method: 'get',
    params
  })
}

/**
 * 获取持仓列表
 */
export async function getPositions(params) {
  const mockResult = await mockPositionApi.getPositions()
  if (mockResult) return mockResult
  
  return request({
    url: '/positions',
    method: 'get',
    params
  })
}

/**
 * 获取持仓详情
 */
export function getPositionDetail(id) {
  return request({
    url: `/positions/${id}`,
    method: 'get'
  })
}

/**
 * 手动下单
 */
export async function placeOrder(data) {
  const mockResult = await mockOrderApi.placeOrder(data)
  if (mockResult) return mockResult
  
  return request({
    url: '/orders',
    method: 'post',
    data
  })
}

/**
 * 取消订单
 */
export async function cancelOrder(id) {
  const mockResult = await mockOrderApi.cancelOrder(id)
  if (mockResult) return mockResult
  
  return request({
    url: `/orders/${id}/cancel`,
    method: 'post'
  })
}

/**
 * 批量取消订单
 */
export async function batchCancelOrders(ids) {
  const mockResult = await mockOrderApi.batchCancelOrders(ids)
  if (mockResult) return mockResult
  
  return request({
    url: '/orders/batch-cancel',
    method: 'post',
    data: { ids }
  })
}

/**
 * 获取订单统计
 */
export function getOrderStatistics(params) {
  return request({
    url: '/orders/statistics',
    method: 'get',
    params
  })
}

/**
 * 导出订单数据
 */
export function exportOrders(params) {
  return request({
    url: '/orders/export',
    method: 'get',
    params,
    responseType: 'blob'
  })
}

