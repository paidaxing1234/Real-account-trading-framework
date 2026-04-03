<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <el-icon :size="50" color="#409eff"><TrendCharts /></el-icon>
        <h2>实盘交易管理系统</h2>
        <p>Trading Management System</p>
      </div>
      
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>
        
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            clearable
          />
        </el-form-item>
        
        <el-form-item>
          <el-checkbox v-model="form.remember">记住密码</el-checkbox>
        </el-form-item>
        
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <p>&copy; 2024 实盘交易管理系统. All rights reserved.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { TrendCharts, User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  remember: false
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ]
}

async function handleLogin() {
  try {
    await formRef.value.validate()
    
    loading.value = true
    await userStore.login({
      username: form.username,
      password: form.password
    })
    
    // 登录成功，跳转到首页
    router.push('/')
  } catch (error) {
    console.error('登录失败:', error)
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-base);
  padding: 20px;
  position: relative;
  overflow: hidden;

  .login-box {
    width: 100%;
    max-width: 440px;
    background: var(--bg-card);
    border-radius: 16px;
    padding: 48px 40px;
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-md);
    position: relative;
    z-index: 1;
    animation: fadeInUp 0.6s ease-out;

    .login-header {
      text-align: center;
      margin-bottom: 40px;

      .el-icon {
        margin-bottom: 16px;
        color: var(--accent-green) !important;
      }

      h2 {
        margin: 0 0 8px 0;
        font-size: 24px;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.5px;
      }

      p {
        margin: 0;
        color: var(--text-secondary);
        font-size: 13px;
        font-family: var(--font-mono);
        letter-spacing: 1.5px;
        text-transform: uppercase;
      }
    }

    :deep(.el-button--primary) {
      font-size: 15px;
      height: 44px;
      letter-spacing: 2px;
    }

    :deep(.el-checkbox__label) {
      color: var(--text-secondary) !important;
      font-size: 13px;
    }

    .login-footer {
      text-align: center;
      margin-top: 28px;

      p {
        margin: 0;
        color: var(--text-muted);
        font-size: 11px;
        font-family: var(--font-mono);
      }
    }
  }
}

/* 暗色模式增强 */
:global(html.dark) .login-container {
  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(0, 212, 170, 0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0, 212, 170, 0.03) 1px, transparent 1px);
    background-size: 60px 60px;
    mask-image: radial-gradient(ellipse at center, black 30%, transparent 70%);
  }
  &::after {
    content: '';
    position: absolute;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(0, 212, 170, 0.08) 0%, transparent 70%);
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
  }
}

@media (max-width: 768px) {
  .login-container {
    .login-box { padding: 32px 20px; }
  }
}
</style>

