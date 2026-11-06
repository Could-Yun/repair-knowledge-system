<template>
  <div class="dashboard-page">
    <!-- 欢迎横幅 -->
    <div class="welcome-banner tech-card">
      <div class="wb-left">
        <div class="wb-icon"><AppIcon name="home"/></div>
        <div>
          <h2 class="wb-title">数据驾驶舱</h2>
          <p class="wb-sub">{{ displayName }}，欢迎回来 · {{ isAdmin ? '管理员' : '一线人员' }} · 设备检修知识检索与作业系统</p>
        </div>
      </div>
      <div class="wb-quick">
        <router-link to="/diagnosis" class="wb-btn"><AppIcon name="bolt"/> 故障诊断</router-link>
        <router-link to="/knowledge" class="wb-btn"><AppIcon name="search"/> 知识检索</router-link>
        <router-link to="/workflow" class="wb-btn"><AppIcon name="clipboard"/> 作业指引</router-link>
      </div>
    </div>

    <!-- 顶部统计卡 -->
    <div class="stats-row">
      <div class="stat-card tech-card" v-for="s in statCards" :key="s.label">
        <div class="sc-icon"><AppIcon :name="s.icon"/></div>
        <div class="sc-content">
          <div class="sc-val">{{ s.value }}</div>
          <div class="sc-label">{{ s.label }}</div>
        </div>
        <div class="sc-trend"
             :class="s.delta === 0 ? 'flat' : (s.up ? 'up' : 'down')"
             :title="s.tip">
          <template v-if="s.delta === 0">— 持平</template>
          <template v-else>{{ s.delta > 0 ? '↑' : '↓' }} {{ Math.abs(s.delta) }}</template>
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="charts-row">
      <!-- 诊断趋势 -->
      <div class="tech-card chart-card">
        <div class="panel-title"><span class="glow-dot"></span> 近7日诊断量</div>
        <div ref="trendChart" class="chart-container"></div>
      </div>
      <!-- 案例状态分布 -->
      <div class="tech-card chart-card">
        <div class="panel-title"><span class="glow-dot"></span> 案例状态分布</div>
        <div ref="pieChart" class="chart-container"></div>
      </div>
    </div>

    <!-- 底部列表 -->
    <div class="lists-row">
      <!-- 管理员：待审核队列 -->
      <div v-if="isAdmin" class="tech-card list-card">
        <div class="panel-title">
          <span class="glow-dot red"></span> 待审核案例
          <router-link to="/audit" class="view-all">查看全部 →</router-link>
        </div>
        <div v-if="pendingCases.length === 0" class="empty-list">暂无待审核案例</div>
        <div v-for="c in pendingCases" :key="c.id" class="list-item">
          <div class="li-title">{{ c.title }}</div>
          <div class="li-meta">
            <span class="tech-tag">{{ c.device_type_name }}</span>
            <span class="li-time">{{ formatTime(c.created_at) }}</span>
          </div>
        </div>
      </div>

      <!-- 一线人员：我的近期诊断 -->
      <div v-else class="tech-card list-card">
        <div class="panel-title">
          <span class="glow-dot"></span> 我的近期诊断
          <router-link to="/diagnosis" class="view-all">去诊断 →</router-link>
        </div>
        <div v-if="myDiagnoses.length === 0" class="empty-list">暂无诊断记录</div>
        <div v-for="d in myDiagnoses" :key="d.id" class="list-item">
          <div class="li-title">{{ (d.fault_description || '').slice(0, 30) }}…</div>
          <div class="li-meta">
            <span class="tech-tag">{{ d.device_type_name || '未知设备' }}</span>
            <span class="li-time">{{ formatTime(d.started_at) }}</span>
          </div>
        </div>
      </div>

      <!-- 最近通过的知识 -->
      <div class="tech-card list-card">
        <div class="panel-title">
          <span class="glow-dot green"></span> 最新知识入库
          <router-link to="/knowledge" class="view-all">检索 →</router-link>
        </div>
        <div v-if="recentKB.length === 0" class="empty-list">暂无数据</div>
        <div v-for="k in recentKB" :key="k.id" class="list-item">
          <div class="li-title">{{ k.title }}</div>
          <div class="li-meta">
            <span class="tech-tag" :class="k.source_type === 'manual' ? 'purple' : ''">
              {{ k.source_type === 'manual' ? '手册' : k.source_type === 'case' ? '案例' : '经验' }}
            </span>
            <span class="li-time">{{ formatTime(k.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { dashboardApi, auditApi, knowledgeApi, diagnosisApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import * as echarts from 'echarts'

const store = useUserStore()
const { isAdmin, displayName } = storeToRefs(store)

const trendChart = ref(null)
const pieChart   = ref(null)
const pendingCases = ref([])
const myDiagnoses  = ref([])
const recentKB     = ref([])

// key 与后端 /api/admin/stats 返回的 deltas 字段名一致，环比数值由接口填充
const statCards = ref([
  { key: 'today_diagnosis', icon: 'bolt',         label: '今日诊断', value: 0, delta: 0, up: true, tip: '较昨日同期诊断量' },
  { key: 'kb_total',        icon: 'folder',       label: '知识条目', value: 0, delta: 0, up: true, tip: '今日新增知识条目' },
  { key: 'approved_cases',  icon: 'check-circle', label: '通过案例', value: 0, delta: 0, up: true, tip: '今日新审核通过的案例' },
  { key: 'pending_cases',   icon: 'hourglass',    label: '待审核',   value: 0, delta: 0, up: true, tip: '较昨日待审积压变化（减少为正面）' },
])

function formatTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
}

onMounted(async () => {
  // 加载统计数据
  try {
    const stats = await dashboardApi.stats()
    statCards.value[0].value = stats.today_diagnosis  || 0
    statCards.value[1].value = stats.kb_total         || 0
    statCards.value[2].value = stats.approved_cases   || 0
    statCards.value[3].value = stats.pending_cases    || 0
    // 环比：与昨日同口径对比，后端已算好差值与正负语义（待审减少视为正面信号）
    const dl = stats.deltas || {}
    statCards.value.forEach(c => {
      const d = dl[c.key]
      if (d) { c.delta = d.value || 0; c.up = !!d.up }
    })
    initTrendChart(stats.trend || [])
    initPieChart(stats.case_status || {})
  } catch { initTrendChart([]); initPieChart({}) }

  // 管理员看待审核队列；一线人员看自己的近期诊断
  if (isAdmin.value) {
    try {
      const r = await auditApi.pending({ page: 1, size: 5 })
      pendingCases.value = r.items || []
    } catch {}
  } else {
    try {
      const r = await diagnosisApi.history({ page: 1, size: 5 })
      myDiagnoses.value = r.items || []
    } catch {}
  }

  // 最新知识
  try {
    const r = await knowledgeApi.search(buildFd(''))
    recentKB.value = (r.items || []).slice(0, 5)
  } catch {}
})

function buildFd(q) {
  const fd = new FormData(); fd.append('query', q || ' '); return fd
}

function initTrendChart(data) {
  const chart = echarts.init(trendChart.value)
  const days  = data.length > 0 ? data.map(d => d.date) : ['周一','周二','周三','周四','周五','周六','周日']
  const vals  = data.length > 0 ? data.map(d => d.count) : [3, 7, 5, 12, 8, 15, 10]
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 20, right: 20, bottom: 30, left: 40 },
    xAxis: { type: 'category', data: days, axisLine: { lineStyle: { color: '#3a496b' } }, axisLabel: { color: '#b8c4d6', fontSize: 13 } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#3a496b' } }, axisLabel: { color: '#b8c4d6', fontSize: 13 }, splitLine: { lineStyle: { color: '#3a496b' } } },
    series: [{
      data: vals, type: 'line', smooth: true,
      lineStyle: { color: '#22ddff', width: 2 },
      itemStyle: { color: '#22ddff' },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(34,221,255,0.3)' },
        { offset: 1, color: 'rgba(34,221,255,0.02)' },
      ]) },
    }],
    tooltip: { trigger: 'axis', backgroundColor: '#28324a', borderColor: '#3a496b', textStyle: { color: '#f1f5f9' } },
  })
}

