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
      
      <el-divider>测试账号</el-divider>
      
      <div class="test-accounts">
        <el-card shadow="hover" @click="quickLogin('admin')">
          <div class="account-info">
            <el-icon color="#409eff" :size="24"><UserFilled /></el-icon>
            <div>
              <div class="account-name">超级管理员</div>
              <div class="account-desc">admin / admin123</div>
            </div>
          </div>
        </el-card>
        
        <el-card shadow="hover" @click="quickLogin('viewer')">
          <div class="account-info">
            <el-icon color="#67c23a" :size="24"><View /></el-icon>
            <div>
              <div class="account-name">观摩者</div>
              <div class="account-desc">viewer / viewer123</div>
            </div>
          </div>
        </el-card>
      </div>
      
      <div class="login-footer">
        <p>© 2024 实盘交易管理系统. All rights reserved.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { TrendCharts, User, Lock, UserFilled, View } from '@element-plus/icons-vue'

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

function quickLogin(type) {
  if (type === 'admin') {
    form.username = 'admin'
    form.password = 'admin123'
  } else if (type === 'viewer') {
    form.username = 'viewer'
    form.password = 'viewer123'
  }
  handleLogin()
}
</script>

<style lang="scss" scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
  
  .login-box {
    width: 100%;
    max-width: 450px;
    background: white;
    border-radius: 16px;
    padding: 40px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    
    .login-header {
      text-align: center;
      margin-bottom: 40px;
      
      .el-icon {
        margin-bottom: 20px;
      }
      
      h2 {
        margin: 0 0 10px 0;
        font-size: 24px;
        color: #303133;
      }
      
      p {
        margin: 0;
        color: #909399;
        font-size: 14px;
      }
    }
    
    .test-accounts {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 20px;
      
      .el-card {
        cursor: pointer;
        transition: all 0.3s;
        
        &:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        
        :deep(.el-card__body) {
          padding: 15px;
        }
        
        .account-info {
          display: flex;
          gap: 10px;
          align-items: center;
          
          .account-name {
            font-weight: bold;
            font-size: 14px;
            margin-bottom: 5px;
          }
          
          .account-desc {
            font-size: 12px;
            color: #909399;
          }
        }
      }
    }
    
    .login-footer {
      text-align: center;
      margin-top: 20px;
      
      p {
        margin: 0;
        color: #909399;
        font-size: 12px;
      }
    }
  }
}

@media (max-width: 768px) {
  .login-container {
    .login-box {
      padding: 30px 20px;
      
      .test-accounts {
        grid-template-columns: 1fr;
      }
    }
  }
}
</style>

