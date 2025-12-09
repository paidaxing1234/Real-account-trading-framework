<template>
  <el-dialog
    v-model="visible"
    title="添加OKX账户"
    width="500px"
    :close-on-click-modal="false"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
    >
      <el-form-item label="账户名称" prop="name">
        <el-input v-model="form.name" placeholder="自定义账户名称" />
      </el-form-item>
      
      <el-form-item label="API Key" prop="apiKey">
        <el-input v-model="form.apiKey" placeholder="输入API Key" show-password />
      </el-form-item>
      
      <el-form-item label="Secret Key" prop="secretKey">
        <el-input v-model="form.secretKey" placeholder="输入Secret Key" show-password />
      </el-form-item>
      
      <el-form-item label="Passphrase" prop="passphrase">
        <el-input v-model="form.passphrase" placeholder="输入Passphrase" show-password />
      </el-form-item>
      
      <el-form-item label="账户类型" prop="accountType">
        <el-select v-model="form.accountType" style="width: 100%">
          <el-option label="统一账户" value="unified" />
          <el-option label="单币种保证金" value="single" />
          <el-option label="多币种保证金" value="multi" />
        </el-select>
      </el-form-item>
      
      <el-form-item label="模拟盘">
        <el-switch v-model="form.isDemo" />
        <span style="margin-left: 10px; color: var(--text-secondary);">
          开启后使用模拟盘环境
        </span>
      </el-form-item>
      
      <el-alert
        title="安全提示"
        type="warning"
        :closable="false"
        style="margin-bottom: 20px;"
      >
        请确保API Key仅具有必要的权限，建议开启IP白名单。密钥将加密存储。
      </el-alert>
    </el-form>
    
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="loading">
        添加
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'

const props = defineProps({
  modelValue: Boolean
})

const emit = defineEmits(['update:modelValue', 'success'])

const accountStore = useAccountStore()

const formRef = ref(null)
const loading = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const form = reactive({
  name: '',
  apiKey: '',
  secretKey: '',
  passphrase: '',
  accountType: 'unified',
  isDemo: false
})

const rules = {
  name: [
    { required: true, message: '请输入账户名称', trigger: 'blur' }
  ],
  apiKey: [
    { required: true, message: '请输入API Key', trigger: 'blur' }
  ],
  secretKey: [
    { required: true, message: '请输入Secret Key', trigger: 'blur' }
  ],
  passphrase: [
    { required: true, message: '请输入Passphrase', trigger: 'blur' }
  ]
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
    
    loading.value = true
    await accountStore.addAccount(form)
    
    ElMessage.success('账户添加成功')
    emit('success')
    handleClose()
  } catch (error) {
    if (error !== false) {
      ElMessage.error('添加失败: ' + error.message)
    }
  } finally {
    loading.value = false
  }
}

function handleClose() {
  visible.value = false
  formRef.value?.resetFields()
}
</script>

