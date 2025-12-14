import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { 
        title: '登录',
        public: true // 公开页面，不需要登录
      }
    },
    {
      path: '/',
      component: () => import('@/views/Layout.vue'),
      redirect: '/dashboard',
      meta: { requiresAuth: true },
      children: [
        {
          path: '/dashboard',
          name: 'Dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { 
            title: '仪表板', 
            icon: 'DataAnalysis',
            requiresAuth: true
          }
        },
        {
          path: '/strategy',
          name: 'Strategy',
          component: () => import('@/views/Strategy.vue'),
          meta: { 
            title: '策略管理', 
            icon: 'SetUp',
            requiresAuth: true,
            permission: 'strategy:view'
          }
        },
        {
          path: '/account',
          name: 'Account',
          component: () => import('@/views/Account.vue'),
          meta: { 
            title: '账户管理', 
            icon: 'Wallet',
            requiresAuth: true,
            permission: 'account:view'
          }
        },
        {
          path: '/orders',
          name: 'Orders',
          component: () => import('@/views/Orders.vue'),
          meta: { 
            title: '订单管理', 
            icon: 'List',
            requiresAuth: true,
            permission: 'order:view'
          }
        },
        {
          path: '/positions',
          name: 'Positions',
          component: () => import('@/views/Positions.vue'),
          meta: { 
            title: '持仓管理', 
            icon: 'PieChart',
            requiresAuth: true,
            permission: 'position:view'
          }
        },
        {
          path: '/users',
          name: 'UserManagement',
          component: () => import('@/views/UserManagement.vue'),
          meta: { 
            title: '用户管理', 
            icon: 'User',
            requiresAuth: true,
            permission: 'user:view',
            adminOnly: true // 仅管理员可访问
          }
        },
        {
          path: '/logs',
          name: 'Logs',
          component: () => import('@/views/Logs.vue'),
          meta: { 
            title: '系统日志', 
            icon: 'Document',
            requiresAuth: true
          }
        }
      ]
    }
  ]
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  
  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - 实盘交易管理系统`
  }
  
  // 公开页面直接放行
  if (to.meta.public) {
    next()
    return
  }
  
  // 需要登录的页面
  if (to.meta.requiresAuth) {
    if (!userStore.isLoggedIn) {
      ElMessage.warning('请先登录')
      next({
        path: '/login',
        query: { redirect: to.fullPath }
      })
      return
    }
    
    // 检查权限
    if (to.meta.permission) {
      if (!userStore.hasPermission(to.meta.permission)) {
        ElMessage.error('您没有访问此页面的权限')
        next(from.fullPath || '/dashboard')
        return
      }
    }
    
    // 检查是否仅管理员可访问
    if (to.meta.adminOnly && !userStore.isSuperAdmin) {
      ElMessage.error('此页面仅管理员可访问')
      next(from.fullPath || '/dashboard')
      return
    }
  }
  
  next()
})

export default router

