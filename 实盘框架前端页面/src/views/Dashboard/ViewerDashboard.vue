<template>
  <div class="viewer-dashboard">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-alert
          title="观摩者模式"
          type="info"
          :closable="false"
          show-icon
        >
          您当前以观摩者身份登录，只能查看数据，无法执行交易操作
        </el-alert>
      </el-col>
    </el-row>
    
    <!-- 账号选择器 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>选择要查看的账号</span>
          </template>
          <el-radio-group v-model="selectedAccountId" @change="handleAccountChange">
            <el-radio-button 
              v-for="account in accounts" 
              :key="account.id" 
              :label="account.id"
            >
              {{ account.name }}
            </el-radio-button>
          </el-radio-group>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 选中账号的统计 -->
    <el-row :gutter="20" class="stats-row" v-if="selectedAccount">
      <el-col :xs="24" :sm="12" :md="8">
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">账户净值 (USDT)</span>
            <el-icon color="#409eff"><Wallet /></el-icon>
          </div>
          <div class="stat-value">{{ formatNumber(selectedAccount.equity || 0, 2) }}</div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="8">
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">未实现盈亏 (USDT)</span>
            <el-icon color="#67c23a"><TrendCharts /></el-icon>
          </div>
          <div class="stat-value" :class="selectedAccount.unrealizedPnl >= 0 ? 'text-success' : 'text-danger'">
            {{ formatNumber(selectedAccount.unrealizedPnl || 0, 2) }}
          </div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="8">
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">收益率</span>
            <el-icon color="#e6a23c"><DataLine /></el-icon>
          </div>
          <div class="stat-value" :class="selectedAccount.returnRate >= 0 ? 'text-success' : 'text-danger'">
            {{ formatPercent((selectedAccount.returnRate || 0) / 100) }}
          </div>
        </div>
      </el-col>
    </el-row>
    
    <!-- 净值曲线 -->
    <el-row :gutter="20" class="charts-row" v-if="selectedAccount">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>{{ selectedAccount.name }} - 净值曲线</span>
          </template>
          <equity-chart :account-id="selectedAccountId" height="300px" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 持仓和订单（只读） -->
    <el-row :gutter="20" class="charts-row" v-if="selectedAccount">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>当前持仓</span>
          </template>
          <position-distribution-chart :positions="positions" />
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>最近订单（只读）</span>
          </template>
          <el-table :data="recentOrders" max-height="300" size="small">
            <el-table-column prop="symbol" label="交易对" width="120" />
            <el-table-column prop="side" label="方向" width="60">
              <template #default="{ row }">
                <el-tag :type="row.side === 'BUY' ? 'success' : 'danger'" size="small">
                  {{ row.side }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="quantity" label="数量" align="right" />
            <el-table-column prop="state" label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.state }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAccountStore } from '@/stores/account'
import { useOrderStore } from '@/stores/order'
import { formatNumber, formatPercent } from '@/utils/format'
import EquityChart from '@/components/Charts/EquityChart.vue'
import PositionDistributionChart from '@/components/Charts/PositionDistributionChart.vue'
import { Wallet, TrendCharts, DataLine } from '@element-plus/icons-vue'

const accountStore = useAccountStore()
const orderStore = useOrderStore()

const selectedAccountId = ref(null)

const accounts = computed(() => accountStore.accounts || [])
const selectedAccount = computed(() => 
  accounts.value.find(a => a.id === selectedAccountId.value)
)
const positions = computed(() => orderStore.positions || [])
const recentOrders = computed(() => (orderStore.orders || []).slice(0, 10))

// 初始化选中第一个账号
watch(accounts, (newAccounts) => {
  if (newAccounts.length > 0 && !selectedAccountId.value) {
    selectedAccountId.value = newAccounts[0].id
  }
}, { immediate: true })

function handleAccountChange() {
  // 账号切换时可以刷新数据
  console.log('切换账号:', selectedAccountId.value)
}
</script>

<style lang="scss" scoped>
.viewer-dashboard {
  .el-alert {
    margin-bottom: 20px;
  }
  
  .stats-row {
    margin: 20px 0;
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
      font-size: 24px;
      font-weight: bold;
      color: #303133;
      
      &.text-success {
        color: #67c23a;
      }
      
      &.text-danger {
        color: #f56c6c;
      }
    }
    
    .stat-change {
      font-size: 12px;
      color: #909399;
      margin-top: 5px;
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

