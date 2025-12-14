<template>
  <div class="super-admin-dashboard">
    <el-row :gutter="20">
      <el-col :span="24">
        <h3>超级管理员视图 - 全局概览</h3>
      </el-col>
    </el-row>
    
    <!-- 全局统计 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">总资产 (USDT)</span>
            <el-icon color="#409eff"><Wallet /></el-icon>
          </div>
          <div class="stat-value">{{ formatNumber(totalEquity, 2) }}</div>
          <div class="stat-change" :class="equityChange >= 0 ? 'text-success' : 'text-danger'">
            <el-icon>
              <component :is="equityChange >= 0 ? 'TopRight' : 'BottomRight'" />
            </el-icon>
            {{ formatPercent(equityChange / 100) }}
          </div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">总盈亏 (USDT)</span>
            <el-icon color="#67c23a"><TrendCharts /></el-icon>
          </div>
          <div class="stat-value" :class="totalPnL >= 0 ? 'text-success' : 'text-danger'">
            {{ formatNumber(totalPnL, 2) }}
          </div>
          <div class="stat-change">
            今日: {{ formatNumber(todayPnL, 2) }}
          </div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">运行策略</span>
            <el-icon color="#e6a23c"><SetUp /></el-icon>
          </div>
          <div class="stat-value">{{ runningStrategies }}</div>
          <div class="stat-change">
            总策略: {{ totalStrategies }}
          </div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">活跃账户</span>
            <el-icon color="#f56c6c"><User /></el-icon>
          </div>
          <div class="stat-value">{{ activeAccounts }}</div>
          <div class="stat-change">
            总账户: {{ totalAccounts }}
          </div>
        </div>
      </el-col>
    </el-row>
    
    <!-- 多账号净值对比 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>多账号净值对比</span>
          </template>
          <multi-account-equity-chart height="350px" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 多策略收益对比 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>多策略收益对比</span>
          </template>
          <multi-strategy-performance-chart height="350px" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 最近订单 + 系统日志 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近订单</span>
              <el-button text @click="$router.push('/orders')">
                查看全部 →
              </el-button>
            </div>
          </template>
          <recent-orders-table :limit="10" />
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>系统日志</span>
              <el-button text @click="$router.push('/logs')">
                查看全部 →
              </el-button>
            </div>
          </template>
          <recent-logs-table :limit="10" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAccountStore } from '@/stores/account'
import { useStrategyStore } from '@/stores/strategy'
import { useOrderStore } from '@/stores/order'
import { formatNumber, formatPercent } from '@/utils/format'
import MultiAccountEquityChart from '@/components/Charts/MultiAccountEquityChart.vue'
import MultiStrategyPerformanceChart from '@/components/Charts/MultiStrategyPerformanceChart.vue'
import { Wallet, TrendCharts, SetUp, User } from '@element-plus/icons-vue'

const accountStore = useAccountStore()
const strategyStore = useStrategyStore()
const orderStore = useOrderStore()

// 统计数据
const totalEquity = computed(() => accountStore.totalEquity || 0)
const equityChange = computed(() => 5.2) // Mock数据
const totalPnL = computed(() => accountStore.totalPnL || 0)
const todayPnL = computed(() => 120.50) // Mock数据
const runningStrategies = computed(() => strategyStore.runningStrategies?.length || 0)
const totalStrategies = computed(() => strategyStore.strategies?.length || 0)
const activeAccounts = computed(() => accountStore.activeAccounts?.length || 0)
const totalAccounts = computed(() => accountStore.accounts?.length || 0)

// 临时组件（简化）
const RecentOrdersTable = {
  template: '<div style="padding: 20px; text-align: center; color: #909399;">最近订单列表</div>'
}

const RecentLogsTable = {
  template: '<div style="padding: 20px; text-align: center; color: #909399;">最近系统日志</div>'
}
</script>

<style lang="scss" scoped>
.super-admin-dashboard {
  h3 {
    margin: 0 0 20px 0;
    color: #303133;
  }
  
  .stats-row {
    margin-bottom: 20px;
  }
  
  .stat-card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
    
    .stat-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 15px;
      
      .stat-label {
        font-size: 14px;
        color: #909399;
      }
    }
    
    .stat-value {
      font-size: 28px;
      font-weight: bold;
      color: #303133;
      margin-bottom: 10px;
    }
    
    .stat-change {
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 4px;
      
      &.text-success {
        color: #67c23a;
      }
      
      &.text-danger {
        color: #f56c6c;
      }
    }
  }
  
  .charts-row {
    margin-bottom: 20px;
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}
</style>

