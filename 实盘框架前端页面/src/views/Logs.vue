<template>
  <div class="logs-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>系统日志</h2>
        <p>查看来自C++实盘框架的所有日志信息</p>
      </div>
      <div class="header-actions">
        <el-radio-group v-model="viewMode" size="default">
          <el-radio-button value="console">
            <el-icon><Monitor /></el-icon>
            控制台视图
          </el-radio-button>
          <el-radio-button value="files">
            <el-icon><FolderOpened /></el-icon>
            文件视图
          </el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 控制台视图（保持原样） -->
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

    <!-- 文件视图 -->
    <div v-else>
      <el-row :gutter="20">
        <!-- 左侧：文件列表 -->
        <el-col :span="6">
          <el-card>
            <template #header>
              <span style="font-weight: 600;">日志文件</span>
            </template>

            <el-input v-model="fileSearch" placeholder="搜索文件..." clearable style="margin-bottom: 10px" />

            <div class="file-list" v-loading="filesLoading">
              <div
                v-for="file in filteredFiles"
                :key="file.filename"
                class="file-item"
                :class="{ active: selectedFile === file.filename }"
                @click="handleSelectFile(file)"
              >
                <div class="file-name">{{ file.filename }}</div>
                <div class="file-size">{{ formatFileSize(file.size) }}</div>
              </div>
              <div v-if="filteredFiles.length === 0 && !filesLoading" class="no-files">暂无文件</div>
            </div>
          </el-card>
        </el-col>

        <!-- 右侧：内容查看 -->
        <el-col :span="18">
          <el-card>
            <template #header>
              <div class="content-header">
                <span>{{ selectedFile || '请选择文件' }}</span>
                <div class="toolbar" v-if="selectedFile">
                  <el-select v-model="logTailLines" style="width: 130px" @change="refreshContent">
                    <el-option label="最近 100 行" :value="100" />
                    <el-option label="最近 200 行" :value="200" />
                    <el-option label="最近 500 行" :value="500" />
                    <el-option label="最近 1000 行" :value="1000" />
                  </el-select>
                  <el-button :icon="Refresh" @click="refreshContent" :loading="contentLoading">刷新</el-button>
                  <el-button :icon="Download" @click="handleExport" :loading="exporting">导出</el-button>
                  <el-switch v-model="autoRefresh" active-text="自动刷新" />
                </div>
              </div>
            </template>

            <div class="content-viewer" ref="viewerRef" v-loading="contentLoading">
              <div v-if="!selectedFile" class="content-empty">← 请从左侧选择文件查看</div>
              <div v-else-if="logLines.length === 0 && !contentLoading" class="content-empty">暂无日志内容</div>
              <pre v-else class="log-content"><code v-for="(line, idx) in logLines" :key="idx" :class="getLogLineClass(line)">{{ line }}
</code></pre>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Refresh, Monitor, FolderOpened, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import LogConsole from '@/components/Log/LogConsole.vue'
import LogSender from '@/components/Log/LogSender.vue'
import { strategyApi } from '@/api/strategy'

// ========== 视图切换 ==========
const viewMode = ref('console')

// ========== 控制台视图（保持原有逻辑） ==========
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

// ========== 文件视图 ==========
const fileSearch = ref('')
const selectedFile = ref('')
const filesLoading = ref(false)
const contentLoading = ref(false)
const logTailLines = ref(200)
const autoRefresh = ref(false)
const viewerRef = ref(null)

const logFiles = ref([])
const logLines = ref([])
const exporting = ref(false)
let autoRefreshTimer = null

const filteredFiles = computed(() => {
  if (!fileSearch.value) return logFiles.value
  return logFiles.value.filter(f => f.filename.toLowerCase().includes(fileSearch.value.toLowerCase()))
})

async function loadLogFiles() {
  filesLoading.value = true
  try {
    const res = await strategyApi.getSystemLogFiles()
    logFiles.value = (res.data || []).sort((a, b) => b.filename.localeCompare(a.filename))
  } finally { filesLoading.value = false }
}

async function handleSelectFile(file) {
  selectedFile.value = file.filename
  contentLoading.value = true
  try {
    const res = await strategyApi.getSystemLogs(file.filename, logTailLines.value)
    logLines.value = res.success && res.data ? res.data.lines || [] : []
    await nextTick()
    if (viewerRef.value) viewerRef.value.scrollTop = viewerRef.value.scrollHeight
  } finally { contentLoading.value = false }
}

async function refreshContent() {
  if (!selectedFile.value) return
  await handleSelectFile({ filename: selectedFile.value })
}

async function handleExport() {
  if (!selectedFile.value) return
  exporting.value = true
  try {
    const res = await strategyApi.downloadLogFile(selectedFile.value, 'system')
    if (res.success && res.data?.content != null) {
      const blob = new Blob([res.data.content], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = selectedFile.value
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success('导出成功')
    } else {
      ElMessage.error(res.message || '导出失败')
    }
  } catch (e) {
    ElMessage.error('导出失败: ' + e.message)
  } finally {
    exporting.value = false
  }
}

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i]
}

function getLogLineClass(line) {
  if (!line) return ''
  if (line.includes('[ERROR]') || line.includes('ERROR')) return 'log-error'
  if (line.includes('[WARN]') || line.includes('WARNING')) return 'log-warn'
  if (line.includes('[DEBUG]')) return 'log-debug'
  return ''
}

// 切换到文件视图时加载文件列表
watch(viewMode, (val) => {
  if (val === 'files') loadLogFiles()
})

watch(autoRefresh, (val) => {
  if (val) {
    autoRefreshTimer = setInterval(() => {
      if (selectedFile.value && viewMode.value === 'files') refreshContent()
    }, 3000)
  } else {
    if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null }
  }
})

onUnmounted(() => { if (autoRefreshTimer) clearInterval(autoRefreshTimer) })
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

    h2 { margin: 0 0 5px 0; }
    p { margin: 0; color: var(--text-secondary); }

    .header-actions {
      display: flex;
      gap: 10px;
    }
  }

  .file-list {
    max-height: 65vh;
    overflow-y: auto;

    .file-item {
      padding: 8px 12px;
      cursor: pointer;
      border-radius: 4px;
      border-bottom: 1px solid var(--border-color-light, #ebeef5);
      &:hover { background: var(--el-fill-color-light); }
      &.active { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
      .file-name { font-size: 13px; word-break: break-all; }
      .file-size { font-size: 11px; color: #999; margin-top: 2px; }
    }

    .no-files { text-align: center; color: #999; padding: 30px 0; }
  }

  .content-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    .toolbar { display: flex; align-items: center; gap: 10px; }
  }

  .content-viewer {
    height: 70vh;
    overflow-y: auto;
    background: #1e1e1e;
    border-radius: 6px;
    padding: 12px;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.5;

    .content-empty { color: #888; text-align: center; padding: 40px; }

    .log-content {
      margin: 0; padding: 0; white-space: pre-wrap; word-break: break-all;
      code {
        display: block; color: #d4d4d4; padding: 1px 0;
        &.log-error { color: #f56c6c; background: rgba(245,108,108,0.1); }
        &.log-warn { color: #e6a23c; background: rgba(230,162,60,0.1); }
        &.log-debug { color: #909399; }
      }
    }
  }
}
</style>