function initPieChart(status) {
  const chart = echarts.init(pieChart.value)
  chart.setOption({
    backgroundColor: 'transparent',
    legend: { bottom: 0, textStyle: { color: '#b8c4d6', fontSize: 13 } },
    series: [{
      type: 'pie', radius: ['40%', '65%'], center: ['50%', '44%'],
      data: [
        { value: status.approved || 0, name: '已通过',  itemStyle: { color: '#2ee6a8' } },
        { value: status.pending  || 0, name: '待审核',  itemStyle: { color: '#ffab57' } },
        { value: status.rejected || 0, name: '已拒绝',  itemStyle: { color: '#ff5e6c' } },
      ],
      label: { color: '#f1f5f9', fontSize: 13 },
    }],
    tooltip: { trigger: 'item', backgroundColor: '#28324a', borderColor: '#3a496b', textStyle: { color: '#f1f5f9' } },
  })
}
</script>

<style scoped>
.dashboard-page { max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }

.welcome-banner { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.wb-left { display: flex; align-items: center; gap: 14px; }
.wb-icon { font-size: 30px; filter: drop-shadow(0 0 8px var(--accent-cyan)); }
.wb-title { font-size: 19px; font-weight: 700; color: var(--text-primary); }
.wb-sub { font-size: 14px; color: var(--text-secondary); margin-top: 3px; }
.wb-quick { display: flex; gap: 8px; flex-wrap: wrap; }
.wb-btn {
  padding: 7px 14px; border-radius: var(--radius-sm); font-size: 14px; text-decoration: none;
  border: 1px solid var(--border-color); color: var(--text-secondary); transition: all 0.2s;
}
.wb-btn:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(34,221,255,0.06); }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
@media (max-width: 900px) { .stats-row { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 500px) { .stats-row { grid-template-columns: 1fr; } }

.stat-card { display: flex; align-items: center; gap: 14px; }
.sc-icon   { font-size: 28px; }
.sc-content { flex: 1; }
.sc-val    { font-size: 26px; font-weight: 700; color: var(--accent-cyan); font-family: monospace; }
.sc-label  { font-size: 14px; color: var(--text-secondary); margin-top: 2px; }
.sc-trend  { font-size: 14px; font-weight: 600; }
.sc-trend.up   { color: var(--accent-green); }
.sc-trend.down { color: var(--accent-red); }
.sc-trend.flat { color: var(--text-tertiary, #9aa4b2); }

.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .charts-row { grid-template-columns: 1fr; } }
.chart-card { }
.chart-container { height: 220px; }
.panel-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 14px;
}
.view-all { margin-left: auto; font-size: 14px; color: var(--accent-cyan); text-decoration: none; }

.lists-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .lists-row { grid-template-columns: 1fr; } }
.list-card { }
.list-item { padding: 10px 0; border-bottom: 1px solid var(--border-color); }
.list-item:last-child { border-bottom: none; }
.li-title  { font-size: 15px; color: var(--text-primary); margin-bottom: 6px; }
.li-meta   { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
.li-time   { font-size: 13px; color: var(--text-muted); }
.empty-list { font-size: 15px; color: var(--text-muted); padding: 20px 0; text-align: center; }
</style>
