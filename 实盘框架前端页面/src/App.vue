<template>
  <el-config-provider :locale="locale">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { ref } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

const locale = ref(zhCn)
</script>

<style lang="scss">
:root {
  /* ── 白天模式（默认） ── */
  --bg-base: #f5f7fa;
  --bg-surface: #ffffff;
  --bg-elevated: #ffffff;
  --bg-card: #ffffff;
  --bg-card-hover: #f9fafb;
  --bg-input: #ffffff;

  --border-color: #e4e7ed;
  --border-glow: rgba(0, 180, 140, 0.2);
  --border-active: rgba(0, 180, 140, 0.5);

  --text-primary: #1d2129;
  --text-secondary: #4e5969;
  --text-muted: #86909c;

  --accent-green: #00b96b;
  --accent-red: #f53f3f;
  --accent-blue: #3b82f6;
  --accent-orange: #ff7d00;
  --accent-purple: #722ed1;

  --primary-color: #00b96b;
  --success-color: #00b96b;
  --danger-color: #f53f3f;
  --warning-color: #ff7d00;
  --info-color: #3b82f6;

  --shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.08);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.1);
  --shadow-glow: 0 0 12px rgba(0, 180, 140, 0.06);

  --font-ui: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'Consolas', 'Monaco', monospace;
  --radius: 8px;
  --log-bg: #1e1e1e;
  --log-text: #d4d4d4;
}

/* ── 暗色模式 ── */
html.dark {
  --bg-base: #0d1117;
  --bg-surface: #161b22;
  --bg-elevated: #1c2333;
  --bg-card: #161b22;
  --bg-card-hover: #1c2333;
  --bg-input: #0d1117;

  --border-color: #30363d;
  --border-glow: rgba(0, 212, 170, 0.3);
  --border-active: rgba(0, 212, 170, 0.6);

  --text-primary: #e6edf3;
  --text-secondary: #b1bac4;
  --text-muted: #8b949e;

  --accent-green: #00d4aa;
  --accent-red: #ff7b72;
  --accent-blue: #58a6ff;
  --accent-orange: #f0883e;
  --accent-purple: #bc8cff;

  --primary-color: #00d4aa;
  --success-color: #00d4aa;
  --danger-color: #ff7b72;
  --warning-color: #f0883e;
  --info-color: #58a6ff;

  --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.4);
  --shadow-md: 0 4px 20px rgba(0, 0, 0, 0.5);
  --shadow-glow: 0 0 20px rgba(0, 212, 170, 0.1);
  --log-bg: #0d1117;
  --log-text: #e6edf3;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
  font-family: var(--font-ui);
  background: var(--bg-base);
  color: var(--text-primary);
}

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--text-muted); border-radius: 3px; opacity: 0.3; }
::-webkit-scrollbar-thumb:hover { opacity: 0.5; }

/* ── 通用文本色 ── */
.text-success { color: var(--accent-green) !important; }
.text-danger { color: var(--accent-red) !important; }
.text-warning { color: var(--accent-orange) !important; }
.text-info { color: var(--accent-blue) !important; }

/* ── 数字字体 ── */
.stat-value, .price, [class*="stat-value"] {
  font-family: var(--font-mono);
}

/* ── Element Plus 覆写（使用 CSS 变量，自动适应明暗） ── */
.el-card {
  --el-card-bg-color: var(--bg-card);
  background: var(--bg-card) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: var(--radius) !important;
  color: var(--text-primary) !important;
  box-shadow: var(--shadow-sm) !important;
}
.el-card__header {
  border-bottom: 1px solid var(--border-color) !important;
  color: var(--text-primary) !important;
}

.el-table {
  --el-table-bg-color: var(--bg-card);
  --el-table-tr-bg-color: var(--bg-card);
  --el-table-header-bg-color: var(--bg-base);
  --el-table-row-hover-bg-color: var(--bg-card-hover);
  --el-table-border-color: var(--border-color);
  --el-table-text-color: var(--text-primary);
  --el-table-header-text-color: var(--text-secondary);
  color: var(--text-primary);
}
.el-table th.el-table__cell {
  background: var(--bg-base) !important;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary) !important;
}

.el-menu {
  background-color: transparent !important;
  border-right: none !important;
}
.el-menu-item {
  color: var(--text-primary) !important;
  &:hover, &:focus {
    background: rgba(0, 180, 140, 0.06) !important;
    color: var(--accent-green) !important;
  }
  &.is-active {
    color: var(--accent-green) !important;
    background: rgba(0, 180, 140, 0.1) !important;
    border-right: 2px solid var(--accent-green) !important;
  }
}

