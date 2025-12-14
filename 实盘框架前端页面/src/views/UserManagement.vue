<template>
  <div class="user-management-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>用户管理</h2>
        <p>管理系统用户和权限</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
        添加用户
      </el-button>
    </div>
    
    <!-- 用户统计 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="8">
        <el-card class="stat-card">
          <el-statistic title="总用户数" :value="users.length">
            <template #prefix>
              <el-icon><User /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="stat-card">
          <el-statistic title="超级管理员" :value="adminCount">
            <template #prefix>
              <el-icon style="color: #409eff;"><UserFilled /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="stat-card">
          <el-statistic title="观摩者" :value="viewerCount">
            <template #prefix>
              <el-icon style="color: #67c23a;"><View /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 用户列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>用户列表</span>
          <el-input
            v-model="searchText"
            placeholder="搜索用户名或邮箱"
            :prefix-icon="Search"
            clearable
            style="width: 250px"
          />
        </div>
      </template>
      
      <el-table :data="filteredUsers" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        
        <el-table-column prop="username" label="用户名" width="150">
          <template #default="{ row }">
            <div class="user-name">
              <el-avatar :size="32" :src="row.avatar">
                {{ (row.name || 'U').charAt(0) }}
              </el-avatar>
              <span>{{ row.username }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="name" label="姓名" width="120" />
        
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="getRoleType(row.role)">
              {{ getRoleName(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="email" label="邮箱" width="200" />
        
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '激活' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="lastLogin" label="最后登录" width="180">
          <template #default="{ row }">
            {{ formatTime(row.lastLogin) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="createdAt" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.createdAt) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              type="warning"
              size="small"
              @click="handleResetPassword(row)"
            >
              重置密码
            </el-button>
            <el-button
              type="danger"
              size="small"
              :disabled="row.id === userStore.userInfo?.id"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 创建/编辑用户对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingUser ? '编辑用户' : '创建用户'"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :disabled="!!editingUser"
          />
        </el-form-item>
        
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="请输入姓名" />
        </el-form-item>
        
        <el-form-item label="密码" prop="password" v-if="!editingUser">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码（至少6位）"
            show-password
          />
        </el-form-item>
        
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option
              label="超级管理员"
              :value="UserRole.SUPER_ADMIN"
            />
            <el-option
              label="观摩者"
              :value="UserRole.VIEWER"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="状态" prop="status">
          <el-switch
            v-model="form.status"
            active-value="active"
            inactive-value="inactive"
            active-text="激活"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          {{ editingUser ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore, UserRole, UserRoleNames } from '@/stores/user'
import { formatTime } from '@/utils/format'
import {
  Plus,
  Search,
  User,
  UserFilled,
  View
} from '@element-plus/icons-vue'

const userStore = useUserStore()

const searchText = ref('')
const showCreateDialog = ref(false)
const editingUser = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  username: '',
  name: '',
  password: '',
  email: '',
  role: UserRole.VIEWER,
  status: 'active'
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度为3-20个字符', trigger: 'blur' }
  ],
  name: [
    { required: true, message: '请输入姓名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  role: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ]
}

const loading = computed(() => userStore.loading)
const users = computed(() => userStore.users)

const adminCount = computed(() =>
  users.value.filter(u => u.role === UserRole.SUPER_ADMIN).length
)

const viewerCount = computed(() =>
  users.value.filter(u => u.role === UserRole.VIEWER).length
)

const filteredUsers = computed(() => {
  if (!searchText.value) return users.value
  
  const search = searchText.value.toLowerCase()
  return users.value.filter(u =>
    u.username.toLowerCase().includes(search) ||
    u.email.toLowerCase().includes(search) ||
    u.name.toLowerCase().includes(search)
  )
})

function getRoleType(role) {
  return role === UserRole.SUPER_ADMIN ? '' : 'success'
}

function getRoleName(role) {
  return UserRoleNames[role] || role
}

function handleEdit(row) {
  editingUser.value = row
  Object.assign(form, {
    username: row.username,
    name: row.name,
    email: row.email,
    role: row.role,
    status: row.status,
    password: ''
  })
  showCreateDialog.value = true
}

async function handleResetPassword(row) {
  try {
    await ElMessageBox.confirm(
      `确定要重置用户 ${row.username} 的密码吗？重置后密码为: 123456`,
      '重置密码',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    // TODO: 调用重置密码接口
    ElMessage.success('密码重置成功，新密码: 123456')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重置密码失败')
    }
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 ${row.username} 吗？此操作不可恢复。`,
      '删除用户',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await userStore.deleteUser(row.id)
    ElMessage.success('用户删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除用户失败')
    }
  }
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
    
    submitting.value = true
    
    if (editingUser.value) {
      // 编辑用户
      await userStore.updateUser(editingUser.value.id, form)
      ElMessage.success('用户更新成功')
    } else {
      // 创建用户
      await userStore.createUser(form)
      ElMessage.success('用户创建成功')
    }
    
    handleCloseDialog()
  } catch (error) {
    if (error !== false) {
      ElMessage.error(error.message || '操作失败')
    }
  } finally {
    submitting.value = false
  }
}

function handleCloseDialog() {
  showCreateDialog.value = false
  editingUser.value = null
  formRef.value?.resetFields()
}

onMounted(() => {
  userStore.fetchUsers()
})
</script>

<style lang="scss" scoped>
.user-management-page {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    
    h2 {
      margin: 0 0 5px 0;
    }
    
    p {
      margin: 0;
      color: var(--text-secondary);
    }
  }
  
  .stats-row {
    margin-bottom: 20px;
    
    .stat-card {
      :deep(.el-card__body) {
        padding: 20px;
      }
    }
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .user-name {
    display: flex;
    align-items: center;
    gap: 10px;
  }
}
</style>

