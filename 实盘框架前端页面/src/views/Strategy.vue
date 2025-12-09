<template>
  <div class="strategy-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>策略管理</h2>
        <p>管理和监控所有交易策略</p>
      </div>
      <el-button 
        type="primary" 
        :icon="Plus" 
        @click="showCreateDialog = true"
        v-permission="'strategy:create'"
      >
        添加策略
      </el-button>
    </div>
    
    <!-- 策略统计 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card running">
          <div class="stat-icon">
            <el-icon><VideoPlay /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ runningStrategies.length }}</div>
            <div class="stat-label">运行中</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card pending">
          <div class="stat-icon">
            <el-icon><Clock /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ pendingStrategies.length }}</div>
            <div class="stat-label">待启动</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card stopped">
          <div class="stat-icon">
            <el-icon><VideoPause /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stoppedStrategies.length }}</div>
            <div class="stat-label">已停止</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card error">
          <div class="stat-icon">
            <el-icon><Warning /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ errorStrategies.length }}</div>
            <div class="stat-label">异常</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 策略列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>策略列表</span>
          <div class="filters">
            <el-input
              v-model="searchText"
              placeholder="搜索策略名称"
              :prefix-icon="Search"
              clearable
              style="width: 200px"
            />
            <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 120px">
              <el-option label="运行中" value="running" />
              <el-option label="已停止" value="stopped" />
              <el-option label="待启动" value="pending" />
              <el-option label="异常" value="error" />
            </el-select>
          </div>
        </div>
      </template>
      
      <el-table :data="filteredStrategies" v-loading="loading">
        <el-table-column prop="name" label="策略名称" min-width="150">
          <template #default="{ row }">
            <div class="strategy-name">
              <el-icon><Document /></el-icon>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="type" label="类型" width="120" />
        
        <el-table-column prop="account" label="账户" width="150" />
        
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ formatStrategyStatus(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="pnl" label="盈亏 (USDT)" width="120" align="right">
          <template #default="{ row }">
            <span :class="row.pnl >= 0 ? 'text-success' : 'text-danger'">
              {{ formatNumber(row.pnl, 2) }}
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
        
        <el-table-column prop="trades" label="成交笔数" width="100" align="right" />
        
        <el-table-column prop="runTime" label="运行时长" width="120" />
        
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <Permission :permission="'strategy:stop'">
              <el-button
                v-if="row.status === 'running'"
                type="warning"
                size="small"
                @click="handleStopStrategy(row)"
              >
                停止
              </el-button>
            </Permission>
            <Permission :permission="'strategy:start'">
              <el-button
                v-if="row.status !== 'running'"
                type="success"
                size="small"
                @click="handleStartStrategy(row)"
              >
                启动
              </el-button>
            </Permission>
            <el-button type="primary" size="small" @click="handleViewDetail(row)">
              详情
            </el-button>
            <Permission :permission="'strategy:delete'">
              <el-button type="danger" size="small" @click="handleDelete(row)">
                删除
              </el-button>
            </Permission>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 创建策略对话框 -->
    <create-strategy-dialog
      v-model="showCreateDialog"
      @success="handleCreateSuccess"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useStrategyStore } from '@/stores/strategy'
import { formatNumber, formatPercent, formatStrategyStatus } from '@/utils/format'
import {
  Plus,
  Search,
  VideoPlay,
  VideoPause,
  Clock,
  Warning,
  Document
} from '@element-plus/icons-vue'

import CreateStrategyDialog from '@/components/Strategy/CreateStrategyDialog.vue'

const strategyStore = useStrategyStore()

const searchText = ref('')
const statusFilter = ref('')
const showCreateDialog = ref(false)

const loading = computed(() => strategyStore.loading)
const strategies = computed(() => strategyStore.strategies)
const runningStrategies = computed(() => strategyStore.runningStrategies)
const stoppedStrategies = computed(() => strategyStore.stoppedStrategies)
const pendingStrategies = computed(() => strategyStore.pendingStrategies)
const errorStrategies = computed(() => strategyStore.errorStrategies)

const filteredStrategies = computed(() => {
  let result = strategies.value
  
  if (searchText.value) {
    result = result.filter(s => 
      s.name.toLowerCase().includes(searchText.value.toLowerCase())
    )
  }
  
  if (statusFilter.value) {
    result = result.filter(s => s.status === statusFilter.value)
  }
  
  return result
})

function getStatusType(status) {
  const typeMap = {
    running: 'success',
    stopped: 'info',
    pending: 'warning',
    error: 'danger'
  }
  return typeMap[status] || 'info'
}

async function handleStartStrategy(row) {
  try {
    await strategyStore.startStrategy(row.id)
    ElMessage.success('策略启动成功')
  } catch (error) {
    ElMessage.error('策略启动失败: ' + error.message)
  }
}

async function handleStopStrategy(row) {
  try {
    await ElMessageBox.confirm(
      '确定要停止该策略吗?',
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await strategyStore.stopStrategy(row.id)
    ElMessage.success('策略停止成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('策略停止失败: ' + error.message)
    }
  }
}

function handleViewDetail(row) {
  // TODO: 跳转到策略详情页
  console.log('查看详情:', row)
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      '确定要删除该策略吗? 此操作不可恢复。',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await strategyStore.deleteStrategy(row.id)
    ElMessage.success('策略删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('策略删除失败: ' + error.message)
    }
  }
}

function handleCreateSuccess() {
  ElMessage.success('策略创建成功')
  strategyStore.fetchStrategies()
}

onMounted(() => {
  strategyStore.fetchStrategies()
})
</script>

<style lang="scss" scoped>
.strategy-page {
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
      
      &.running .stat-icon {
        background: #e7f5ed;
        color: #67c23a;
      }
      
      &.pending .stat-icon {
        background: #fdf6ec;
        color: #e6a23c;
      }
      
      &.stopped .stat-icon {
        background: #f4f4f5;
        color: #909399;
      }
      
      &.error .stat-icon {
        background: #fef0f0;
        color: #f56c6c;
      }
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
  
  .strategy-name {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}
</style>

