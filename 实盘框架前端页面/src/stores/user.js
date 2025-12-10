import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { wsClient } from '@/services/WebSocketClient'

// 用户角色枚举
export const UserRole = {
  SUPER_ADMIN: 'super_admin',  // 超级管理员
  VIEWER: 'viewer'              // 观摩者
}

// 用户角色中文名称
export const UserRoleNames = {
  [UserRole.SUPER_ADMIN]: '超级管理员',
  [UserRole.VIEWER]: '观摩者'
}

// 权限定义
export const Permissions = {
  // 策略权限
  STRATEGY_VIEW: 'strategy:view',
  STRATEGY_CREATE: 'strategy:create',
  STRATEGY_START: 'strategy:start',
  STRATEGY_STOP: 'strategy:stop',
  STRATEGY_DELETE: 'strategy:delete',
  
  // 账户权限
  ACCOUNT_VIEW: 'account:view',
  ACCOUNT_CREATE: 'account:create',
  ACCOUNT_EDIT: 'account:edit',
  ACCOUNT_DELETE: 'account:delete',
  ACCOUNT_SYNC: 'account:sync',
  
  // 订单权限
  ORDER_VIEW: 'order:view',
  ORDER_CREATE: 'order:create',
  ORDER_CANCEL: 'order:cancel',
  
  // 持仓权限
  POSITION_VIEW: 'position:view',
  POSITION_CLOSE: 'position:close',
  
  // 用户管理权限
  USER_VIEW: 'user:view',
  USER_CREATE: 'user:create',
  USER_EDIT: 'user:edit',
  USER_DELETE: 'user:delete'
}

// 角色权限映射
const RolePermissions = {
  [UserRole.SUPER_ADMIN]: [
    // 所有权限
    ...Object.values(Permissions)
  ],
  [UserRole.VIEWER]: [
    // 仅查看权限
    Permissions.STRATEGY_VIEW,
    Permissions.ACCOUNT_VIEW,
    Permissions.ORDER_VIEW,
    Permissions.POSITION_VIEW
  ]
}

