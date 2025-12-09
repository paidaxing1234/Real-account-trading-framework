import request from '@/utils/request'
import { mockAccountApi } from './mock'

/**
 * 获取所有账户列表
 */
export async function getAccounts(params) {
  const mockResult = await mockAccountApi.getAccounts()
  if (mockResult) return mockResult
  
  return request({
    url: '/accounts',
    method: 'get',
    params
  })
}

/**
 * 获取账户详情
 */
export function getAccountDetail(id) {
  return request({
    url: `/accounts/${id}`,
    method: 'get'
  })
}

/**
 * 获取账户余额
 */
export function getAccountBalance(id, currency) {
  return request({
    url: `/accounts/${id}/balance`,
    method: 'get',
    params: { currency }
  })
}

/**
 * 获取账户持仓
 */
export function getAccountPositions(id, params) {
  return request({
    url: `/accounts/${id}/positions`,
    method: 'get',
    params
  })
}

/**
 * 获取账户净值曲线
 */
export async function getAccountEquityCurve(id, timeRange) {
  const mockResult = await mockAccountApi.getAccountEquityCurve(id, timeRange)
  if (mockResult) return mockResult
  
  return request({
    url: `/accounts/${id}/equity-curve`,
    method: 'get',
    params: { timeRange }
  })
}

/**
 * 获取账户统计信息
 */
export function getAccountStatistics(id, timeRange) {
  return request({
    url: `/accounts/${id}/statistics`,
    method: 'get',
    params: { timeRange }
  })
}

/**
 * 添加新账户
 */
export async function addAccount(data) {
  const mockResult = await mockAccountApi.addAccount(data)
  if (mockResult) return mockResult
  
  return request({
    url: '/accounts',
    method: 'post',
    data
  })
}

/**
 * 更新账户信息
 */
export async function updateAccount(id, data) {
  const mockResult = await mockAccountApi.updateAccount(id, data)
  if (mockResult) return mockResult
  
  return request({
    url: `/accounts/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除账户
 */
export async function deleteAccount(id) {
  const mockResult = await mockAccountApi.deleteAccount(id)
  if (mockResult) return mockResult
  
  return request({
    url: `/accounts/${id}`,
    method: 'delete'
  })
}

/**
 * 获取账户资金流水
 */
export function getAccountBills(id, params) {
  return request({
    url: `/accounts/${id}/bills`,
    method: 'get',
    params
  })
}

/**
 * 同步账户数据
 */
export async function syncAccount(id) {
  const mockResult = await mockAccountApi.syncAccount(id)
  if (mockResult) return mockResult
  
  return request({
    url: `/accounts/${id}/sync`,
    method: 'post'
  })
}

