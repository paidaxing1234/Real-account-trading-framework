<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside :width="sidebarWidth" class="layout-aside">
      <div class="logo">
        <el-icon v-if="!collapsed" size="32"><TrendCharts /></el-icon>
        <span v-if="!collapsed" class="logo-text">实盘交易系统</span>
      </div>
      
      <el-menu
        :default-active="currentRoute"
        :collapse="collapsed"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>仪表板</template>
        </el-menu-item>
        
        <el-menu-item index="/strategy" v-permission="'strategy:view'">
          <el-icon><SetUp /></el-icon>
          <template #title>策略管理</template>
        </el-menu-item>
        
        <el-menu-item index="/account" v-permission="'account:view'">
          <el-icon><Wallet /></el-icon>
          <template #title>账户管理</template>
        </el-menu-item>
        
        <el-menu-item index="/orders" v-permission="'order:view'">
          <el-icon><List /></el-icon>
          <template #title>订单管理</template>
        </el-menu-item>
        
        <el-menu-item index="/positions" v-permission="'position:view'">
          <el-icon><PieChart /></el-icon>
          <template #title>持仓管理</template>
        </el-menu-item>
        
        <el-menu-item index="/users" v-permission="'user:view'">
          <el-icon><User /></el-icon>
          <template #title>用户管理</template>
        </el-menu-item>
        
        <el-menu-item index="/papertrading">
          <el-icon><EditPen /></el-icon>
          <template #title>模拟交易</template>
        </el-menu-item>
        
        <el-menu-item index="/logs">
          <el-icon><Document /></el-icon>
          <template #title>系统日志</template>
        </el-menu-item>
      </el-menu>
      
      <div class="sidebar-footer">
        <el-button
          circle
          :icon="collapsed ? 'Expand' : 'Fold'"
          @click="toggleSidebar"
        />
      </div>
    </el-aside>
    
    <!-- 主内容区 -->
    <el-container class="main-container">
      <!-- 顶部栏 -->
      <el-header class="layout-header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentPageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        
        <div class="header-right">
          <!-- WebSocket 连接状态 -->
          <div class="ws-status">
            <el-tooltip :content="wsConnected ? '已连接' : '未连接'">
              <el-icon :color="wsConnected ? '#67c23a' : '#f56c6c'">
                <Connection />
              </el-icon>
            </el-tooltip>
          </div>
          
          <!-- 通知 -->
          <el-badge :value="notifications.length" :hidden="notifications.length === 0">
            <el-button circle :icon="Bell" @click="showNotifications" />
          </el-badge>
          
          <!-- 主题切换 -->
          <el-switch
            v-model="isDark"
            inline-prompt
            :active-icon="Moon"
            :inactive-icon="Sunny"
            @change="toggleTheme"
          />
          
          <!-- 用户菜单 -->
          <el-dropdown @command="handleUserCommand">
            <div class="user-dropdown">
              <el-avatar :size="32" :icon="UserFilled" />
              <div class="user-info" v-if="!collapsed">
                <div class="user-name">{{ userStore.userInfo?.name }}</div>
                <div class="user-role">{{ userStore.userRoleName }}</div>
              </div>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  <div style="text-align: center;">
                    <div style="font-weight: bold;">{{ userStore.userInfo?.username }}</div>
                    <el-tag size="small" style="margin-top: 5px;">
                      {{ userStore.userRoleName }}
                    </el-tag>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item divided command="changePassword">
                  <el-icon><Lock /></el-icon>
                  修改密码
                </el-dropdown-item>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <!-- 主内容 -->
      <el-main class="layout-main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import {
  DataAnalysis,
  SetUp,
  Wallet,
  List,
  PieChart,
  User,
  Document,
  TrendCharts,
  Connection,
  Bell,
  Moon,
  Sunny,
  UserFilled,
  Lock,
  SwitchButton,
  EditPen
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const collapsed = computed(() => appStore.sidebarCollapsed)
const sidebarWidth = computed(() => collapsed.value ? '64px' : '200px')
const currentRoute = computed(() => route.path)
const currentPageTitle = computed(() => route.meta.title || '')
const wsConnected = computed(() => appStore.wsConnected)
const notifications = computed(() => appStore.notifications)

const isDark = ref(appStore.theme === 'dark')

function toggleSidebar() {
  appStore.toggleSidebar()
}

function toggleTheme(value) {
  appStore.setTheme(value ? 'dark' : 'light')
}

function showNotifications() {
  // TODO: 显示通知列表
  console.log('显示通知')
}

async function handleUserCommand(command) {
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm(
        '确定要退出登录吗？',
        '提示',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
      
      await userStore.logout()
      router.push('/login')
    } catch (error) {
      // 用户取消
    }
  } else if (command === 'changePassword') {
    // TODO: 打开修改密码对话框
    console.log('修改密码')
  }
}
</script>

<style lang="scss" scoped>
.layout-container {
  height: 100vh;
  
  .layout-aside {
    background: #fff;
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    transition: width 0.3s;
    
    .logo {
      height: 60px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      border-bottom: 1px solid var(--border-color);
      
      .logo-text {
        font-size: 16px;
        font-weight: bold;
        color: var(--primary-color);
      }
    }
    
    .sidebar-menu {
      flex: 1;
      border-right: none;
    }
    
    .sidebar-footer {
      height: 50px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-top: 1px solid var(--border-color);
    }
  }
  
  .main-container {
    background: var(--bg-color);
    
    .layout-header {
      background: #fff;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      
      .header-right {
        display: flex;
        align-items: center;
        gap: 20px;
        
        .ws-status {
          display: flex;
          align-items: center;
        }
        
        .user-dropdown {
          display: flex;
          align-items: center;
          gap: 10px;
          cursor: pointer;
          
          .user-info {
            .user-name {
              font-size: 14px;
              font-weight: 500;
            }
            
            .user-role {
              font-size: 12px;
              color: var(--text-secondary);
            }
          }
        }
      }
    }
    
    .layout-main {
      padding: 20px;
      overflow-y: auto;
    }
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