export const useUserStore = defineStore('user', () => {
  // 状态
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(null)
  const users = ref([])
  const loading = ref(false)
  
  // 计算属性
  const isLoggedIn = computed(() => !!token.value)
  
  const isSuperAdmin = computed(() => 
    userInfo.value?.role === UserRole.SUPER_ADMIN
  )
  
  const isViewer = computed(() => 
    userInfo.value?.role === UserRole.VIEWER
  )
  
  const userRole = computed(() => userInfo.value?.role || '')
  
  const userRoleName = computed(() => 
    UserRoleNames[userRole.value] || '未知'
  )
  
  const permissions = computed(() => {
    if (!userInfo.value) return []
    return RolePermissions[userInfo.value.role] || []
  })
  
  // 权限检查方法
  function hasPermission(permission) {
    return permissions.value.includes(permission)
  }
  
  function hasAnyPermission(permissionList) {
    return permissionList.some(p => hasPermission(p))
  }
  
  function hasAllPermissions(permissionList) {
    return permissionList.every(p => hasPermission(p))
  }
  
  // 登录
  async function login(credentials) {
    try {
      loading.value = true
      
      // Mock登录逻辑
      if (import.meta.env.DEV) {
        // 开发环境使用Mock数据
        let mockUser
        if (credentials.username === 'admin' && credentials.password === 'admin123') {
          mockUser = {
            id: 1,
            username: 'admin',
            name: '超级管理员',
            role: UserRole.SUPER_ADMIN,
            email: 'admin@example.com',
            avatar: '',
            createdAt: new Date('2024-01-01')
          }
        } else if (credentials.username === 'viewer' && credentials.password === 'viewer123') {
          mockUser = {
            id: 2,
            username: 'viewer',
            name: '观摩者',
            role: UserRole.VIEWER,
            email: 'viewer@example.com',
            avatar: '',
            createdAt: new Date('2024-01-15')
          }
        } else {
          throw new Error('用户名或密码错误')
        }
        
        const mockToken = 'mock_token_' + Date.now()
        token.value = mockToken
        userInfo.value = mockUser
        localStorage.setItem('token', mockToken)
        localStorage.setItem('userInfo', JSON.stringify(mockUser))
        
        ElMessage.success('登录成功')
        return { success: true, user: mockUser }
      }
      
      // 生产环境调用真实接口
      const res = await userApi.login(credentials)
      token.value = res.data.token
      userInfo.value = res.data.user
      
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('userInfo', JSON.stringify(res.data.user))
      
      ElMessage.success('登录成功')
      return res
    } catch (error) {
      ElMessage.error(error.message || '登录失败')
      throw error
    } finally {
      loading.value = false
    }
  }
  
  // 登出
  async function logout() {
    try {
      if (!import.meta.env.DEV) {
        await userApi.logout()
      }
      
      token.value = ''
      userInfo.value = null
      
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      
      ElMessage.success('已退出登录')
    } catch (error) {
      console.error('登出失败:', error)
    }
  }
  
  // 获取用户信息
  async function fetchUserInfo() {
    try {
      if (import.meta.env.DEV) {
        // 开发环境从本地存储恢复
        const savedUserInfo = localStorage.getItem('userInfo')
        if (savedUserInfo) {
          userInfo.value = JSON.parse(savedUserInfo)
          return
        }
      }
      
      const res = await userApi.getUserInfo()
      userInfo.value = res.data
      localStorage.setItem('userInfo', JSON.stringify(res.data))
    } catch (error) {
      console.error('获取用户信息失败:', error)
      // 如果获取失败，清除登录状态
      await logout()
    }
  }
  
  // 获取用户列表（仅管理员）
  async function fetchUsers(params) {
    if (!hasPermission(Permissions.USER_VIEW)) {
      ElMessage.error('无权限查看用户列表')
      return
    }
    
    loading.value = true
    try {
      // Mock用户列表（C++端未实现用户管理）
      users.value = [
          {
            id: 1,
            username: 'admin',
            name: '超级管理员',
            role: UserRole.SUPER_ADMIN,
            email: 'admin@example.com',
            status: 'active',
            lastLogin: new Date(),
            createdAt: new Date('2024-01-01')
          },
          {
            id: 2,
            username: 'viewer',
            name: '观摩者',
            role: UserRole.VIEWER,
            email: 'viewer@example.com',
            status: 'active',
            lastLogin: new Date(),
            createdAt: new Date('2024-01-15')
          },
          {
            id: 3,
            username: 'viewer2',
            name: '观摩者2',
            role: UserRole.VIEWER,
            email: 'viewer2@example.com',
            status: 'inactive',
            lastLogin: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
            createdAt: new Date('2024-02-01')
          }
        ]
    } finally {
      loading.value = false
    }
  }
  
  // 创建用户（仅管理员）
  async function createUser(data) {
    if (!hasPermission(Permissions.USER_CREATE)) {
      ElMessage.error('无权限创建用户')
      return
    }
    
    // 通过WebSocket发送命令
    wsClient.send('create_user', data)
    await fetchUsers()
    return { success: true }
  }
  
  // 更新用户（仅管理员）
  async function updateUser(id, data) {
    if (!hasPermission(Permissions.USER_EDIT)) {
      ElMessage.error('无权限编辑用户')
      return
    }
    
    wsClient.send('update_user', { id, ...data })
    await fetchUsers()
    return { success: true }
  }
  
  // 删除用户（仅管理员）
  async function deleteUser(id) {
    if (!hasPermission(Permissions.USER_DELETE)) {
      ElMessage.error('无权限删除用户')
      return
    }
    
    wsClient.send('delete_user', { id })
    await fetchUsers()
    return { success: true }
  }
  
  // 修改密码
  async function changePassword(data) {
    wsClient.send('change_password', data)
    ElMessage.success('密码修改成功，请重新登录')
    await logout()
    return { success: true }
  }
  
  // 初始化（从本地存储恢复）
  function init() {
    const savedToken = localStorage.getItem('token')
    const savedUserInfo = localStorage.getItem('userInfo')
    
    if (savedToken && savedUserInfo) {
      token.value = savedToken
      userInfo.value = JSON.parse(savedUserInfo)
    }
  }
  
  return {
    // 状态
    token,
    userInfo,
    users,
    loading,
    
    // 计算属性
    isLoggedIn,
    isSuperAdmin,
    isViewer,
    userRole,
    userRoleName,
    permissions,
    
    // 方法
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    login,
    logout,
    fetchUserInfo,
    fetchUsers,
    createUser,
    updateUser,
    deleteUser,
    changePassword,
    init
  }
})

