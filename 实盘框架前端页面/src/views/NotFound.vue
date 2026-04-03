<template>
  <div class="not-found">
    <div class="glitch-text">404</div>
    <div class="not-found-sub">PAGE_NOT_FOUND</div>
    <el-button type="primary" @click="goHome">返回首页</el-button>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const goHome = () => {
  router.push('/dashboard')
}
</script>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: var(--bg-base);
  position: relative;
  overflow: hidden;
}

.not-found::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 212, 170, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 212, 170, 0.02) 1px, transparent 1px);
  background-size: 80px 80px;
  mask-image: radial-gradient(ellipse at center, black 20%, transparent 60%);
}

.glitch-text {
  font-family: var(--font-mono);
  font-size: 120px;
  font-weight: 900;
  color: var(--text-primary);
  position: relative;
  z-index: 1;
  text-shadow: 0 0 40px rgba(0, 212, 170, 0.15);
  animation: glitch 2.5s infinite;
}

.not-found-sub {
  color: var(--text-muted);
  font-size: 16px;
  margin: 16px 0 32px;
  z-index: 1;
  font-family: var(--font-mono);
  letter-spacing: 2px;
}

@keyframes glitch {
  0%, 90%, 100% { text-shadow: 0 0 40px rgba(0, 212, 170, 0.15); }
  92% { text-shadow: -3px 0 var(--accent-red), 3px 0 var(--accent-blue); }
  94% { text-shadow: 3px 0 var(--accent-red), -3px 0 var(--accent-blue); }
  96% { text-shadow: 0 0 40px rgba(0, 212, 170, 0.15); }
}
</style>
