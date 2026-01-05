import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 3000,
    strictPort: false, // 如果端口被占用，自动尝试下一个
    host: true // 允许外部访问
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false
  }
  // 注意：VITE_WS_URL 由 .env.development 或 .env.local 自动加载
  // 不需要在 define 中手动设置
})

