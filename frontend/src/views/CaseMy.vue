<template>
  <div class="case-my-page">
    <!-- 筛选栏 -->
    <div class="filter-bar tech-card">
      <div class="filter-title"><AppIcon name="folder"/> 我的案例</div>
      <div class="filter-options">
        <button
          v-for="opt in statusOpts"
          :key="opt.value"
          class="filter-btn"
          :class="{ active: filterStatus === opt.value }"
          @click="filterStatus = opt.value; loadCases()"
        >
          <span class="glow-dot" :class="opt.dot"></span>
          {{ opt.label }}
        </button>
      </div>
      <router-link to="/cases/new" class="btn-primary new-btn"><AppIcon name="plus"/> 新建案例</router-link>
    </div>

    <!-- 列表 -->
    <div v-if="loading" class="loading-state tech-card">
      <span class="loading-dot">◉</span> 加载中...
    </div>

    <div v-if="!loading && cases.length === 0" class="empty-state tech-card">
      <div class="empty-icon"><AppIcon name="inbox"/></div>
      <div class="empty-title">暂无案例</div>
      <router-link to="/cases/new" class="btn-outline">去提交第一个案例</router-link>
    </div>

    <div class="case-list">
      <div
        v-for="c in cases"
        :key="c.id"
        class="case-item tech-card"
        @click="openCase(c)"
      >
        <div class="ci-header">
          <div class="ci-title">{{ c.title }}</div>
          <div class="ci-status">
            <span class="glow-dot" :class="statusDot(c.status)"></span>
            <span class="status-label" :class="'s-' + c.status">{{ statusLabel(c.status) }}</span>
          </div>
        </div>

        <div class="ci-body">
          <div class="ci-desc">{{ c.fault_phenomenon?.slice(0, 120) }}{{ c.fault_phenomenon?.length > 120 ? '...' : '' }}</div>
        </div>

        <div class="ci-footer">
          <span v-if="c.device_type_name" class="tech-tag">{{ c.device_type_name }}</span>
          <span v-for="tool in (c.tools_used || []).slice(0, 3)" :key="tool" class="tech-tag">{{ tool }}</span>
          <span class="ci-date">{{ formatDate(c.created_at) }}</span>
          <button
            v-if="c.status === 'pending'"
            class="delete-btn"
            @click.stop="deleteCase(c)"
          ><AppIcon name="trash"/></button>
        </div>

        <!-- 审核意见 -->
        <div v-if="c.review_comment && c.status === 'rejected'" class="reject-reason">
          <AppIcon name="warning"/> 拒绝原因：{{ c.review_comment }}
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination" v-if="total > pageSize">
      <button class="btn-outline" :disabled="page <= 1" @click="prevPage">◀ 上一页</button>
      <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
      <button class="btn-outline" :disabled="page >= Math.ceil(total / pageSize)" @click="nextPage">下一页 ▶</button>
    </div>
  </div>
</template>

<script setup>
import { casesApi } from '@/api'
import { showDialog, showToast } from 'vant'

const cases        = ref([])
const loading      = ref(false)
const filterStatus = ref('')
const page         = ref(1)
const pageSize     = 10
const total        = ref(0)

const statusOpts = [
  { value: '',         label: '全部',   dot: '' },
  { value: 'pending',  label: '待审核', dot: 'orange' },
  { value: 'approved', label: '已通过', dot: 'green' },
  { value: 'rejected', label: '已拒绝', dot: 'red' },
]

function statusLabel(s) { return { pending: '待审核', approved: '已通过', rejected: '已拒绝' }[s] || s }
function statusDot(s)   { return { pending: 'orange', approved: 'green',  rejected: 'red'    }[s] || '' }
function formatDate(t)  { return t ? new Date(t).toLocaleDateString('zh-CN') : '' }

async function loadCases() {
  loading.value = true
  try {
    const r = await casesApi.myCases({ status: filterStatus.value || undefined, page: page.value, size: pageSize })
    cases.value = r.items || []
    total.value = r.total || 0
  } catch { showToast('加载失败') } finally { loading.value = false }
}

function openCase(c) {
  // 简单展示（可扩展为详情页）
  showToast(c.title)
}

async function deleteCase(c) {
  await showDialog({ title: '确认删除', message: '删除后不可恢复，确认删除该案例？', confirmButtonText: '确认删除' })
  try {
    await casesApi.delete(c.id)
    showToast({ message: '已删除', type: 'success' })
    loadCases()
  } catch {}
}

function prevPage() { page.value--; loadCases() }
function nextPage() { page.value++; loadCases() }

loadCases()
</script>

<style scoped>
.case-my-page { max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }

.filter-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.filter-title { font-size: 15px; font-weight: 700; color: var(--text-primary); margin-right: 8px; }
.filter-options { display: flex; gap: 6px; flex: 1; }
.filter-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 20px;
  border: 1px solid var(--border-color); background: transparent;
  color: var(--text-secondary); font-size: 14px; cursor: pointer; transition: all 0.2s;
}
.filter-btn.active { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(34,221,255,0.06); }
.new-btn { padding: 6px 16px; font-size: 15px; }

.loading-state {
  padding: 40px; text-align: center; color: var(--accent-cyan); font-size: 16px;
}
.empty-state {
  padding: 60px 20px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px;
}
.empty-icon  { font-size: 36px; opacity: 0.3; }
.empty-title { font-size: 16px; color: var(--text-secondary); }

.case-list { display: flex; flex-direction: column; gap: 12px; }
.case-item { cursor: pointer; transition: all 0.2s; }
.case-item:hover { border-color: var(--border-glow); transform: translateY(-1px); }

.ci-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.ci-title  { font-size: 15px; font-weight: 600; color: var(--text-primary); flex: 1; }
.ci-status { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.status-label { font-size: 14px; font-weight: 600; }
.s-pending  { color: var(--accent-orange); }
.s-approved { color: var(--accent-green); }
.s-rejected { color: var(--accent-red); }

.ci-body { margin-bottom: 10px; }
.ci-desc { font-size: 15px; color: var(--text-secondary); line-height: 1.6; }

.ci-footer {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.ci-date { font-size: 13px; color: var(--text-muted); margin-left: auto; }
.delete-btn {
  background: none; border: none; cursor: pointer; font-size: 16px;
  padding: 2px 6px; border-radius: 4px; transition: background 0.2s;
}
.delete-btn:hover { background: rgba(255,71,87,0.1); }

.reject-reason {
  margin-top: 8px; padding: 8px 10px;
  background: rgba(255,71,87,0.06); border: 1px solid rgba(255,71,87,0.2);
  border-radius: var(--radius-sm); font-size: 14px; color: var(--accent-red);
}

.pagination { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 8px 0; }
.page-info  { font-size: 15px; color: var(--text-secondary); }
</style>
