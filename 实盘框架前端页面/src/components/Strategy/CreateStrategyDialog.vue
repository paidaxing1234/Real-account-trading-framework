<template>
  <el-dialog
    v-model="visible"
    title="创建策略"
    width="600px"
    :close-on-click-modal="false"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
    >
      <el-form-item label="策略名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入策略名称" />
      </el-form-item>
      
      <el-form-item label="策略类型" prop="type">
        <el-select v-model="form.type" placeholder="选择策略类型" style="width: 100%">
          <el-option label="网格交易" value="grid" />
          <el-option label="趋势跟踪" value="trend" />
          <el-option label="套利策略" value="arbitrage" />
          <el-option label="做市策略" value="market_making" />
          <el-option label="自定义" value="custom" />
        </el-select>
      </el-form-item>
      
      <el-form-item label="选择账户" prop="accountId">
        <el-select v-model="form.accountId" placeholder="选择交易账户" style="width: 100%">
          <el-option
            v-for="account in accounts"
            :key="account.id"
            :label="account.name"
            :value="account.id"
          />
        </el-select>
      </el-form-item>
      
      <el-form-item label="交易对" prop="symbol">
        <el-input v-model="form.symbol" placeholder="例如: BTC-USDT-SWAP" />
      </el-form-item>
      
      <el-form-item label="Python文件" prop="pythonFile">
        <el-input v-model="form.pythonFile" placeholder="策略Python文件路径">
          <template #append>
            <el-button :icon="FolderOpened" @click="handleSelectFile">
              选择文件
            </el-button>
          </template>
        </el-input>
      </el-form-item>
      
      <el-form-item label="策略参数">
        <el-input
          v-model="form.parameters"
          type="textarea"
          :rows="4"
          placeholder='JSON格式参数, 例如: {"grid_size": 10, "interval": 100}'
        />
      </el-form-item>
      
      <el-form-item label="描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="策略描述（可选）"
        />
      </el-form-item>
      
      <el-form-item label="自动启动">
        <el-switch v-model="form.autoStart" />
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="loading">
        创建
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useStrategyStore } from '@/stores/strategy'
import { FolderOpened } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: Boolean
})

const emit = defineEmits(['update:modelValue', 'success'])

const accountStore = useAccountStore()
const strategyStore = useStrategyStore()

const formRef = ref(null)
const loading = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const accounts = computed(() => accountStore.accounts)

const form = reactive({
  name: '',
  type: '',
  accountId: '',
  symbol: '',
  pythonFile: '',
  parameters: '',
  description: '',
  autoStart: false
})

const rules = {
  name: [
    { required: true, message: '请输入策略名称', trigger: 'blur' }
  ],
  type: [
    { required: true, message: '请选择策略类型', trigger: 'change' }
  ],
  accountId: [
    { required: true, message: '请选择交易账户', trigger: 'change' }
  ],
  symbol: [
    { required: true, message: '请输入交易对', trigger: 'blur' }
  ],
  pythonFile: [
    { required: true, message: '请选择Python文件', trigger: 'blur' }
  ]
}

function handleSelectFile() {
  ElMessage.info('请在后端配置Python文件路径')
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
    
    loading.value = true
    
    // 验证参数格式
    if (form.parameters) {
      try {
        JSON.parse(form.parameters)
      } catch (e) {
        ElMessage.error('参数格式错误，请输入有效的JSON')
        loading.value = false
        return
      }
    }
    
    await strategyStore.createStrategy({
      ...form,
      parameters: form.parameters ? JSON.parse(form.parameters) : {}
    })
    
    ElMessage.success('策略创建成功')
    emit('success')
    handleClose()
  } catch (error) {
    if (error !== false) {
      ElMessage.error('创建失败: ' + error.message)
    }
  } finally {
    loading.value = false
  }
}

function handleClose() {
  visible.value = false
  formRef.value?.resetFields()
}

watch(visible, (val) => {
  if (val) {
    accountStore.fetchAccounts()
  }
})
</script>

