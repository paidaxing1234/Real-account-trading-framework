import request from '@/utils/request'
import { mockStrategyApi } from './mock'

/**
 * 获取所有策略列表
 */
export async function getStrategies(params) {
  const mockResult = await mockStrategyApi.getStrategies(params)
  if (mockResult) return mockResult
  
  return request({
    url: '/strategies',
    method: 'get',
    params
  })
}

/**
 * 获取策略详情
 */
export async function getStrategyDetail(id) {
  const mockResult = await mockStrategyApi.getStrategyDetail(id)
  if (mockResult) return mockResult
  
  return request({
    url: `/strategies/${id}`,
    method: 'get'
  })
}

/**
 * 启动策略
 */
export async function startStrategy(id, config) {
  const mockResult = await mockStrategyApi.startStrategy(id, config)
  if (mockResult) return mockResult
  
  return request({
    url: `/strategies/${id}/start`,
    method: 'post',
    data: config
  })
}

/**
 * 停止策略
 */
export async function stopStrategy(id) {
  const mockResult = await mockStrategyApi.stopStrategy(id)
  if (mockResult) return mockResult
  
  return request({
    url: `/strategies/${id}/stop`,
    method: 'post'
  })
}

/**
 * 获取策略性能数据
 */
export function getStrategyPerformance(id, timeRange) {
  return request({
    url: `/strategies/${id}/performance`,
    method: 'get',
    params: { timeRange }
  })
}

/**
 * 获取策略配置
 */
export function getStrategyConfig(id) {
  return request({
    url: `/strategies/${id}/config`,
    method: 'get'
  })
}

/**
 * 更新策略配置
 */
export function updateStrategyConfig(id, config) {
  return request({
    url: `/strategies/${id}/config`,
    method: 'put',
    data: config
  })
}

/**
 * 获取策略日志
 */
export function getStrategyLogs(id, params) {
  return request({
    url: `/strategies/${id}/logs`,
    method: 'get',
    params
  })
}

/**
 * 创建新策略
 */
export async function createStrategy(data) {
  const mockResult = await mockStrategyApi.createStrategy(data)
  if (mockResult) return mockResult
  
  return request({
    url: '/strategies',
    method: 'post',
    data
  })
}

/**
 * 删除策略
 */
export async function deleteStrategy(id) {
  const mockResult = await mockStrategyApi.deleteStrategy(id)
  if (mockResult) return mockResult
  
  return request({
    url: `/strategies/${id}`,
    method: 'delete'
  })
}

