<template>
  <div class="paper-trading-page">
    <div class="page-header">
      <div>
        <h2>模拟交易 (Paper Trading)</h2>
        <p>使用真实行情数据进行模拟交易测试</p>
      </div>
      <el-button
        v-if="!isRunning"
        type="primary"
        :icon="VideoPlay"
        @click="showConfigDialog = true"
      >
        启动模拟交易
      </el-button>
      <el-button
        v-else
        type="danger"
        :icon="VideoPause"
        @click="handleStop"
      >
        停止模拟交易
      </el-button>
    </div>

    <!-- 运行状态 -->
    <el-card v-if="isRunning" class="status-card">
      <div class="status-header">
        <el-tag type="success" size="large">
          <el-icon><VideoPlay /></el-icon>
          运行中
        </el-tag>
        <span class="run-time">运行时长: {{ runTime }}</span>
      </div>

      <el-descriptions :column="3" border class="mt-4">
        <el-descriptions-item label="策略">{{ currentConfig.strategy }}</el-descriptions-item>
        <el-descriptions-item label="交易对">{{ currentConfig.symbol }}</el-descriptions-item>
        <el-descriptions-item label="交易所">{{ currentConfig.exchange }}</el-descriptions-item>
        <el-descriptions-item label="初始资金">{{ currentConfig.initialBalance }} USDT</el-descriptions-item>
        <el-descriptions-item label="当前权益">{{ equity.toFixed(2) }} USDT</el-descriptions-item>
        <el-descriptions-item label="收益率">
          <span :class="returnRate >= 0 ? 'text-success' : 'text-danger'">
            {{ returnRate.toFixed(2) }}%
          </span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 账户统计 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card>
          <el-statistic title="总权益" :value="equity" suffix="USDT" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="总盈亏" :value="totalPnl" suffix="USDT">
            <template #prefix>
              <el-icon :class="totalPnl >= 0 ? 'text-success' : 'text-danger'">
                <component :is="totalPnl >= 0 ? TrendCharts : 'CaretBottom'" />
              </el-icon>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="成交笔数" :value="tradeCount" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="持仓数量" :value="positionCount" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 配置对话框 -->
    <el-dialog
      v-model="showConfigDialog"
      title="配置模拟交易"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-divider content-position="left">账户配置</el-divider>

        <el-form-item label="交易所" prop="exchange">
          <el-select v-model="form.exchange" style="width: 100%">
            <el-option label="OKX" value="okx" />
            <el-option label="Binance" value="binance" />
          </el-select>
        </el-form-item>

        <el-form-item label="API Key" prop="apiKey">
          <el-input v-model="form.apiKey" placeholder="用于获取真实行情数据" show-password />
        </el-form-item>

        <el-form-item label="Secret Key" prop="secretKey">
          <el-input v-model="form.secretKey" show-password />
        </el-form-item>

        <el-form-item label="Passphrase" prop="passphrase" v-if="form.exchange === 'okx'">
          <el-input v-model="form.passphrase" show-password />
        </el-form-item>

        <el-form-item label="初始资金">
          <el-input-number v-model="form.initialBalance" :min="1000" :max="1000000" :step="1000" />
          <span style="margin-left: 10px">USDT</span>
        </el-form-item>

        <el-divider content-position="left">策略配置</el-divider>

        <el-form-item label="策略类型" prop="strategy">
          <el-select v-model="form.strategy" style="width: 100%">
            <el-option label="网格策略" value="grid" />
            <el-option label="趋势策略" value="trend" />
            <el-option label="做市策略" value="market_making" />
          </el-select>
        </el-form-item>

        <el-form-item label="交易对" prop="symbol">
          <el-select v-model="form.symbol" style="width: 100%" filterable>
            <el-option label="BTC-USDT-SWAP" value="BTC-USDT-SWAP" />
            <el-option label="ETH-USDT-SWAP" value="ETH-USDT-SWAP" />
            <el-option label="SOL-USDT-SWAP" value="SOL-USDT-SWAP" />
            <el-option label="BNB-USDT-SWAP" value="BNB-USDT-SWAP" />
          </el-select>
        </el-form-item>

        <!-- 网格策略参数 -->
        <template v-if="form.strategy === 'grid'">
          <el-form-item label="网格数量">
            <el-input-number v-model="form.gridNum" :min="5" :max="50" />
          </el-form-item>

          <el-form-item label="网格间距">
            <el-input-number v-model="form.gridSpread" :min="0.0001" :max="0.01" :step="0.0001" :precision="4" />
            <span style="margin-left: 10px">{{ (form.gridSpread * 100).toFixed(2) }}%</span>
          </el-form-item>

          <el-form-item label="单次下单">
            <el-input-number v-model="form.orderAmount" :min="10" :max="10000" :step="10" />
            <span style="margin-left: 10px">USDT</span>
          </el-form-item>
        </template>

        <el-alert
          title="说明"
          type="info"
          :closable="false"
          show-icon
        >
          <p>• 使用真实账户 API 获取实时行情数据</p>
          <p>• 所有交易均为模拟，不会实际下单</p>
          <p>• 可用于测试策略参数和风险控制</p>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="showConfigDialog = false">取消</el-button>
        <el-button type="primary" @click="handleStart" :loading="loading">
          启动
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoPlay,
  VideoPause,
  TrendCharts
} from '@element-plus/icons-vue'
import papertradingApi from '@/api/papertrading'

