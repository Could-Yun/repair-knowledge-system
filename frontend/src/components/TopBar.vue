<template>
  <header class="app-topbar">
    <!-- 页面标题 -->
    <div class="topbar-title">
      <span class="title-bracket">[</span>
      <span class="title-text">{{ pageTitle }}</span>
      <span class="title-bracket">]</span>
    </div>

    <!-- 系统状态 -->
    <div class="topbar-status">
      <div class="status-item">
        <span class="glow-dot green"></span>
        <span class="status-label">系统在线</span>
      </div>
      <div class="status-item status-time">
        {{ currentTime }}
      </div>
    </div>

    <!-- 移动端菜单按钮 -->
    <button class="mobile-menu-btn" @click="showMobileMenu = true"><AppIcon name="menu"/></button>
  </header>

  <!-- 移动端侧边菜单 -->
  <van-popup v-model:show="showMobileMenu" position="left" :style="{ width: '220px', height: '100%' }">
    <SideMenu />
  </van-popup>
</template>

<script setup>
import { useRoute } from 'vue-router'
import SideMenu from '@/components/SideMenu.vue'

const route = useRoute()
const showMobileMenu = ref(false)
const currentTime = ref('')

const titleMap = {
  '/diagnosis': '故障诊断',
  '/knowledge': '知识检索',
  '/workflow':  '作业指引',
  '/cases/new': '提交案例',
  '/cases/my':  '我的案例',
  '/audit':     '审核面板',
  '/dashboard': '管理驾驶舱',
  '/profile':   '个人中心',
}

const pageTitle = computed(() => titleMap[route.path] || '设备检修智能作业系统')

function updateTime() {
  currentTime.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}
updateTime()
const timer = setInterval(updateTime, 1000)
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.topbar-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 15px;
  font-weight: 600;
}
.title-bracket { color: var(--accent-cyan); opacity: 0.6; }
.title-text    { color: var(--text-primary); letter-spacing: 0.04em; }

.topbar-status {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}
.status-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--text-secondary);
}
.status-label { display: none; }
@media (min-width: 900px) { .status-label { display: inline; } }
.status-time { font-family: monospace; color: var(--accent-cyan); opacity: 0.7; }

.mobile-menu-btn {
  display: none;
  background: none;
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 18px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-left: auto;
}
@media (max-width: 768px) {
  .mobile-menu-btn { display: block; }
  .topbar-status { display: none; }
}
</style>
