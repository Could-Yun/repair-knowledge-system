<template>
  <aside class="app-sidebar">
    <!-- Logo -->
    <div class="sidebar-logo">
      <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="10" stroke="#22ddff" stroke-width="1.5" fill="none"/>
        <circle cx="16" cy="16" r="5" fill="#22ddff" opacity="0.8"/>
        <line x1="16" y1="3" x2="16" y2="8" stroke="#22ddff" stroke-width="1.5"/>
        <line x1="16" y1="24" x2="16" y2="29" stroke="#22ddff" stroke-width="1.5"/>
        <line x1="3" y1="16" x2="8" y2="16" stroke="#22ddff" stroke-width="1.5"/>
        <line x1="24" y1="16" x2="29" y2="16" stroke="#22ddff" stroke-width="1.5"/>
      </svg>
      <div class="logo-text">
        <span class="logo-main">智检系统</span>
        <span class="logo-sub">REPAIR·AI</span>
      </div>
    </div>

    <!-- 角色徽章 -->
    <div class="role-badge">
      <span class="glow-dot" :class="isAdmin ? 'orange' : 'green'"></span>
      <span>{{ isAdmin ? '管理员' : '一线人员' }}</span>
      <span class="username">{{ displayName }}</span>
    </div>

    <!-- 导航菜单 -->
    <nav class="sidebar-nav">
      <!-- 首页：数据驾驶舱（所有人） -->
      <div class="nav-group">
        <router-link to="/dashboard" class="nav-item home-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/></svg></i><span>首页 · 数据驾驶舱</span>
        </router-link>
      </div>

      <div class="nav-group">
        <div class="nav-group-title">工作台</div>
        <router-link to="/diagnosis" class="nav-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 2 4 14h6l-1 8 9-12h-6l2-8z"/></svg></i><span>故障诊断</span>
        </router-link>
        <router-link to="/knowledge" class="nav-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg></i><span>知识检索</span>
        </router-link>
        <router-link to="/workflow" class="nav-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4.5V3h6v1.5"/><path d="M8.5 10h7M8.5 14h7M8.5 18h4"/></svg></i><span>作业指引</span>
        </router-link>
        <router-link v-if="isAdmin" to="/audit" class="nav-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.2 2.2L15.5 9.5"/></svg></i>
          <span>审核面板</span>
          <span v-if="pendingCount > 0" class="badge">{{ pendingCount }}</span>
        </router-link>
      </div>

      <div class="nav-group">
        <div class="nav-group-title">案例管理</div>
        <router-link to="/cases/new" class="nav-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg></i><span>提交案例</span>
        </router-link>
        <router-link to="/cases/my" class="nav-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg></i><span>我的案例</span>
        </router-link>
        <router-link to="/documents" class="nav-item">
          <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/></svg></i><span>知识文档</span>
        </router-link>
      </div>
    </nav>

    <!-- 底部 -->
    <div class="sidebar-footer">
      <router-link to="/profile" class="nav-item">
        <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c0-3.6 3.4-5.5 7.5-5.5s7.5 1.9 7.5 5.5"/></svg></i><span>个人中心</span>
      </router-link>
      <button class="nav-item logout-btn" @click="logout">
        <i class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-2"/><path d="M10 12h11M18 9l3 3-3 3"/></svg></i><span>退出登录</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { useUserStore } from '@/stores/user'
import { useRouter } from 'vue-router'
import { auditApi, documentsApi, feedbackApi, workflowApi } from '@/api'

const store  = useUserStore()
const router = useRouter()
const { isAdmin, displayName } = storeToRefs(store)

// 待审总数 = 待审案例 + 待审文档 + 待采纳反馈 + 作业指引申请（问题 #2：审核面板是一切待审的唯一入口）
const pendingCount = ref(0)

if (store.isAdmin) {
  Promise.allSettled([
    auditApi.pending({ page: 1, size: 1, status: 'pending' }),
    documentsApi.pending({ page: 1, size: 1, status: 'pending' }),
    feedbackApi.pending({ page: 1, size: 1 }),
    workflowApi.listRequests({ page: 1, size: 1, status: 'pending' }),
  ]).then(results => {
    pendingCount.value = results.reduce(
      (sum, r) => sum + (r.status === 'fulfilled' ? (r.value?.total || 0) : 0), 0
    )
  })
}

function logout() {
  store.logout()
  router.push('/login')
}
</script>

<script>
import { storeToRefs } from 'pinia'
</script>

<style scoped>
.app-sidebar {
  display: flex;
  flex-direction: column;
  padding: 0;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--border-color);
}
.logo-text { display: flex; flex-direction: column; }
.logo-main { font-size: 15px; font-weight: 700; color: var(--accent-cyan); letter-spacing: 0.08em; }
.logo-sub  { font-size: 13px; color: var(--text-muted); letter-spacing: 0.15em; margin-top: 1px; }

.role-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 14px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
}
.username { margin-left: auto; color: var(--text-primary); font-weight: 500; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.nav-group { margin-bottom: 4px; }
.nav-group-title {
  font-size: 13px;
  color: var(--text-muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 10px 16px 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 15px;
  border-radius: 0;
  transition: all 0.2s;
  cursor: pointer;
  border: none;
  background: none;
  width: 100%;
  text-align: left;
  position: relative;
}
.nav-item:hover { color: var(--text-primary); background: rgba(34,221,255,0.05); }
.nav-item.router-link-active {
  color: var(--accent-cyan);
  background: rgba(34,221,255,0.08);
  border-left: 2px solid var(--accent-cyan);
}
.nav-icon { width: 18px; height: 18px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; font-style: normal; }
.nav-icon svg { width: 17px; height: 17px; display: block; }

.home-item { font-weight: 600; color: var(--text-primary); }

.badge {
  margin-left: auto;
  background: var(--accent-red);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  min-width: 18px;
  text-align: center;
}

.sidebar-footer {
  border-top: 1px solid var(--border-color);
  padding: 8px 0;
}
.logout-btn { color: var(--text-muted) !important; }
.logout-btn:hover { color: var(--accent-red) !important; background: rgba(255,71,87,0.05) !important; }
</style>