.el-input__wrapper {
  background: var(--bg-input) !important;
  border: 1px solid var(--border-color) !important;
  box-shadow: none !important;
  &:hover { border-color: var(--border-glow) !important; }
  &.is-focus { border-color: var(--accent-green) !important; box-shadow: 0 0 6px rgba(0,180,140,0.12) !important; }
}
.el-input__inner { color: var(--text-primary) !important; }
.el-input__prefix .el-icon { color: var(--text-muted) !important; }
.el-input .el-input__wrapper .el-input__inner::placeholder { color: var(--text-muted) !important; }

.el-select .el-select__wrapper {
  background: var(--bg-input) !important;
  border: 1px solid var(--border-color) !important;
  box-shadow: none !important;
  color: var(--text-primary) !important;
}

.el-button--primary {
  --el-button-bg-color: var(--accent-green);
  --el-button-border-color: var(--accent-green);
  --el-button-hover-bg-color: var(--accent-green);
  --el-button-hover-border-color: var(--accent-green);
  background-color: var(--accent-green) !important;
  border-color: var(--accent-green) !important;
  color: #fff !important;
  font-weight: 600;
  &:hover { filter: brightness(1.1); }
}

.el-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
}
.el-tag--success { background: rgba(0, 180, 140, 0.1) !important; color: var(--accent-green) !important; border-color: transparent !important; }
.el-tag--danger { background: rgba(245, 63, 63, 0.1) !important; color: var(--accent-red) !important; border-color: transparent !important; }
.el-tag--warning { background: rgba(255, 125, 0, 0.1) !important; color: var(--accent-orange) !important; border-color: transparent !important; }
.el-tag--info { background: rgba(0,0,0,0.04) !important; color: var(--text-secondary) !important; border-color: transparent !important; }
.el-tag--primary { background: rgba(0, 180, 140, 0.1) !important; color: var(--accent-green) !important; border-color: transparent !important; }

.el-dialog {
  --el-dialog-bg-color: var(--bg-elevated);
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: 12px !important;
}
.el-dialog__title { color: var(--text-primary) !important; }
.el-dialog__headerbtn .el-dialog__close { color: var(--text-muted) !important; }

.el-form-item__label { color: var(--text-primary) !important; }
.el-breadcrumb__inner { color: var(--text-secondary) !important; }
.el-breadcrumb__separator { color: var(--text-muted) !important; }

.el-dropdown-menu {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-color) !important;
}
.el-dropdown-menu__item {
  color: var(--text-primary) !important;
  &:hover { background: var(--bg-card-hover) !important; color: var(--accent-green) !important; }
}

.el-switch.is-checked .el-switch__core { background-color: var(--accent-green) !important; border-color: var(--accent-green) !important; }
.el-checkbox__label { color: var(--text-primary) !important; }
.el-empty__description p { color: var(--text-secondary) !important; }
.el-loading-mask { background: rgba(255,255,255,0.6) !important; }
html.dark .el-loading-mask { background: rgba(13,17,23,0.7) !important; }

.el-popper.is-light { background: var(--bg-elevated) !important; border: 1px solid var(--border-color) !important; color: var(--text-primary) !important; }

.el-select-dropdown {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-color) !important;
}
.el-select-dropdown__item {
  color: var(--text-primary) !important;
  &:hover, &.is-hovering { background: var(--bg-card-hover) !important; }
  &.is-selected { color: var(--accent-green) !important; font-weight: 600; }
}

.el-badge__content { background-color: var(--accent-red) !important; }

.el-pagination {
  --el-pagination-bg-color: transparent;
  --el-pagination-button-bg-color: var(--bg-input);
  --el-pagination-text-color: var(--text-secondary);
  --el-pagination-hover-color: var(--accent-green);
}

/* ── 暗色模式 tag 颜色加强 ── */
html.dark {
  .el-tag--success { background: rgba(0, 212, 170, 0.15) !important; }
  .el-tag--danger { background: rgba(255, 123, 114, 0.15) !important; }
  .el-tag--warning { background: rgba(240, 136, 62, 0.15) !important; }
  .el-tag--info { background: rgba(139, 148, 158, 0.15) !important; }
  .el-tag--primary { background: rgba(0, 212, 170, 0.15) !important; }
}

/* ── 动画 ── */
@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 8px rgba(0, 212, 170, 0.1); }
  50% { box-shadow: 0 0 16px rgba(0, 212, 170, 0.25); }
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes price-flash-up {
  0% { background: rgba(0, 212, 170, 0.3); }
  100% { background: transparent; }
}
@keyframes price-flash-down {
  0% { background: rgba(255, 107, 107, 0.3); }
  100% { background: transparent; }
}
.animate-in {
  animation: fadeInUp 0.4s ease-out both;
}
</style>

