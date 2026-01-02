<template>
  <div class="papertrading-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>模拟交易</h2>
        <p>使用模拟账户进行策略测试和回测</p>
      </div>
      <div class="header-actions">
        <el-button 
          type="warning" 
          :icon="Refresh"
          @click="handleResetAccount"
        >
          重置账户
        </el-button>
        <el-button 
          type="primary" 
          :icon="Setting"
          @click="showConfigDialog = true"
        >
          账户配置
        </el-button>
      </div>
    </div>
    
    <!-- 账户概览 -->
    <el-row :gutter="20" class="overview-row">
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="overview-icon balance">
            <el-icon><Wallet /></el-icon>
          </div>
          <div class="overview-content">
            <div class="overview-label">账户余额 (USDT)</div>
            <div class="overview-value">{{ formatMoney(accountInfo.balance || 0, 'USDT', 2) }}</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="overview-icon equity">
            <el-icon><TrendCharts /></el-icon>
          </div>
          <div class="overview-content">
            <div class="overview-label">账户净值 (USDT)</div>
            <div class="overview-value">{{ formatMoney(accountInfo.equity || 0, 'USDT', 2) }}</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="overview-icon pnl">
            <el-icon><TrendCharts /></el-icon>
          </div>
          <div class="overview-content">
            <div class="overview-label">总盈亏 (USDT)</div>
            <div class="overview-value" :class="(accountInfo.totalPnl || 0) >= 0 ? 'text-success' : 'text-danger'">
              {{ formatMoney(accountInfo.totalPnl || 0, 'USDT', 2) }}
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="overview-icon return">
            <el-icon><DataAnalysis /></el-icon>
          </div>
          <div class="overview-content">
            <div class="overview-label">收益率</div>
            <div class="overview-value" :class="(accountInfo.returnRate || 0) >= 0 ? 'text-success' : 'text-danger'">
              {{ formatPercent((accountInfo.returnRate || 0) / 100) }}
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 统计信息 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon">
            <el-icon><List /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ orderStats.total || 0 }}</div>
            <div class="stat-label">总订单数</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon filled">
            <el-icon><Check /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ orderStats.filled || 0 }}</div>
            <div class="stat-label">已成交</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon positions">
            <el-icon><PieChart /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ positionStats.total || 0 }}</div>
            <div class="stat-label">持仓数量</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon trades">
            <el-icon><Tools /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ orderStats.trades || 0 }}</div>
            <div class="stat-label">成交笔数</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 标签页 -->
    <el-tabs v-model="activeTab" class="content-tabs">
      <!-- 持仓列表 -->
      <el-tab-pane label="持仓" name="positions">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>持仓列表</span>
              <el-input
                v-model="positionSearchText"
                placeholder="搜索交易对"
                :prefix-icon="Search"
                clearable
                style="width: 200px"
              />
            </div>
          </template>
          
          <el-table :data="filteredPositions" v-loading="loading">
            <el-table-column prop="symbol" label="交易对" width="150" />
            
            <el-table-column prop="side" label="方向" width="100">
              <template #default="{ row }">
                <el-tag :type="row.side === 'long' ? 'success' : 'danger'">
                  {{ row.side === 'long' ? '做多' : '做空' }}
                </el-tag>
              </template>
            </el-table-column>
            
            <el-table-column prop="size" label="持仓数量" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.size || 0, 4) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="entryPrice" label="开仓价格" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.entryPrice || 0, 2) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="markPrice" label="标记价格" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.markPrice || 0, 2) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="unrealizedPnl" label="未实现盈亏" width="150" align="right">
              <template #default="{ row }">
                <span :class="(row.unrealizedPnl || 0) >= 0 ? 'text-success' : 'text-danger'">
                  {{ formatMoney(row.unrealizedPnl || 0, 'USDT', 2) }}
                </span>
              </template>
            </el-table-column>
            
            <el-table-column prop="returnRate" label="收益率" width="120" align="right">
              <template #default="{ row }">
                <span :class="(row.returnRate || 0) >= 0 ? 'text-success' : 'text-danger'">
                  {{ formatPercent((row.returnRate || 0) / 100) }}
                </span>
              </template>
            </el-table-column>
            
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button
                  type="danger"
                  size="small"
                  @click="handleClosePosition(row)"
                >
                  平仓
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
      
      <!-- 订单列表 -->
      <el-tab-pane label="订单" name="orders">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>订单列表</span>
              <div class="filters">
                <el-input
                  v-model="orderSearchText"
                  placeholder="搜索交易对"
                  :prefix-icon="Search"
                  clearable
                  style="width: 200px"
                />
                <el-select v-model="orderStatusFilter" placeholder="状态筛选" clearable style="width: 120px">
                  <el-option label="全部" value="" />
                  <el-option label="待成交" value="pending" />
                  <el-option label="部分成交" value="partially_filled" />
                  <el-option label="已成交" value="filled" />
                  <el-option label="已取消" value="cancelled" />
                </el-select>
              </div>
            </div>
          </template>
          
          <el-table :data="filteredOrders" v-loading="loading">
            <el-table-column prop="orderId" label="订单ID" width="150" />
            
            <el-table-column prop="symbol" label="交易对" width="150" />
            
            <el-table-column prop="side" label="方向" width="100">
              <template #default="{ row }">
                <el-tag :type="row.side === 'buy' ? 'success' : 'danger'">
                  {{ row.side === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </template>
            </el-table-column>
            
            <el-table-column prop="type" label="类型" width="120">
              <template #default="{ row }">
                <el-tag size="small">{{ formatOrderType(row.type) }}</el-tag>
              </template>
            </el-table-column>
            
            <el-table-column prop="price" label="价格" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.price || 0, 2) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="quantity" label="数量" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.quantity || 0, 4) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="filled" label="已成交" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.filled || 0, 4) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="getOrderStatusType(row.status)">
                  {{ formatOrderStatus(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            
            <el-table-column prop="createTime" label="创建时间" width="180">
              <template #default="{ row }">
                {{ formatTime(row.createTime) }}
              </template>
            </el-table-column>
            
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'pending' || row.status === 'partially_filled'"
                  type="warning"
                  size="small"
                  @click="handleCancelOrder(row)"
                >
                  撤单
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
      
      <!-- 交易历史 -->
      <el-tab-pane label="交易历史" name="trades">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>成交记录</span>
              <el-input
                v-model="tradeSearchText"
                placeholder="搜索交易对"
                :prefix-icon="Search"
                clearable
                style="width: 200px"
              />
            </div>
          </template>
          
          <el-table :data="filteredTrades" v-loading="loading">
            <el-table-column prop="tradeId" label="成交ID" width="150" />
            
            <el-table-column prop="orderId" label="订单ID" width="150" />
            
            <el-table-column prop="symbol" label="交易对" width="150" />
            
            <el-table-column prop="side" label="方向" width="100">
              <template #default="{ row }">
                <el-tag :type="row.side === 'buy' ? 'success' : 'danger'">
                  {{ row.side === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </template>
            </el-table-column>
            
            <el-table-column prop="price" label="成交价格" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.price || 0, 2) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="quantity" label="成交数量" width="150" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.quantity || 0, 4) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="fee" label="手续费" width="120" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.fee || 0, 4) }}
              </template>
            </el-table-column>
            
            <el-table-column prop="pnl" label="盈亏" width="120" align="right">
              <template #default="{ row }">
                <span :class="(row.pnl || 0) >= 0 ? 'text-success' : 'text-danger'">
                  {{ formatMoney(row.pnl || 0, 'USDT', 2) }}
                </span>
              </template>
            </el-table-column>
            
            <el-table-column prop="tradeTime" label="成交时间" width="180">
              <template #default="{ row }">
                {{ formatTime(row.tradeTime) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
    
    <!-- 账户配置对话框 -->
    <el-dialog
      v-model="showConfigDialog"
      title="模拟账户配置"
      width="500px"
    >
      <el-form :model="configForm" label-width="120px">
        <el-form-item label="初始资金 (USDT)">
          <el-input-number
            v-model="configForm.initialBalance"
            :min="100"
            :max="10000000"
            :precision="2"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item label="挂单费率 (Maker)">
          <el-input-number
            v-model="configForm.makerFeeRate"
            :min="0"
            :max="1"
            :precision="4"
            :step="0.0001"
            style="width: 100%"
          />
          <div style="color: var(--text-secondary); font-size: 12px; margin-top: 5px;">
            例如：0.001 表示 0.1%（挂单成交时收取）
          </div>
        </el-form-item>
        
        <el-form-item label="市价费率 (Taker)">
          <el-input-number
            v-model="configForm.takerFeeRate"
            :min="0"
            :max="1"
            :precision="4"
            :step="0.0001"
            style="width: 100%"
          />
          <div style="color: var(--text-secondary); font-size: 12px; margin-top: 5px;">
            例如：0.001 表示 0.1%（市价成交时收取）
          </div>
        </el-form-item>
        
        <el-form-item label="滑点设置">
          <el-input-number
            v-model="configForm.slippage"
            :min="0"
            :max="1"
            :precision="4"
            :step="0.0001"
            style="width: 100%"
          />
          <div style="color: var(--text-secondary); font-size: 12px; margin-top: 5px;">
            例如：0.0001 表示 0.01%
          </div>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showConfigDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSaveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatNumber, formatPercent, formatMoney, formatTime } from '@/utils/format'
import {
  Wallet,
  TrendCharts,
  DataAnalysis,
  List,
  Check,
  PieChart,
  Tools,
  Search,
  Refresh,
  Setting
} from '@element-plus/icons-vue'

const activeTab = ref('positions')
const loading = ref(false)
const showConfigDialog = ref(false)
const positionSearchText = ref('')
const orderSearchText = ref('')
const orderStatusFilter = ref('')
const tradeSearchText = ref('')

// 账户信息
const accountInfo = ref({
  balance: 10000,
  equity: 10000,
  totalPnl: 0,
  returnRate: 0
})

// 订单统计
const orderStats = ref({
  total: 0,
  filled: 0,
  trades: 0
})

// 持仓统计
const positionStats = ref({
  total: 0
})

// 持仓列表
const positions = ref([])

// 订单列表
const orders = ref([])

// 成交记录
const trades = ref([])

// 配置表单
const configForm = ref({
  initialBalance: 10000,
  makerFeeRate: 0.001,
  takerFeeRate: 0.001,
  slippage: 0.0001
})

const filteredPositions = computed(() => {
  if (!positionSearchText.value) return positions.value
  
  return positions.value.filter(pos =>
    pos.symbol.toLowerCase().includes(positionSearchText.value.toLowerCase())
  )
})

const filteredOrders = computed(() => {
  let result = orders.value
  
  if (orderSearchText.value) {
    result = result.filter(order =>
      order.symbol.toLowerCase().includes(orderSearchText.value.toLowerCase())
    )
  }
  
  if (orderStatusFilter.value) {
    result = result.filter(order => order.status === orderStatusFilter.value)
  }
  
  return result
})

const filteredTrades = computed(() => {
  if (!tradeSearchText.value) return trades.value
  
  return trades.value.filter(trade =>
    trade.symbol.toLowerCase().includes(tradeSearchText.value.toLowerCase())
  )
})

function formatOrderType(type) {
  const typeMap = {
    'limit': '限价',
    'market': '市价',
    'post_only': '只做Maker',
    'fok': 'FOK',
    'ioc': 'IOC'
  }
  return typeMap[type] || type
}

function formatOrderStatus(status) {
  const statusMap = {
    'pending': '待成交',
    'partially_filled': '部分成交',
    'filled': '已成交',
    'cancelled': '已取消',
    'rejected': '已拒绝'
  }
  return statusMap[status] || status
}

function getOrderStatusType(status) {
  const typeMap = {
    'pending': 'warning',
    'partially_filled': 'info',
    'filled': 'success',
    'cancelled': 'info',
    'rejected': 'danger'
  }
  return typeMap[status] || ''
}

async function handleResetAccount() {
  try {
    await ElMessageBox.confirm(
      '确定要重置模拟账户吗？这将清空所有持仓、订单和交易记录，并恢复初始资金。此操作不可恢复！',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const { papertradingApi } = await import('@/api/papertrading')
    const result = await papertradingApi.resetAccount()
    
    if (result.success) {
      ElMessage.success('账户重置成功')
      // 重新加载数据
      loadData()
    } else {
      ElMessage.error('账户重置失败: ' + (result.message || '未知错误'))
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('账户重置失败: ' + error.message)
    }
  }
}

async function handleClosePosition(row) {
  try {
    await ElMessageBox.confirm(
      `确定要平仓 ${row.symbol} 吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    // TODO: 调用API平仓
    ElMessage.success('平仓成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('平仓失败: ' + error.message)
    }
  }
}

async function handleCancelOrder(row) {
  try {
    await ElMessageBox.confirm(
      `确定要撤销订单 ${row.orderId} 吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    // TODO: 调用API撤单
    ElMessage.success('撤单成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('撤单失败: ' + error.message)
    }
  }
}

async function handleSaveConfig() {
  try {
    const { papertradingApi } = await import('@/api/papertrading')
    const result = await papertradingApi.updateConfig(configForm.value)
    
    if (result.success) {
      ElMessage.success('配置保存成功')
      showConfigDialog.value = false
      // 重新加载数据
      loadData()
    } else {
      ElMessage.error('配置保存失败: ' + (result.message || '未知错误'))
    }
  } catch (error) {
    ElMessage.error('配置保存失败: ' + error.message)
  }
}

function loadData() {
  loading.value = true
  // TODO: 从WebSocket或API加载数据
  setTimeout(() => {
    loading.value = false
  }, 500)
}

onMounted(() => {
  loadData()
})
</script>

<style lang="scss" scoped>
.papertrading-page {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    
    h2 {
      margin: 0 0 5px 0;
    }
    
    p {
      margin: 0;
      color: var(--text-secondary);
    }
    
    .header-actions {
      display: flex;
      gap: 10px;
    }
  }
  
  .overview-row {
    margin-bottom: 20px;
    
    .overview-card {
      :deep(.el-card__body) {
        display: flex;
        align-items: center;
        gap: 20px;
        padding: 24px;
      }
      
      .overview-icon {
        width: 60px;
        height: 60px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 28px;
        color: white;
        
        &.balance {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        
        &.equity {
          background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        &.pnl {
          background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        
        &.return {
          background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
        }
      }
      
      .overview-content {
        flex: 1;
        
        .overview-label {
          font-size: 14px;
          color: var(--text-secondary);
          margin-bottom: 8px;
        }
        
        .overview-value {
          font-size: 24px;
          font-weight: bold;
        }
      }
    }
  }
  
  .stats-row {
    margin-bottom: 20px;
    
    .stat-card {
      :deep(.el-card__body) {
        display: flex;
        align-items: center;
        gap: 15px;
        padding: 20px;
      }
      
      .stat-icon {
        width: 50px;
        height: 50px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        background: #e7f5ed;
        color: #67c23a;
        
        &.filled {
          background: #e1f3ff;
          color: #409eff;
        }
        
        &.positions {
          background: #fdf6ec;
          color: #e6a23c;
        }
        
        &.trades {
          background: #fef0f0;
          color: #f56c6c;
        }
      }
      
      .stat-info {
        .stat-value {
          font-size: 24px;
          font-weight: bold;
          margin-bottom: 5px;
        }
        
        .stat-label {
          font-size: 14px;
          color: var(--text-secondary);
        }
      }
    }
  }
  
  .content-tabs {
    :deep(.el-tabs__content) {
      padding-top: 20px;
    }
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    
    .filters {
      display: flex;
      gap: 10px;
    }
  }
  
  .text-success {
    color: #67c23a;
  }
  
  .text-danger {
    color: #f56c6c;
  }
}
</style>

