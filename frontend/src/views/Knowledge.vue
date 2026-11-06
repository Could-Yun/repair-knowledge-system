<template>
  <div class="knowledge-page">
    <!-- 搜索栏 -->
    <div class="search-section tech-card">
      <div class="search-header">
        <div class="search-icon"><AppIcon name="search"/></div>
        <div>
          <h2 class="header-title">知识检索</h2>
          <p class="header-desc">输入故障描述或上传现场图片，智能检索检修手册与历史案例，快速调取检修方案</p>
        </div>
      </div>

      <div class="search-bar">
        <div class="search-input-wrap">
          <span class="search-prefix">&gt;_</span>
          <input
            v-model="query"
            class="tech-input search-input"
            placeholder="输入故障描述，例如：发动机启动困难 / 化油器堵塞 / 冒蓝烟..."
            @keyup.enter="doSearch"
          />
        </div>
        <button class="btn-primary search-btn" :disabled="searching" @click="doSearch">
          <AppIcon name="search"/> {{ searching ? ' 检索中...' : ' 检索' }}
        </button>
      </div>

      <!-- 辅助图片上传 -->
      <div class="search-options">
        <label class="option-item">
          <span class="option-label">辅助图片（可选）</span>
          <label class="upload-mini">
            <span v-if="!queryImage"><AppIcon name="camera"/> 上传故障图</span>
            <span v-else class="img-selected">✓ {{ queryImage.name }}</span>
            <input type="file" accept="image/*" style="display:none" @change="e => queryImage = e.target.files[0]" />
          </label>
          <button v-if="queryImage" @click="queryImage = null" class="clear-img"><AppIcon name="x"/></button>
        </label>

        <label class="option-item">
          <span class="option-label">设备型号过滤</span>
          <input v-model="deviceModel" class="tech-input option-input" placeholder="如: CB125T" />
        </label>

        <label class="option-item">
          <span class="option-label">返回数量</span>
          <select v-model="topK" class="tech-input option-select">
            <option :value="5">5 条</option>
            <option :value="10">10 条</option>
            <option :value="20">20 条</option>
          </select>
        </label>
      </div>

      <!-- 热门检索词 -->
      <div class="hot-tags">
        <span class="hot-label">热门:</span>
        <button
          v-for="tag in hotTags"
          :key="tag"
          class="hot-tag"
          @click="quickSearch(tag)"
        >{{ tag }}</button>
      </div>

      <!-- 我的检索历史 -->
      <div v-if="searchHistory.length" class="hist-row">
        <span class="hist-label"><AppIcon name="clock"/> 最近检索:</span>
        <button
          v-for="h in searchHistory"
          :key="h.id"
          class="hist-chip"
          :title="`${fmtHist(h.created_at)} · 命中 ${h.result_count} 条`"
          @click="quickSearch(h.query)"
        >
          <span v-if="h.has_image" class="hist-img"><AppIcon name="image"/></span>{{ h.query }}
        </button>
      </div>
    </div>

    <!-- 检索结果 -->
    <div class="results-section">
      <!-- 空状态 -->
      <div v-if="!searched && !searching" class="empty-state tech-card">
        <div class="empty-icon"><AppIcon name="book"/></div>
        <div class="empty-title">输入故障描述，开始知识检索</div>
        <div class="empty-desc">知识库包含摩托车发动机维修手册 + 历史审核案例</div>
      </div>

      <!-- 加载中 -->
      <div v-if="searching" class="searching-state tech-card">
        <div class="scan-line"></div>
        <div class="searching-text">
          <span class="loading-dot">◉</span> 向量检索中，融合语义与全文双路径...
        </div>
      </div>

      <!-- 无结果 -->
      <div v-if="searched && !searching && results.length === 0" class="empty-state tech-card">
        <div class="empty-icon"><AppIcon name="help"/></div>
        <div class="empty-title">未找到相关知识</div>
        <div class="empty-desc">尝试调整关键词或去掉设备型号过滤条件</div>
      </div>

      <!-- 结果列表 -->
      <div v-if="results.length > 0" class="results-meta">
        找到 <span class="accent">{{ results.length }}</span> 条相关知识
        <span class="meta-time">（耗时 {{ searchTime }}ms）</span>
      </div>

      <div class="result-list">
        <div
          v-for="(item, idx) in results"
          :key="item.id"
          class="result-item tech-card"
          @click="openDetail(item)"
        >
          <div class="ri-index">{{ String(idx + 1).padStart(2, '0') }}</div>
          <div class="ri-body">
            <div class="ri-header">
              <div class="ri-title">{{ item.title }}</div>
              <div class="ri-tags">
                <span class="tech-tag" :class="sourceTagClass(item.source_type)">
                  {{ sourceTagLabel(item.source_type) }}
                </span>
                <span v-for="tag in (item.tags || []).slice(0, 3)" :key="tag" class="tech-tag">{{ tag }}</span>
              </div>
            </div>
            <div class="ri-content">{{ item.content?.slice(0, 200) }}{{ item.content?.length > 200 ? '...' : '' }}</div>
            <div class="ri-footer">
              <div class="score-wrap">
                <div class="score-bar-bg">
                  <div class="score-bar-fill" :style="{ width: (item.score * 100) + '%' }"></div>
                </div>
                <span class="score-text">匹配度 {{ (item.score * 100).toFixed(1) }}%</span>
              </div>
              <span v-if="item.device_model" class="ri-device">设备: {{ item.device_model }}</span>
              <span class="ri-date">{{ formatDate(item.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <van-popup
      v-model:show="showDetail"
      position="right"
      :style="{ width: '520px', height: '100%', maxWidth: '100vw' }"
    >
      <div class="detail-panel" v-if="currentItem">
        <div class="detail-header">
          <button class="close-btn" @click="showDetail = false"><AppIcon name="x"/></button>
          <div class="detail-title">{{ currentItem.title }}</div>
          <span class="tech-tag" :class="sourceTagClass(currentItem.source_type)">
            {{ sourceTagLabel(currentItem.source_type) }}
          </span>
        </div>
        <div class="detail-body">
          <div class="detail-content">{{ currentItem.content }}</div>
          <div v-if="currentItem.image_urls?.length > 0" class="detail-images">
            <div class="detail-section-title">相关图片</div>
            <div class="image-grid">
              <img v-for="url in currentItem.image_urls" :key="url" :src="url" class="detail-img" />
            </div>
          </div>
        </div>
        <div class="detail-footer">
          <button class="btn-primary" @click="useToDiagnosis">用于诊断</button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { knowledgeApi } from '@/api'
import { useRouter, useRoute } from 'vue-router'
import { showToast } from 'vant'

const router = useRouter()
const route  = useRoute()
const query       = ref('')
const queryImage  = ref(null)
const deviceModel = ref('')
const topK        = ref(5)
const searching   = ref(false)
const searched    = ref(false)
const results     = ref([])
const searchTime  = ref(0)
const showDetail  = ref(false)
const currentItem = ref(null)

const hotTags = ['发动机启动困难', '化油器堵塞', '冒蓝烟', '机油泄漏', '怠速不稳', '离合器打滑', '点火系统故障']

// 我的检索历史
const searchHistory = ref([])
const fmtHist = (t) => t ? new Date(t).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
async function loadSearchHistory() {
  try { searchHistory.value = (await knowledgeApi.history({ page: 1, size: 12 })).items || [] } catch {}
}

function sourceTagClass(t) { return t === 'manual' ? 'purple' : t === 'case' ? 'green' : '' }
function sourceTagLabel(t) { return t === 'manual' ? '手册' : t === 'case' ? '案例' : '经验' }

function quickSearch(tag) { query.value = tag; doSearch() }
function formatDate(t) { return t ? new Date(t).toLocaleDateString('zh-CN') : '' }

// 加载检索历史；并支持 ?q=... 自动填入并检索（兼容旧入口）
onMounted(() => {
  loadSearchHistory()
  const q = route.query.q
  if (q && String(q).trim()) { query.value = String(q); doSearch() }
})

async function doSearch() {
  if (!query.value.trim()) { showToast('请输入检索词'); return }
  searching.value = true
  searched.value  = false
  results.value   = []
  const t0 = Date.now()

  try {
    const fd = new FormData()
    fd.append('query', query.value)
    fd.append('top_k', topK.value)
    if (deviceModel.value) fd.append('device_model', deviceModel.value)
    if (queryImage.value) fd.append('image', queryImage.value)

    const res = await knowledgeApi.search(fd)
    results.value  = res.items || []
    searchTime.value = Date.now() - t0
    searched.value = true
    loadSearchHistory()   // 刷新检索历史
  } catch {
    showToast('检索失败')
  } finally {
    searching.value = false
  }
}

function openDetail(item) {
  currentItem.value = item
  showDetail.value  = true
}

function useToDiagnosis() {
  showDetail.value = false
  router.push({ path: '/diagnosis', query: { q: currentItem.value?.title } })
}
</script>

<style scoped>
.knowledge-page { max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }

.search-section { }
.search-header { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.search-icon   { font-size: 28px; }
.header-title  { font-size: 18px; font-weight: 700; }
.header-desc   { font-size: 14px; color: var(--text-secondary); margin-top: 3px; }

.search-bar { display: flex; gap: 10px; margin-bottom: 14px; }
.search-input-wrap { flex: 1; position: relative; display: flex; align-items: center; }
.search-prefix { position: absolute; left: 12px; color: var(--accent-cyan); font-family: monospace; font-weight: 700; }
.search-input  { padding-left: 36px; font-size: 16px; }
.search-btn    { white-space: nowrap; padding: 10px 20px; }

.search-options { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.option-item    { display: flex; align-items: center; gap: 8px; }
.option-label   { font-size: 14px; color: var(--text-secondary); white-space: nowrap; }
.option-input, .option-select { width: 120px; padding: 6px 10px; font-size: 15px; }
.upload-mini {
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-sm); padding: 6px 12px; font-size: 14px;
  color: var(--text-secondary); cursor: pointer; transition: all 0.2s;
}
.upload-mini:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.img-selected { color: var(--accent-green); }
.clear-img { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; }

.hot-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hot-label { font-size: 13px; color: var(--text-muted); }
.hot-tag {
  background: rgba(34,221,255,0.06); border: 1px solid rgba(34,221,255,0.2);
  color: var(--text-secondary); padding: 3px 10px; border-radius: 20px;
  font-size: 14px; cursor: pointer; transition: all 0.2s;
}
.hot-tag:hover { color: var(--accent-cyan); border-color: var(--accent-cyan); }

.hist-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border-color); }
.hist-label { font-size: 13px; color: var(--text-muted); white-space: nowrap; }
.hist-chip {
  max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  background: transparent; border: 1px solid var(--border-color);
  color: var(--text-secondary); padding: 3px 10px; border-radius: 20px;
  font-size: 13px; cursor: pointer; transition: all 0.2s;
}
.hist-chip:hover { color: var(--accent-cyan); border-color: var(--accent-cyan); }
.hist-img { margin-right: 3px; }

/* 结果 */
.results-section { display: flex; flex-direction: column; gap: 12px; }
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 10px; padding: 60px 20px; text-align: center;
}
.empty-icon  { font-size: 40px; opacity: 0.3; }
.empty-title { font-size: 15px; color: var(--text-secondary); }
.empty-desc  { font-size: 14px; color: var(--text-muted); }

.searching-state {
  padding: 40px; text-align: center; position: relative; overflow: hidden;
}
.searching-text { color: var(--accent-cyan); font-size: 16px; }
.scan-line {
  position: absolute; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
  animation: scan-line 1.5s ease-in-out infinite;
}
@keyframes scan-line {
  0%   { top: 0; }
  100% { top: 100%; }
}

.results-meta { font-size: 15px; color: var(--text-secondary); }
.accent { color: var(--accent-cyan); font-weight: 700; }
.meta-time { color: var(--text-muted); font-size: 13px; }

.result-list { display: flex; flex-direction: column; gap: 12px; }
.result-item {
  display: flex; gap: 16px; cursor: pointer; transition: all 0.2s;
}
.result-item:hover { border-color: var(--border-glow); transform: translateY(-1px); }

.ri-index { font-size: 20px; font-weight: 700; color: var(--accent-cyan); opacity: 0.4; font-family: monospace; min-width: 30px; padding-top: 2px; }
.ri-body  { flex: 1; }
.ri-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.ri-title  { font-size: 15px; font-weight: 600; color: var(--text-primary); flex: 1; }
.ri-tags   { display: flex; gap: 6px; flex-wrap: wrap; }
.ri-content { font-size: 15px; color: var(--text-secondary); line-height: 1.7; margin-bottom: 10px; }
.ri-footer  { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.score-wrap { display: flex; align-items: center; gap: 8px; }
.score-bar-bg   { width: 80px; height: 4px; background: var(--border-color); border-radius: 2px; overflow: hidden; }
.score-bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent-blue), var(--accent-cyan)); border-radius: 2px; transition: width 0.4s; }
.score-text { font-size: 13px; color: var(--accent-cyan); }
.ri-device { font-size: 13px; color: var(--text-muted); }
.ri-date   { font-size: 13px; color: var(--text-muted); margin-left: auto; }

/* 详情面板 */
.detail-panel { height: 100%; display: flex; flex-direction: column; background: var(--bg-card); }
.detail-header {
  padding: 16px 20px; border-bottom: 1px solid var(--border-color);
  display: flex; align-items: center; gap: 10px;
}
.close-btn { background: none; border: none; color: var(--text-muted); font-size: 16px; cursor: pointer; padding: 0 6px 0 0; }
.detail-title { flex: 1; font-size: 15px; font-weight: 600; color: var(--text-primary); }
.detail-body  { flex: 1; overflow-y: auto; padding: 20px; }
.detail-content { font-size: 15px; color: var(--text-secondary); line-height: 1.8; white-space: pre-wrap; }
.detail-section-title { font-size: 14px; color: var(--text-muted); margin: 16px 0 8px; }
.image-grid { display: flex; gap: 8px; flex-wrap: wrap; }
.detail-img { width: 120px; height: 90px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-color); }
.detail-footer { padding: 16px 20px; border-top: 1px solid var(--border-color); }
</style>
