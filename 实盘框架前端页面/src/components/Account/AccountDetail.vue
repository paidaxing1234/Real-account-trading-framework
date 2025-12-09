<template>
  <div class="account-detail">
    <el-descriptions :column="2" border>
      <el-descriptions-item label="账户ID">
        {{ account.id }}
      </el-descriptions-item>
      
      <el-descriptions-item label="账户名称">
        {{ account.name }}
      </el-descriptions-item>
      
      <el-descriptions-item label="交易所">
        OKX
      </el-descriptions-item>
      
      <el-descriptions-item label="账户类型">
        {{ account.accountType || '现货' }}
      </el-descriptions-item>
      
      <el-descriptions-item label="总余额">
        {{ formatNumber(account.balance, 2) }} USDT
      </el-descriptions-item>
      
      <el-descriptions-item label="可用余额">
        {{ formatNumber(account.availableBalance, 2) }} USDT
      </el-descriptions-item>
      
      <el-descriptions-item label="冻结余额">
        {{ formatNumber(account.frozenBalance, 2) }} USDT
      </el-descriptions-item>
      
      <el-descriptions-item label="总净值">
        {{ formatNumber(account.equity, 2) }} USDT
      </el-descriptions-item>
      
      <el-descriptions-item label="未实现盈亏">
        <span :class="account.unrealizedPnl >= 0 ? 'text-success' : 'text-danger'">
          {{ formatNumber(account.unrealizedPnl, 2) }} USDT
        </span>
      </el-descriptions-item>
      
      <el-descriptions-item label="已实现盈亏">
        <span :class="account.realizedPnl >= 0 ? 'text-success' : 'text-danger'">
          {{ formatNumber(account.realizedPnl, 2) }} USDT
        </span>
      </el-descriptions-item>
      
      <el-descriptions-item label="收益率">
        <span :class="account.returnRate >= 0 ? 'text-success' : 'text-danger'">
          {{ formatPercent(account.returnRate / 100) }}
        </span>
      </el-descriptions-item>
      
      <el-descriptions-item label="最后同步">
        {{ formatTime(account.lastSyncTime) }}
      </el-descriptions-item>
      
      <el-descriptions-item label="创建时间" :span="2">
        {{ formatTime(account.createdAt) }}
      </el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup>
import { formatNumber, formatPercent, formatTime } from '@/utils/format'

defineProps({
  account: {
    type: Object,
    required: true
  }
})
</script>

<style lang="scss" scoped>
.account-detail {
  padding: 20px;
}
</style>