const showConfigDialog = ref(false)
const loading = ref(false)
const isRunning = ref(false)
const formRef = ref(null)

const form = ref({
  exchange: 'okx',
  apiKey: '',
  secretKey: '',
  passphrase: '',
  initialBalance: 100000,
  strategy: 'grid',
  symbol: 'BTC-USDT-SWAP',
  gridNum: 10,
  gridSpread: 0.002,
  orderAmount: 100
})

const rules = {
  exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
  apiKey: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
  secretKey: [{ required: true, message: '请输入 Secret Key', trigger: 'blur' }],
  strategy: [{ required: true, message: '请选择策略', trigger: 'change' }],
  symbol: [{ required: true, message: '请选择交易对', trigger: 'change' }]
}

const currentConfig = ref({})
const startTime = ref(null)
const runTime = ref('00:00:00')
const equity = ref(100000)
const totalPnl = ref(0)
const tradeCount = ref(0)
const positionCount = ref(0)

const returnRate = computed(() => {
  if (!currentConfig.value.initialBalance) return 0
  return ((equity.value - currentConfig.value.initialBalance) / currentConfig.value.initialBalance) * 100
})

let timer = null

async function handleStart() {
  try {
    await formRef.value.validate()

    loading.value = true

    // 调用后端 API 启动 PaperTrading 策略
    const result = await papertradingApi.startStrategy(form.value)

    if (!result.success) {
      throw new Error(result.message || '启动失败')
    }

    currentConfig.value = { ...form.value }
    isRunning.value = true
    startTime.value = Date.now()
    showConfigDialog.value = false

    // 启动计时器
    timer = setInterval(updateRunTime, 1000)

    ElMessage.success('模拟交易已启动')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('启动失败: ' + error.message)
    }
  } finally {
    loading.value = false
  }
}

async function handleStop() {
  try {
    await ElMessageBox.confirm(
      '确定要停止模拟交易吗？',
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 调用后端 API 停止 PaperTrading
    const result = await papertradingApi.stopStrategy()

    if (!result.success) {
      throw new Error(result.message || '停止失败')
    }

    isRunning.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }

    ElMessage.success('模拟交易已停止')
  } catch (error) {
    // 用户取消
  }
}

function updateRunTime() {
  if (!startTime.value) return

  const elapsed = Date.now() - startTime.value
  const hours = Math.floor(elapsed / 3600000)
  const minutes = Math.floor((elapsed % 3600000) / 60000)
  const seconds = Math.floor((elapsed % 60000) / 1000)

  runTime.value = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

// 检查策略状态
async function checkStatus() {
  try {
    const result = await papertradingApi.getStrategyStatus()
    if (result.success && result.data) {
      isRunning.value = result.data.isRunning
      if (result.data.isRunning) {
        currentConfig.value = result.data.config || {}
        startTime.value = result.data.startTime || Date.now()
        if (!timer) {
          timer = setInterval(updateRunTime, 1000)
        }
      }
    }
  } catch (error) {
    console.error('检查状态失败:', error)
  }
}

onMounted(() => {
  checkStatus()
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
  }
})
</script>

<style scoped lang="scss">
.paper-trading-page {
  padding: 20px;

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;

    h2 {
      margin: 0 0 5px 0;
      font-size: 24px;
    }

    p {
      margin: 0;
      color: var(--text-secondary);
    }
  }

  .status-card {
    margin-bottom: 20px;

    .status-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;

      .run-time {
        font-size: 18px;
        font-weight: bold;
        color: var(--text-primary);
      }
    }
  }

  .stats-row {
    margin-bottom: 20px;
  }

  .text-success {
    color: #67c23a;
  }

  .text-danger {
    color: #f56c6c;
  }
}
</style>
