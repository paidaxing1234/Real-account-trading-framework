<template>
  <div class="strategy-logs-page">
    <div class="page-header">
      <div>
        <h2>策略日志</h2>
        <p>查看策略运行日志和源代码</p>
      </div>
    </div>

    <el-row :gutter="20">
      <!-- 左侧：文件列表 -->
      <el-col :span="6">
        <el-card>
          <template #header>
            <el-tabs v-model="activeTab" @tab-change="handleTabChange">
              <el-tab-pane label="日志文件" name="logs" />
              <el-tab-pane label="策略代码" name="source" />
            </el-tabs>
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
            <div v-if="filteredFiles.length === 0" class="no-files">暂无文件</div>
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
                <template v-if="activeTab === 'logs'">
                  <el-select v-model="logTailLines" style="width: 130px" @change="refreshContent">
                    <el-option label="最近 100 行" :value="100" />
                    <el-option label="最近 200 行" :value="200" />
                    <el-option label="最近 500 行" :value="500" />
                    <el-option label="最近 1000 行" :value="1000" />
                  </el-select>
                  <el-button :icon="Refresh" @click="refreshContent" :loading="contentLoading">刷新</el-button>
                  <el-switch v-model="autoRefresh" active-text="自动刷新" />
                </template>
              </div>
            </div>
          </template>

          <div class="content-viewer" ref="viewerRef" v-loading="contentLoading">
            <div v-if="!selectedFile" class="content-empty">← 请从左侧选择文件查看</div>
            <div v-else-if="activeTab === 'logs' && logLines.length === 0 && !contentLoading" class="content-empty">暂无日志内容</div>
            <pre v-else-if="activeTab === 'logs'" class="log-content"><code v-for="(line, idx) in logLines" :key="idx" :class="getLogLineClass(line)">{{ line }}
</code></pre>
            <pre v-else-if="activeTab === 'source'" class="source-content"><code>{{ sourceContent }}</code></pre>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { strategyApi } from '@/api/strategy'

const activeTab = ref('logs')
const fileSearch = ref('')
const selectedFile = ref('')
const filesLoading = ref(false)
const contentLoading = ref(false)
const logTailLines = ref(200)
const autoRefresh = ref(false)
const viewerRef = ref(null)

const logFiles = ref([])
const sourceFiles = ref([])
const logLines = ref([])
const sourceContent = ref('')
let autoRefreshTimer = null

const filteredFiles = computed(() => {
  const files = activeTab.value === 'logs' ? logFiles.value : sourceFiles.value
  if (!fileSearch.value) return files
  return files.filter(f => f.filename.toLowerCase().includes(fileSearch.value.toLowerCase()))
})

async function loadLogFiles() {
  filesLoading.value = true
  try {
    const res = await strategyApi.getStrategyLogFiles()
    logFiles.value = (res.data || []).sort((a, b) => b.filename.localeCompare(a.filename))
  } finally { filesLoading.value = false }
}

async function loadSourceFiles() {
  filesLoading.value = true
  try {
    const res = await strategyApi.listStrategyFiles()
    sourceFiles.value = (res.data || []).sort((a, b) => a.filename.localeCompare(b.filename))
  } finally { filesLoading.value = false }
}

async function handleSelectFile(file) {
  selectedFile.value = file.filename
  contentLoading.value = true
  try {
    if (activeTab.value === 'logs') {
      const res = await strategyApi.getStrategyLogs(file.filename, logTailLines.value)
      logLines.value = res.success && res.data ? res.data.lines || [] : []
      await nextTick()
      if (viewerRef.value) viewerRef.value.scrollTop = viewerRef.value.scrollHeight
    } else {
      const res = await strategyApi.getStrategySource(file.filename)
      sourceContent.value = res.success && res.data ? res.data.content || '' : '加载失败'
    }
  } finally { contentLoading.value = false }
}

async function refreshContent() {
  if (!selectedFile.value) return
  const file = { filename: selectedFile.value }
  await handleSelectFile(file)
}

function handleTabChange() {
  selectedFile.value = ''
  logLines.value = []
  sourceContent.value = ''
  fileSearch.value = ''
  autoRefresh.value = false
  if (activeTab.value === 'logs') loadLogFiles()
  else loadSourceFiles()
}
</script>

