import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  { path: '/',        redirect: '/dashboard' },
  { path: '/login',   component: () => import('@/views/Login.vue'),     meta: { public: true } },
  { path: '/dashboard', component: () => import('@/views/Dashboard.vue'),   meta: { title: '数据驾驶舱' } },
  { path: '/diagnosis', component: () => import('@/views/Diagnosis.vue'),  meta: { title: '故障诊断' } },
  { path: '/knowledge', component: () => import('@/views/Knowledge.vue'),  meta: { title: '知识检索' } },
  { path: '/cases/new', component: () => import('@/views/CaseNew.vue'),    meta: { title: '提交案例', role: 'field_worker' } },
  { path: '/cases/my',  component: () => import('@/views/CaseMy.vue'),     meta: { title: '我的案例' } },
  { path: '/documents', component: () => import('@/views/Documents.vue'),  meta: { title: '知识文档' } },
  { path: '/workflow',  component: () => import('@/views/Workflow.vue'),    meta: { title: '作业指引' } },
  { path: '/repair',    component: () => import('@/views/RepairGuide.vue'), meta: { title: '维修执行' } },
  { path: '/audit',     component: () => import('@/views/Audit.vue'),       meta: { title: '审核面板', role: 'admin' } },
  { path: '/profile',   component: () => import('@/views/Profile.vue'),     meta: { title: '个人中心' } },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const store = useUserStore()

  if (to.meta.public) return true

  if (!store.isLoggedIn) return '/login'

  // 懒加载用户信息
  if (!store.userInfo) await store.fetchMe()

  // 角色鉴权
  if (to.meta.role && store.role !== to.meta.role && store.role !== 'admin') {
    return '/diagnosis'
  }

  return true
})

export default router
