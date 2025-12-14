<template>
  <div class="logs-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>系统日志</h2>
        <p>查看来自C++实盘框架的所有日志信息</p>
      </div>
      <div class="header-actions">
        <el-radio-group v-model="viewMode" size="default" style="margin-right: 15px;">
          <el-radio-button value="console">
            <el-icon><Monitor /></el-icon>
            控制台视图
          </el-radio-button>
          <el-radio-button value="table">
            <el-icon><List /></el-icon>
            表格视图
          </el-radio-button>
        </el-radio-group>
        <el-button :icon="Download" @click="handleExport">
          导出日志
        </el-button>
        <el-button 
          type="danger" 
          :icon="Delete" 
          @click="handleClear"
        >
          清空日志
        </el-button>
      </div>
    </div>
    
    <!-- 控制台视图 -->
    <div v-if="viewMode === 'console'" class="console-view">
      <el-alert
        v-if="componentError"
        title="日志组件加载错误"
        type="error"
        :description="componentError"
        show-icon
        :closable="false"
        style="margin-bottom: 20px;"
      >
        <template #default>
          <el-button size="small" @click="reloadComponent">重新加载</el-button>
        </template>
      </el-alert>
      
      <template v-else>
        <LogSender v-if="!senderError" @error="handleSenderError" />
        <LogConsole v-if="!consoleError" @error="handleConsoleError" />
      </template>
    </div>
    
    <!-- 表格视图 -->
    <div v-else>
      <!-- 日志统计 -->
      <el-row :gutter="20" class="stats-row">
        <el-col :span="6">
          <el-card class="stat-mini">
            <el-statistic title="总日志数" :value="stats.total">
              <template #prefix>
                <el-icon><Document /></el-icon>
              </template>
            </el-statistic>
          </el-card>
        </el-col>
        
        <el-col :span="6">
          <el-card class="stat-mini">
            <el-statistic title="错误日志" :value="stats.error">
              <template #prefix>
                <el-icon style="color: #f56c6c;"><CircleClose /></el-icon>
              </template>
            </el-statistic>
          </el-card>
        </el-col>
        
        <el-col :span="6">
          <el-card class="stat-mini">
            <el-statistic title="警告日志" :value="stats.warning">
              <template #prefix>
                <el-icon style="color: #e6a23c;"><Warning /></el-icon>
              </template>
            </el-statistic>
          </el-card>
        </el-col>
        
        <el-col :span="6">
          <el-card class="stat-mini">
            <el-statistic title="信息日志" :value="stats.info">
              <template #prefix>
                <el-icon style="color: #409eff;"><InfoFilled /></el-icon>
              </template>
            </el-statistic>
          </el-card>
        </el-col>
      </el-row>
      
      <!-- 筛选和搜索 -->
      <el-card class="filter-card">
      <el-form :inline="true" :model="filters">
        <el-form-item label="日志级别">
          <el-select v-model="filters.level" placeholder="全部" style="width: 120px">
            <el-option label="全部" value="all" />
            <el-option label="调试" value="debug" />
            <el-option label="信息" value="info" />
            <el-option label="警告" value="warning" />
            <el-option label="错误" value="error" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="日志来源">
          <el-select v-model="filters.source" placeholder="全部" style="width: 150px">
            <el-option 
              v-for="source in sources" 
              :key="source" 
              :label="formatSource(source)" 
              :value="source" 
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="关键词">
          <el-input 
            v-model="filters.keyword" 
            placeholder="搜索日志内容" 
            clearable 
            style="width: 200px"
          />
        </el-form-item>
        
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            style="width: 360px"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="applyFilters">
            搜索
          </el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
        
        <el-form-item label="自动滚动">
          <el-switch v-model="autoScroll" />
        </el-form-item>
      </el-form>
      </el-card>
      
      <!-- 日志列表 -->
      <el-card>
      <div class="log-container" ref="logContainerRef">
        <el-table
          :data="displayedLogs"
          :height="tableHeight"
          stripe
          :row-class-name="getRowClassName"
        >
          <el-table-column prop="timestamp" label="时间" width="180">
            <template #default="{ row }">
              {{ formatTime(row.timestamp) }}
            </template>
          </el-table-column>
          
          <el-table-column prop="level" label="级别" width="100">
            <template #default="{ row }">
              <el-tag :type="getLevelType(row.level)" size="small">
                {{ formatLevel(row.level) }}
              </el-tag>
            </template>
          </el-table-column>
          
          <el-table-column prop="source" label="来源" width="150">
            <template #default="{ row }">
              <el-tag size="small">{{ formatSource(row.source) }}</el-tag>
            </template>
          </el-table-column>
          
          <el-table-column prop="message" label="日志内容" min-width="400">
            <template #default="{ row }">
              <div class="log-message">
                {{ row.message }}
              </div>
            </template>
          </el-table-column>
          
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                type="primary"
                size="small"
                @click="handleViewDetail(row)"
              >
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="filteredLogs.length"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
      </el-card>
    </div>
    
    <!-- 日志详情对话框 -->
    <el-dialog 
      v-model="showDetailDialog" 
      title="日志详情" 
      width="800px"
      :append-to-body="true"
    >
      <div v-if="selectedLog" class="log-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="时间">
            {{ formatTime(selectedLog.timestamp) }}
          </el-descriptions-item>
          <el-descriptions-item label="级别">
            <el-tag :type="getLevelType(selectedLog.level)">
              {{ formatLevel(selectedLog.level) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="来源">
            <el-tag>{{ formatSource(selectedLog.source) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="日志ID">
            {{ selectedLog.id }}
          </el-descriptions-item>
          <el-descriptions-item label="消息内容" :span="2">
            <div class="log-message-detail">{{ selectedLog.message }}</div>
          </el-descriptions-item>
          <el-descriptions-item v-if="selectedLog.data" label="附加数据" :span="2">
            <pre class="log-data">{{ JSON.stringify(selectedLog.data, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
        <el-button type="primary" @click="copyLogDetail">复制详情</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useLogStore } from '@/stores/log'
import { formatTime } from '@/utils/format'
import LogConsole from '@/components/Log/LogConsole.vue'
import LogSender from '@/components/Log/LogSender.vue'
import {
  Download,
  Delete,
  Search,
  Document,
  CircleClose,
  Warning,
  InfoFilled,
  Monitor,
  List
} from '@element-plus/icons-vue'

const logStore = useLogStore()

// 视图模式
const viewMode = ref('console')

// 错误处理
const componentError = ref(null)
const senderError = ref(false)
const consoleError = ref(false)

function handleSenderError(error) {
  console.error('LogSender error:', error)
  senderError.value = true
  componentError.value = 'LogSender组件加载失败'
}

function handleConsoleError(error) {
  console.error('LogConsole error:', error)
  consoleError.value = true
  componentError.value = 'LogConsole组件加载失败'
}

function reloadComponent() {
  componentError.value = null
  senderError.value = false
  consoleError.value = false
}

const filters = reactive({
  level: 'all',
  source: 'all',
  keyword: '',
  dateRange: null
})

const pagination = reactive({
  page: 1,
  pageSize: 50
})

const showDetailDialog = ref(false)
const selectedLog = ref(null)
const autoScroll = ref(false)
const logContainerRef = ref(null)
const tableHeight = ref(600)

// 计算属性
const stats = computed(() => logStore.stats)
const sources = computed(() => logStore.sources)

const filteredLogs = computed(() => {
  return logStore.filterLogs(filters)
})

const displayedLogs = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  const end = start + pagination.pageSize
  return filteredLogs.value.slice(start, end)
})

// 格式化函数
function formatLevel(level) {
  const levelMap = {
    debug: '调试',
    info: '信息',
    warning: '警告',
    error: '错误'
  }
  return levelMap[level] || level
}

function formatSource(source) {
  if (source === 'all') return '全部来源'
  
  const sourceMap = {
    system: '系统',
    strategy: '策略',
    order: '订单',
    account: '账户',
    market: '行情',
    backend: '后端'
  }
  return sourceMap[source] || source
}

function getLevelType(level) {
  const typeMap = {
    debug: 'info',
    info: '',
    warning: 'warning',
    error: 'danger'
  }
  return typeMap[level] || ''
}

function getRowClassName({ row }) {
  return `log-row-${row.level}`
}

// 事件处理
function applyFilters() {
  pagination.page = 1
}

function resetFilters() {
  filters.level = 'all'
  filters.source = 'all'
  filters.keyword = ''
  filters.dateRange = null
  pagination.page = 1
}

function handleSizeChange() {
  pagination.page = 1
}

function handlePageChange() {
  if (autoScroll.value) {
    nextTick(() => {
      if (logContainerRef.value) {
        logContainerRef.value.scrollTop = 0
      }
    })
  }
}

async function handleClear() {
  try {
    await ElMessageBox.confirm(
      '确定要清空所有日志吗？此操作不可恢复。',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    logStore.clearLogs()
    ElMessage.success('日志已清空')
  } catch (error) {
    // 用户取消
  }
}

function handleExport() {
  try {
    logStore.exportLogs(filteredLogs.value)
    ElMessage.success('日志导出成功')
  } catch (error) {
    ElMessage.error('日志导出失败: ' + error.message)
  }
}

function handleViewDetail(row) {
  selectedLog.value = row
  showDetailDialog.value = true
}

function copyLogDetail() {
  if (!selectedLog.value) return
  
  const detail = `
时间: ${formatTime(selectedLog.value.timestamp)}
级别: ${formatLevel(selectedLog.value.level)}
来源: ${formatSource(selectedLog.value.source)}
消息: ${selectedLog.value.message}
${selectedLog.value.data ? '附加数据:\n' + JSON.stringify(selectedLog.value.data, null, 2) : ''}
  `.trim()
  
  navigator.clipboard.writeText(detail).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

// 监听日志更新，自动滚动到最新
watch(() => logStore.logs.length, () => {
  if (autoScroll.value && pagination.page === 1) {
    nextTick(() => {
      if (logContainerRef.value) {
        logContainerRef.value.scrollTop = 0
      }
    })
  }
})

onMounted(() => {
  // 计算表格高度
  const updateTableHeight = () => {
    tableHeight.value = window.innerHeight - 450
  }
  updateTableHeight()
  window.addEventListener('resize', updateTableHeight)
  
  onUnmounted(() => {
    window.removeEventListener('resize', updateTableHeight)
  })
})
</script>

<style lang="scss" scoped>
.logs-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  
  .console-view {
    flex: 1;
    min-height: 0;
    margin-bottom: 20px;
  }
  
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-shrink: 0;
    
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
  
  .stats-row {
    margin-bottom: 20px;
    
    .stat-mini {
      :deep(.el-card__body) {
        padding: 20px;
      }
    }
  }
  
  .filter-card {
    margin-bottom: 20px;
    
    :deep(.el-card__body) {
      padding: 15px 20px;
    }
  }
  
  .log-container {
    overflow-y: auto;
  }
  
  :deep(.el-table) {
    .log-row-error {
      background-color: #fef0f0;
      
      &:hover > td {
        background-color: #fde2e2 !important;
      }
    }
    
    .log-row-warning {
      background-color: #fdf6ec;
      
      &:hover > td {
        background-color: #faecd8 !important;
      }
    }
    
    .log-row-debug {
      background-color: #f4f4f5;
      
      &:hover > td {
        background-color: #e9e9eb !important;
      }
    }
  }
  
  .log-message {
    word-break: break-word;
    line-height: 1.5;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
  }
  
  :deep(.el-pagination) {
    margin-top: 20px;
    justify-content: flex-end;
  }
}

.log-detail {
  .log-message-detail {
    word-break: break-word;
    line-height: 1.6;
    font-family: 'Consolas', 'Monaco', monospace;
    padding: 10px;
    background: #f5f7fa;
    border-radius: 4px;
  }
  
  .log-data {
    margin: 0;
    padding: 10px;
    background: #f5f7fa;
    border-radius: 4px;
    font-size: 12px;
    line-height: 1.5;
    overflow-x: auto;
    max-height: 300px;
  }
}
</style>


