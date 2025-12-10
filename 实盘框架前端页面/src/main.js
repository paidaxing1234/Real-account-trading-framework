import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import { useAppStore } from './stores/app'
import { permission, role } from './directives/permission'
import PermissionComponent from './components/Permission/index.vue'
import WebSocketPlugin, { wsClient } from './services/WebSocketClient'
import './styles/main.scss'

const app = createApp(App)

// 创建Pinia实例
const pinia = createPinia()
app.use(pinia)

// 初始化用户Store（从本地存储恢复登录状态）
const userStore = useUserStore()
userStore.init()

// 初始化应用Store（监听EventClient连接状态）
const appStore = useAppStore()
appStore.init()

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册权限指令
app.directive('permission', permission)
app.directive('role', role)

// 注册权限组件
app.component('Permission', PermissionComponent)

// 注册WebSocket插件
app.use(WebSocketPlugin)

app.use(router)
app.use(ElementPlus, {
  locale: zhCn,
})

app.mount('#app')

// 用户登录后启动WebSocket连接
router.afterEach((to) => {
  if (to.meta.requiresAuth && userStore.isLoggedIn) {
    // 确保WebSocket已连接
    if (!wsClient.connected) {
      wsClient.connect()
    }
  }
})

