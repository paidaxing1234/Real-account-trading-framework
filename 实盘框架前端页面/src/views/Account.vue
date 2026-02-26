<template>
  <div class="account-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>账户管理</h2>
        <p>管理多策略多交易所账户 (OKX / Binance)</p>
      </div>
      <el-button
        type="primary"
        :icon="Plus"
        @click="showAddDialog = true"
        v-permission="'account:create'"
      >
        注册账户
      </el-button>
    </div>

    <!-- 账户概览 -->
    <el-row :gutter="20" class="overview-row">
      <el-col :span="8">
        <el-card class="overview-card">
          <div class="overview-icon">
            <el-icon><Wallet /></el-icon>
          </div>
          <div class="overview-content">
            <div class="overview-label">总资产 (USDT)</div>
            <div class="overview-value">{{ formatMoney(totalEquity, 'USDT', 2) }}</div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="overview-card">
          <div class="overview-icon profit">
            <el-icon><TrendCharts /></el-icon>
          </div>
          <div class="overview-content">
            <div class="overview-label">总盈亏 (USDT)</div>
            <div class="overview-value" :class="totalPnL >= 0 ? 'text-success' : 'text-danger'">
              {{ formatMoney(totalPnL, 'USDT', 2) }}
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="overview-card">
          <div class="overview-icon accounts">
            <el-icon><User /></el-icon>
          </div>
          <div class="overview-content">
            <div class="overview-label">活跃账户数</div>
            <div class="overview-value">{{ activeAccounts.length }} / {{ accounts.length }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 净值曲线图 -->
    <el-card class="equity-chart-card">
      <template #header>
        <div class="card-header">
          <span>账户净值曲线</span>
          <el-radio-group v-model="equityTimeRange" size="small">
            <el-radio-button label="7d">7天</el-radio-button>
            <el-radio-button label="30d">30天</el-radio-button>
            <el-radio-button label="90d">90天</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div class="equity-chart-container">
        <equity-chart :time-range="equityTimeRange" height="300px" />
      </div>
    </el-card>
    
    <!-- 账户列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>账户列表</span>
          <el-input
            v-model="searchText"
            placeholder="搜索账户名称"
            :prefix-icon="Search"
            clearable
            style="width: 200px"
          />
        </div>
      </template>
      
      <el-table :data="filteredAccounts" v-loading="loading">
        <el-table-column type="expand">
          <template #default="{ row }">
            <account-detail :account="row" />
          </template>
        </el-table-column>
        
        <el-table-column prop="name" label="账户名称 / 交易所" min-width="180">
          <template #default="{ row }">
            <div class="account-name clickable" @click="handleAccountClick(row)">
              <el-tag :type="row.exchange === 'okx' ? 'primary' : 'success'" size="small">
                {{ row.exchange?.toUpperCase() || 'OKX' }}
              </el-tag>
              <span class="account-link">{{ row.name || row.strategyId || '默认账户' }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="apiKey" label="API Key" width="200">
          <template #default="{ row }">
            <el-text truncated>{{ maskApiKey(row.apiKey) }}</el-text>
          </template>
        </el-table-column>
        
        <el-table-column prop="balance" label="余额 (USDT)" width="150" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.balance, 2) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="equity" label="净值 (USDT)" width="150" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.equity, 2) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="unrealizedPnl" label="未实现盈亏" width="150" align="right">
          <template #default="{ row }">
            <span :class="row.unrealizedPnl >= 0 ? 'text-success' : 'text-danger'">
              {{ formatNumber(row.unrealizedPnl, 2) }}
            </span>
          </template>
        </el-table-column>
        
        <el-table-column prop="returnRate" label="收益率" width="100" align="right">
          <template #default="{ row }">
            <span :class="row.returnRate >= 0 ? 'text-success' : 'text-danger'">
              {{ formatPercent(row.returnRate / 100) }}
            </span>
          </template>
        </el-table-column>
        
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.isTestnet ? 'warning' : 'success'">
              {{ row.isTestnet ? '模拟盘' : '实盘' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <Permission :permission="'account:sync'">
              <el-button
                type="primary"
                size="small"
                :icon="RefreshRight"
                @click="handleSync(row)"
              >
                同步
              </el-button>
            </Permission>
            <Permission :permission="'account:delete'">
              <el-button
                type="danger"
                size="small"
                @click="handleDelete(row)"
              >
                注销
              </el-button>
            </Permission>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 添加账户对话框 -->
    <add-account-dialog
      v-model="showAddDialog"
      @success="handleAddSuccess"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { formatNumber, formatPercent, formatMoney } from '@/utils/format'
import {
  Plus,
  Search,
  Wallet,
  TrendCharts,
  User,
  RefreshRight
} from '@element-plus/icons-vue'

import AccountDetail from '@/components/Account/AccountDetail.vue'
import AddAccountDialog from '@/components/Account/AddAccountDialog.vue'
import EquityChart from '@/components/Charts/EquityChart.vue'

const router = useRouter()
const accountStore = useAccountStore()

const searchText = ref('')
const showAddDialog = ref(false)
const equityTimeRange = ref('30d')

const loading = computed(() => accountStore.loading)
const accounts = computed(() => accountStore.accounts)
const activeAccounts = computed(() => accountStore.activeAccounts)
const totalEquity = computed(() => accountStore.totalEquity)
const totalPnL = computed(() => accountStore.totalPnL)

const filteredAccounts = computed(() => {
  if (!searchText.value) return accounts.value

  return accounts.value.filter(acc =>
    (acc.strategyId || '').toLowerCase().includes(searchText.value.toLowerCase())
  )
})

function maskApiKey(apiKey) {
  if (!apiKey) return ''
  const len = apiKey.length
  if (len <= 8) return apiKey
  return apiKey.substring(0, 4) + '****' + apiKey.substring(len - 4)
}

async function handleSync(row) {
  try {
    await accountStore.syncAccount(row.strategyId || 'default')
    ElMessage.success('账户同步成功')
  } catch (error) {
    ElMessage.error('账户同步失败: ' + error.message)
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      '确定要注销该账户吗? 此操作不可恢复。',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await accountStore.deleteAccount(row.strategyId || 'default')
    ElMessage.success('账户注销成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('账户注销失败: ' + error.message)
    }
  }
}

function handleAddSuccess() {
  ElMessage.success('账户注册成功')
  accountStore.fetchAccounts()
}

function handleAccountClick(row) {
  router.push({
    path: '/account-positions',
    query: { accountId: row.id || row.strategyId }
  })
}

onMounted(() => {
  accountStore.fetchAccounts()
})
</script>

<style lang="scss" scoped>
.account-page {
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
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 28px;
        color: white;
        
        &.profit {
          background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        &.accounts {
          background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
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
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .account-name {
    display: flex;
    align-items: center;
    gap: 10px;

    &.clickable {
      cursor: pointer;

      .account-link {
        color: var(--el-color-primary);

        &:hover {
          text-decoration: underline;
        }
      }
    }
  }

  .equity-chart-card {
    margin-bottom: 20px;

    .equity-chart-container {
      height: 300px;
    }
  }
}
</style>

