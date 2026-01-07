<template>
  <div class="paper-trading-page">
    <div class="page-header">
      <div>
        <h2>模拟交易 (Paper Trading)</h2>
        <p>使用真实行情数据进行模拟交易测试</p>
      </div>
      <div class="header-buttons">
        <el-button
          v-if="runningStrategies.length > 0"
          type="danger"
          plain
          @click="handleClearAllStrategies"
        >
          清除所有策略
        </el-button>
        <el-button
          type="primary"
          :icon="Plus"
          @click="showConfigDialog = true"
        >
          添加策略
        </el-button>
      </div>
    </div>

    <!-- 实时行情卡片 -->
    <el-card class="market-card">
      <template #header>
        <div class="card-header">
          <span>实时行情</span>
          <el-tag v-if="marketConnected" type="success" size="small">已连接</el-tag>
          <el-tag v-else type="danger" size="small">未连接</el-tag>
        </div>
      </template>

      <!-- OKX 行情 -->
      <div class="exchange-row">
        <div class="exchange-label">OKX</div>
        <div class="price-row">
          <div v-for="coin in displayCoins" :key="'okx-' + coin" class="price-item">
            <div class="symbol">{{ coin }}-USDT</div>
            <div class="price" :class="priceDirection[coin + '-USDT']">
              {{ formatPrice(marketPrices[coin + '-USDT']) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Binance 行情 -->
      <div class="exchange-row">
        <div class="exchange-label">Binance</div>
        <div class="price-row">
          <div v-for="coin in displayCoins" :key="'binance-' + coin" class="price-item">
            <div class="symbol">{{ coin }}USDT</div>
            <div class="price" :class="priceDirection[coin + 'USDT']">
              {{ formatPrice(marketPrices[coin + 'USDT']) }}
            </div>
          </div>
        </div>
      </div>

      <div v-if="Object.keys(marketPrices).length === 0" class="no-data">
        等待行情数据...
      </div>
    </el-card>

    <!-- 策略列表 -->
    <el-card class="strategies-card">
      <template #header>
        <div class="card-header">
          <span>运行中的策略</span>
          <el-tag type="info" size="small">{{ runningStrategies.length }} 个</el-tag>
        </div>
      </template>

      <el-table :data="runningStrategies" v-if="runningStrategies.length > 0">
        <el-table-column prop="strategyId" label="策略ID" width="150" />
        <el-table-column prop="strategy" label="策略类型" width="100">
          <template #default="{ row }">
            {{ strategyLabels[row.strategy] || row.strategy }}
          </template>
        </el-table-column>
        <el-table-column prop="symbol" label="交易对" width="150" />
        <el-table-column prop="exchange" label="交易所" width="100" />
        <el-table-column label="初始资金" width="120">
          <template #default="{ row }">
            {{ row.initialBalance }} USDT
          </template>
        </el-table-column>
        <el-table-column label="当前权益" width="120">
          <template #default="{ row }">
            {{ (row.equity || row.initialBalance).toFixed(2) }} USDT
          </template>
        </el-table-column>
        <el-table-column label="收益率" width="100">
          <template #default="{ row }">
            <span :class="getReturnRate(row) >= 0 ? 'text-success' : 'text-danger'">
              {{ getReturnRate(row).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="运行时长" width="100">
          <template #default="{ row }">
            {{ formatRunTime(row.startTime) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="toggleStrategyDetail(row)">
              {{ expandedStrategyId === row.strategyId ? '收起' : '详情' }}
            </el-button>
            <el-button type="danger" size="small" @click="handleStopStrategy(row)">
              停止
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 策略详情展开区域 -->
      <div v-if="expandedStrategy" class="strategy-detail-inline">
        <el-divider content-position="left">策略详情 - {{ expandedStrategy.strategyId }}</el-divider>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="策略ID">{{ expandedStrategy.strategyId }}</el-descriptions-item>
              <el-descriptions-item label="策略类型">{{ strategyLabels[expandedStrategy.strategy] || expandedStrategy.strategy }}</el-descriptions-item>
              <el-descriptions-item label="交易对">{{ expandedStrategy.symbol }}</el-descriptions-item>
              <el-descriptions-item label="交易所">{{ expandedStrategy.exchange }}</el-descriptions-item>
              <el-descriptions-item label="初始资金">{{ expandedStrategy.initialBalance }} USDT</el-descriptions-item>
              <el-descriptions-item label="当前权益">{{ (expandedStrategy.equity || expandedStrategy.initialBalance).toFixed(2) }} USDT</el-descriptions-item>
            </el-descriptions>
          </el-col>
          <el-col :span="12">
            <el-descriptions :column="2" border size="small" title="网格参数">
              <el-descriptions-item label="网格数量">{{ expandedStrategy.gridNum }}</el-descriptions-item>
              <el-descriptions-item label="网格间距">{{ (expandedStrategy.gridSpread * 100).toFixed(2) }}%</el-descriptions-item>
              <el-descriptions-item label="单次下单">{{ expandedStrategy.orderAmount }} USDT</el-descriptions-item>
              <el-descriptions-item label="收益率">
                <span :class="getReturnRate(expandedStrategy) >= 0 ? 'text-success' : 'text-danger'">
                  {{ getReturnRate(expandedStrategy).toFixed(2) }}%
                </span>
              </el-descriptions-item>
            </el-descriptions>
          </el-col>
        </el-row>

        <el-divider content-position="left">交易记录</el-divider>
        <el-table :data="expandedStrategy.trades || []" max-height="300" size="small">
          <el-table-column prop="time" label="时间" width="180">
            <template #default="{ row }">
              {{ formatTradeTime(row.time) }}
            </template>
          </el-table-column>
          <el-table-column prop="side" label="方向" width="80">
            <template #default="{ row }">
              <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                {{ row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="120" />
          <el-table-column prop="quantity" label="数量" width="120" />
          <el-table-column prop="amount" label="金额" width="120">
            <template #default="{ row }">
              {{ (row.price * row.quantity).toFixed(2) }} USDT
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'filled' ? 'success' : 'info'" size="small">
                {{ row.status === 'filled' ? '已成交' : row.status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!expandedStrategy.trades || expandedStrategy.trades.length === 0" class="no-data">
          暂无交易记录
        </div>
      </div>

      <div v-else-if="runningStrategies.length === 0" class="no-data">
        暂无运行中的策略，点击"添加策略"开始
      </div>
    </el-card>

    <!-- 账户统计 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card>
          <el-statistic title="总权益" :value="totalEquity" suffix="USDT" />
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
      title="添加模拟策略"
      width="550px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="交易所" prop="exchange">
          <el-select v-model="form.exchange" style="width: 100%">
            <el-option label="OKX" value="okx" />
            <el-option label="Binance" value="binance" />
          </el-select>
        </el-form-item>

        <el-form-item label="交易对" prop="symbol">
          <el-select v-model="form.symbol" style="width: 100%" filterable>
            <el-option label="BTC-USDT-SWAP" value="BTC-USDT-SWAP" />
            <el-option label="ETH-USDT-SWAP" value="ETH-USDT-SWAP" />
            <el-option label="SOL-USDT-SWAP" value="SOL-USDT-SWAP" />
            <el-option label="DOGE-USDT-SWAP" value="DOGE-USDT-SWAP" />
            <el-option label="XRP-USDT-SWAP" value="XRP-USDT-SWAP" />
          </el-select>
        </el-form-item>

        <el-form-item label="初始资金">
          <el-input-number v-model="form.initialBalance" :min="1000" :max="1000000" :step="1000" />
          <span style="margin-left: 10px">USDT</span>
        </el-form-item>

        <el-divider content-position="left">策略配置</el-divider>

        <el-form-item label="策略类型" prop="strategy">
          <el-select v-model="form.strategy" style="width: 100%">
            <el-option label="网格策略" value="grid" />
            <el-option label="趋势策略" value="trend" disabled />
            <el-option label="做市策略" value="market_making" disabled />
          </el-select>
        </el-form-item>

        <!-- 网格策略参数 -->
        <template v-if="form.strategy === 'grid'">
          <el-form-item label="网格数量">
            <el-input-number v-model="form.gridNum" :min="5" :max="50" />
          </el-form-item>

          <el-form-item label="网格间距">
            <el-input-number v-model="form.gridSpread" :min="0.0005" :max="0.05" :step="0.0005" :precision="4" />
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
          <p>• 复用主服务器的实时行情数据</p>
          <p>• 所有交易均为模拟，不会实际下单</p>
          <p>• 可同时运行多个策略进行对比测试</p>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="showConfigDialog = false">取消</el-button>
        <el-button type="primary" @click="handleStart" :loading="loading">
          启动
        </el-button>
      </template>
    </el-dialog>

    <!-- 策略详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      :title="'策略详情 - ' + (selectedStrategy?.strategyId || '')"
      width="700px"
    >
      <div v-if="selectedStrategy" class="strategy-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="策略ID">{{ selectedStrategy.strategyId }}</el-descriptions-item>
          <el-descriptions-item label="策略类型">{{ strategyLabels[selectedStrategy.strategy] || selectedStrategy.strategy }}</el-descriptions-item>
          <el-descriptions-item label="交易对">{{ selectedStrategy.symbol }}</el-descriptions-item>
          <el-descriptions-item label="交易所">{{ selectedStrategy.exchange }}</el-descriptions-item>
          <el-descriptions-item label="初始资金">{{ selectedStrategy.initialBalance }} USDT</el-descriptions-item>
          <el-descriptions-item label="当前权益">{{ (selectedStrategy.equity || selectedStrategy.initialBalance).toFixed(2) }} USDT</el-descriptions-item>
          <el-descriptions-item label="收益率">
            <span :class="getReturnRate(selectedStrategy) >= 0 ? 'text-success' : 'text-danger'">
              {{ getReturnRate(selectedStrategy).toFixed(2) }}%
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="运行时长">{{ formatRunTime(selectedStrategy.startTime) }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">网格参数</el-divider>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="网格数量">{{ selectedStrategy.gridNum }}</el-descriptions-item>
          <el-descriptions-item label="网格间距">{{ (selectedStrategy.gridSpread * 100).toFixed(2) }}%</el-descriptions-item>
          <el-descriptions-item label="单次下单">{{ selectedStrategy.orderAmount }} USDT</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">交易统计</el-divider>
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic title="买入次数" :value="selectedStrategy.buyCount || 0" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="卖出次数" :value="selectedStrategy.sellCount || 0" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="总成交" :value="(selectedStrategy.buyCount || 0) + (selectedStrategy.sellCount || 0)" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="盈亏" :value="((selectedStrategy.equity || selectedStrategy.initialBalance) - selectedStrategy.initialBalance).toFixed(2)" suffix="USDT" />
          </el-col>
        </el-row>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  TrendCharts,
  Plus
} from '@element-plus/icons-vue'
import papertradingApi from '@/api/papertrading'
import { wsClient } from '@/services/WebSocketClient'

const showConfigDialog = ref(false)
const showDetailDialog = ref(false)
const selectedStrategy = ref(null)
const expandedStrategyId = ref(null)
const loading = ref(false)
const formRef = ref(null)

// 展开的策略详情
const expandedStrategy = computed(() => {
  if (!expandedStrategyId.value) return null
  return runningStrategies.value.find(s => s.strategyId === expandedStrategyId.value)
})

// 策略列表
const runningStrategies = ref([])

// 策略类型标签
const strategyLabels = {
  grid: '网格策略',
  trend: '趋势策略',
  market_making: '做市策略'
}

// 实时行情数据
const marketPrices = reactive({})
const priceDirection = reactive({})
const marketConnected = ref(false)

// 展示的币种
const displayCoins = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']

// 格式化价格
function formatPrice(price) {
  if (!price) return '--'
  if (price >= 1000) return price.toFixed(2)
  if (price >= 1) return price.toFixed(4)
  return price.toFixed(6)
}

const form = ref({
  exchange: 'okx',
  initialBalance: 100000,
  strategy: 'grid',
  symbol: 'BTC-USDT-SWAP',
  gridNum: 10,
  gridSpread: 0.002,
  orderAmount: 100
})

const rules = {
  exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
  strategy: [{ required: true, message: '请选择策略', trigger: 'change' }],
  symbol: [{ required: true, message: '请选择交易对', trigger: 'change' }]
}

// 统计数据
const totalEquity = computed(() => {
  return runningStrategies.value.reduce((sum, s) => sum + (s.equity || s.initialBalance), 0)
})

const totalPnl = computed(() => {
  return runningStrategies.value.reduce((sum, s) => {
    return sum + ((s.equity || s.initialBalance) - s.initialBalance)
  }, 0)
})

const tradeCount = ref(0)
const positionCount = ref(0)

async function handleClearAllStrategies() {
  try {
    await ElMessageBox.confirm(
      '确定要清除所有策略吗？这将停止所有运行中的策略并清除历史记录。',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 停止所有策略（忽略不存在的策略错误）
    for (const strategy of runningStrategies.value) {
      try {
        await papertradingApi.stopStrategy(strategy.strategyId)
      } catch (e) {
        // 忽略"策略不存在"错误，因为后端可能已重启
        console.log('策略可能已不存在:', strategy.strategyId)
      }
    }

    // 清除列表和 localStorage
    runningStrategies.value = []
    tradeCount.value = 0
    expandedStrategyId.value = null
    localStorage.removeItem('paperTradingStrategies')

    ElMessage.success('所有策略已清除')
  } catch (error) {
    // 用户取消
  }
}

function getReturnRate(strategy) {
  const equity = strategy.equity || strategy.initialBalance
  return ((equity - strategy.initialBalance) / strategy.initialBalance) * 100
}

function formatRunTime(startTime) {
  if (!startTime) return '00:00:00'
  const elapsed = Date.now() - startTime
  const hours = Math.floor(elapsed / 3600000)
  const minutes = Math.floor((elapsed % 3600000) / 60000)
  const seconds = Math.floor((elapsed % 60000) / 1000)
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function formatTradeTime(timestamp) {
  if (!timestamp) return '--'
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN')
}

function toggleStrategyDetail(strategy) {
  if (expandedStrategyId.value === strategy.strategyId) {
    expandedStrategyId.value = null
  } else {
    expandedStrategyId.value = strategy.strategyId
  }
}

let timer = null

async function handleStart() {
  try {
    await formRef.value.validate()

    loading.value = true

    // 生成策略ID
    const strategyId = `paper_${form.value.strategy}_${Date.now()}`

    // 调用后端 API 启动策略
    const result = await papertradingApi.startStrategy({
      ...form.value,
      strategyId
    })

    if (!result.success) {
      throw new Error(result.message || '启动失败')
    }

    // 添加到策略列表
    runningStrategies.value.push({
      strategyId,
      ...form.value,
      startTime: Date.now(),
      equity: form.value.initialBalance
    })

    showConfigDialog.value = false
    ElMessage.success('策略已启动')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('启动失败: ' + error.message)
    }
  } finally {
    loading.value = false
  }
}

async function handleStopStrategy(strategy) {
  try {
    await ElMessageBox.confirm(
      `确定要停止策略 ${strategy.strategyId} 吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 调用后端 API 停止策略
    try {
      const result = await papertradingApi.stopStrategy(strategy.strategyId)
      if (!result.success && !result.message?.includes('不存在')) {
        throw new Error(result.message || '停止失败')
      }
    } catch (e) {
      // 如果是"策略不存在"错误，仍然从前端列表移除
      if (!e.message?.includes('不存在')) {
        throw e
      }
      console.log('策略在后端已不存在，从前端列表移除')
    }

    // 从列表中移除
    const index = runningStrategies.value.findIndex(s => s.strategyId === strategy.strategyId)
    if (index !== -1) {
      runningStrategies.value.splice(index, 1)
    }

    // 更新 localStorage
    localStorage.setItem('paperTradingStrategies', JSON.stringify(runningStrategies.value))

    ElMessage.success('策略已停止')
  } catch (error) {
    if (error !== 'cancel' && error.message !== 'cancel') {
      ElMessage.error('停止失败: ' + error.message)
    }
  }
}

// 检查策略状态，同步后端实际运行的策略
async function checkStatus() {
  try {
    const result = await papertradingApi.getStrategyStatus()
    if (result.success && result.data) {
      let backendStrategies = []

      if (result.data.strategies) {
        backendStrategies = result.data.strategies
      } else if (result.data.isRunning && result.data.config) {
        // 兼容旧格式
        backendStrategies = [{
          strategyId: result.data.config.strategyId || 'paper_grid_default',
          ...result.data.config,
          startTime: result.data.startTime || Date.now()
        }]
      }

      // 获取后端实际运行的策略ID列表
      const backendStrategyIds = new Set(backendStrategies.map(s => s.strategyId))

      // 过滤掉前端有但后端没有的策略（后端可能已重启）
      const validStrategies = runningStrategies.value.filter(s =>
        backendStrategyIds.has(s.strategyId)
      )

      // 合并后端的策略数据（更新权益等信息）
      for (const backendStrategy of backendStrategies) {
        const existingIndex = validStrategies.findIndex(s => s.strategyId === backendStrategy.strategyId)
        if (existingIndex !== -1) {
          // 更新现有策略的数据
          validStrategies[existingIndex] = { ...validStrategies[existingIndex], ...backendStrategy }
        } else {
          // 添加后端有但前端没有的策略
          validStrategies.push(backendStrategy)
        }
      }

      runningStrategies.value = validStrategies

      // 更新 localStorage
      localStorage.setItem('paperTradingStrategies', JSON.stringify(validStrategies))
    } else {
      // 后端没有运行中的策略，清空前端列表
      if (runningStrategies.value.length > 0) {
        console.log('后端无运行策略，清空前端列表')
        runningStrategies.value = []
        localStorage.removeItem('paperTradingStrategies')
      }
    }
  } catch (error) {
    console.error('检查状态失败:', error)
  }
}

// 处理订单回报
function handleOrderReport(event) {
  const { data } = event
  if (!data) return

  // 检查是否是模拟交易的订单（策略ID以 paper_ 开头）
  const strategyId = data.strategy_id || data.strategyId
  if (!strategyId || !strategyId.startsWith('paper_')) return

  // 找到对应的策略
  const strategy = runningStrategies.value.find(s => s.strategyId === strategyId)
  if (!strategy) return

  // 初始化 trades 数组
  if (!strategy.trades) {
    strategy.trades = []
  }

  // 添加交易记录
  const trade = {
    time: data.timestamp || Date.now(),
    side: data.side?.toLowerCase() || 'buy',
    price: parseFloat(data.filled_price) || parseFloat(data.price) || 0,
    quantity: parseFloat(data.filled_quantity) || parseFloat(data.quantity) || parseFloat(data.filled_qty) || 0,
    status: data.status || 'filled',
    orderId: data.client_order_id || data.orderId
  }

  // 避免重复添加
  const exists = strategy.trades.some(t => t.orderId === trade.orderId)
  if (!exists) {
    strategy.trades.unshift(trade)  // 新的在前面
    tradeCount.value++

    // 更新权益（简单模拟）
    const amount = trade.price * trade.quantity
    if (trade.side === 'buy') {
      strategy.equity = (strategy.equity || strategy.initialBalance) - amount * 0.0001  // 手续费
    } else {
      strategy.equity = (strategy.equity || strategy.initialBalance) + amount * 0.0001
    }

    // 保存到 localStorage
    localStorage.setItem('paperTradingStrategies', JSON.stringify(runningStrategies.value))
  }
}

// 处理行情数据
function handleTrade(event) {
  const { data } = event
  if (data && data.symbol && data.price) {
    const oldPrice = marketPrices[data.symbol]
    const newPrice = parseFloat(data.price)

    if (oldPrice !== undefined) {
      if (newPrice > oldPrice) {
        priceDirection[data.symbol] = 'up'
      } else if (newPrice < oldPrice) {
        priceDirection[data.symbol] = 'down'
      }
    }

    marketPrices[data.symbol] = newPrice
    marketConnected.value = true
  }
}

function handleSnapshot(event) {
  const { data } = event
  if (data && data.trades) {
    for (const trade of data.trades) {
      if (trade.symbol && trade.price) {
        const newPrice = parseFloat(trade.price)
        const oldPrice = marketPrices[trade.symbol]

        if (oldPrice !== undefined) {
          if (newPrice > oldPrice) {
            priceDirection[trade.symbol] = 'up'
          } else if (newPrice < oldPrice) {
            priceDirection[trade.symbol] = 'down'
          }
        }

        marketPrices[trade.symbol] = newPrice
      }
    }
    marketConnected.value = true
  }
}

function handleConnected() {
  marketConnected.value = true
}

function handleDisconnected() {
  marketConnected.value = false
}

// 更新运行时间
function updateRunTimes() {
  // 触发响应式更新
  runningStrategies.value = [...runningStrategies.value]
}

onMounted(() => {
  // 从 localStorage 恢复策略列表
  const saved = localStorage.getItem('paperTradingStrategies')
  if (saved) {
    try {
      runningStrategies.value = JSON.parse(saved)
    } catch (e) {
      console.error('恢复策略列表失败:', e)
    }
  }

  checkStatus()

  // 监听行情数据
  wsClient.on('trade', handleTrade)
  wsClient.on('ticker', handleTrade)
  wsClient.on('snapshot', handleSnapshot)
  wsClient.on('connected', handleConnected)
  wsClient.on('disconnected', handleDisconnected)

  // 监听订单回报
  wsClient.on('order_filled', handleOrderReport)
  wsClient.on('order_report', handleOrderReport)

  marketConnected.value = wsClient.connected

  // 定时更新运行时间
  timer = setInterval(updateRunTimes, 1000)
})

onUnmounted(() => {
  // 保存策略列表到 localStorage
  localStorage.setItem('paperTradingStrategies', JSON.stringify(runningStrategies.value))

  if (timer) {
    clearInterval(timer)
  }

  wsClient.off('trade', handleTrade)
  wsClient.off('ticker', handleTrade)
  wsClient.off('snapshot', handleSnapshot)
  wsClient.off('connected', handleConnected)
  wsClient.off('disconnected', handleDisconnected)
  wsClient.off('order_filled', handleOrderReport)
  wsClient.off('order_report', handleOrderReport)
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

    .header-buttons {
      display: flex;
      gap: 10px;
    }
  }

  .market-card, .strategies-card {
    margin-bottom: 20px;

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .exchange-row {
      display: flex;
      align-items: center;
      margin-bottom: 15px;

      &:last-of-type {
        margin-bottom: 0;
      }

      .exchange-label {
        width: 80px;
        font-weight: bold;
        color: var(--text-primary);
        flex-shrink: 0;
      }

      .price-row {
        display: flex;
        flex: 1;
        gap: 15px;
      }
    }

    .price-item {
      flex: 1;
      text-align: center;
      padding: 10px;
      background: var(--bg-secondary, #f5f5f5);
      border-radius: 8px;

      .symbol {
        font-size: 12px;
        color: var(--text-secondary, #666);
        margin-bottom: 5px;
      }

      .price {
        font-size: 18px;
        font-weight: bold;
        transition: color 0.3s;

        &.up {
          color: #67c23a;
        }

        &.down {
          color: #f56c6c;
        }
      }
    }

    .no-data {
      text-align: center;
      color: var(--text-secondary, #999);
      padding: 20px;
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

  .strategy-detail-inline {
    margin-top: 20px;
    padding: 15px;
    background: var(--bg-secondary, #fafafa);
    border-radius: 8px;

    .el-descriptions {
      margin-bottom: 15px;
    }

    .no-data {
      text-align: center;
      color: var(--text-secondary, #999);
      padding: 20px;
    }
  }
}

.strategy-detail {
  .el-descriptions {
    margin-bottom: 15px;
  }

  .el-row {
    text-align: center;
  }
}
</style>
