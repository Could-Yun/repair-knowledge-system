<template>
  <div class="audit-page">
    <div class="audit-header tech-card">
      <div class="header-left">
        <span class="glow-dot red"></span>
        <h2 class="header-title">审核中心</h2>
        <span class="header-sub">案例 / 知识文档 / 反馈 / 作业指引申请 统一审核入口</span>
      </div>
    </div>

    <!-- 顶部 Tab（带待审角标） -->
    <div class="audit-tabs tech-card">
      <button class="atab" :class="{ active: tab === 'case' }" @click="tab = 'case'">
        <AppIcon name="folder"/> 案例审核 <span v-if="counts.case" class="tab-badge">{{ counts.case }}</span>
      </button>
      <button class="atab" :class="{ active: tab === 'doc' }" @click="tab = 'doc'">
        <AppIcon name="doc"/> 知识文档审核 <span v-if="counts.doc" class="tab-badge">{{ counts.doc }}</span>
      </button>
      <button class="atab" :class="{ active: tab === 'fb' }" @click="tab = 'fb'">
        <AppIcon name="edit"/> 反馈采纳 <span v-if="counts.fb" class="tab-badge">{{ counts.fb }}</span>
      </button>
      <button class="atab" :class="{ active: tab === 'wf' }" @click="tab = 'wf'">
        <AppIcon name="tools"/> 作业指引申请 <span v-if="counts.wf" class="tab-badge">{{ counts.wf }}</span>
      </button>
    </div>

    <!-- ============ Tab① 案例审核 ============ -->
    <div v-show="tab === 'case'" class="tech-card table-card">
      <div class="table-toolbar">
        <input v-model="keyword" class="tech-input search-kw" placeholder="搜索标题..." @input="loadCases" />
        <select v-model="filterStatus" class="tech-input filter-sel" @change="loadCases">
          <option value="pending">待审核</option>
          <option value="approved">已通过</option>
          <option value="rejected">已拒绝</option>
          <option value="">全部</option>
        </select>
        <button class="btn-outline" :disabled="selected.size === 0" @click="batchApprove">
          <AppIcon name="check-circle"/> 批量通过 ({{ selected.size }})
        </button>
      </div>

      <div v-if="loading" class="loading-state"><span class="loading-dot">◉</span> 加载中...</div>
      <div v-if="!loading && cases.length === 0" class="empty-row">暂无数据</div>

      <div class="audit-list">
        <div v-for="item in cases" :key="item.id" class="audit-row" :class="{ selected: selected.has(item.id) }">
          <input type="checkbox" :checked="selected.has(item.id)" @change="toggleSelect(item.id)" class="row-check" />
          <div class="row-body">
            <div class="row-header">
              <div class="row-title">{{ item.title }}</div>
              <span class="tech-tag" :class="statusTagClass(item.status)">{{ statusLabel(item.status) }}</span>
            </div>
            <div class="row-meta">
              <span v-if="item.device_type_name" class="meta-item"><AppIcon name="monitor"/> {{ item.device_type_name }}</span>
              <span class="meta-item"><AppIcon name="user"/> {{ item.submitter_name }}</span>
              <span class="meta-item"><AppIcon name="clock"/> {{ formatDate(item.created_at) }}</span>
            </div>
            <div class="row-preview">{{ item.fault_phenomenon?.slice(0, 100) }}...</div>
          </div>
          <div class="row-actions">
            <button class="action-btn view" @click="openDetail(item)"><AppIcon name="eye"/> 详情</button>
            <button v-if="item.status === 'pending'" class="action-btn approve" @click="approveCase(item)"><AppIcon name="check-circle"/> 通过</button>
            <button v-if="item.status === 'pending'" class="action-btn reject" @click="openReject(item)"><AppIcon name="x-circle"/> 拒绝</button>
          </div>
        </div>
      </div>

      <div class="pagination" v-if="total > pageSize">
        <button class="btn-outline sm" :disabled="page <= 1" @click="prevPage">◀</button>
        <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
        <button class="btn-outline sm" :disabled="page >= Math.ceil(total / pageSize)" @click="nextPage">▶</button>
      </div>
    </div>

    <!-- ============ Tab② 知识文档审核 ============ -->
    <div v-show="tab === 'doc'" class="tech-card table-card">
      <div class="table-toolbar">
        <select v-model="docStatus" class="tech-input filter-sel" @change="loadDocs">
          <option value="pending">待审核</option>
          <option value="approved">已入库</option>
          <option value="rejected">已拒绝</option>
        </select>
        <span class="toolbar-hint">通过后 PDF 段落块会向量化写入知识库；已入库文档可在此「下架」（含知识库清理）。</span>
      </div>

      <div v-if="docLoading" class="loading-state"><span class="loading-dot">◉</span> 加载中...</div>
      <div v-if="!docLoading && docs.length === 0" class="empty-row">暂无文档</div>

      <div class="audit-list">
        <div v-for="d in docs" :key="d.id" class="review-item">
          <div class="review-head">
            <div>
              <span class="doc-item-title">{{ d.title }}</span>
              <span class="tech-tag" :class="statusTagClass(d.status)" style="margin-left:8px">{{ statusLabel(d.status) }}</span>
              <div class="doc-sub">{{ d.filename }} · {{ d.chunk_count }} 块 · {{ d.page_count ?? '?' }} 页 · 提交人 {{ d.submitter_name || '—' }}
                <span v-if="d.status==='approved'" class="green">· 已入库 {{ d.ingested_count }} 条</span>
              </div>
            </div>
            <div class="review-actions">
              <a class="link" :href="d.file_path" target="_blank">查看原文</a>
              <button class="btn-mini" @click="toggleExpand(d.id)">{{ expanded === d.id ? '收起' : '预览' }}</button>
            </div>
          </div>

          <div v-if="expanded === d.id" class="chunks-preview">
            <div v-if="loadingChunks" class="empty-hint">加载中…</div>
            <template v-else>
              <div v-for="(c, i) in detailChunks" :key="i" class="pr-chunk">
                <div class="pr-chunk-title">{{ c.title }}<span v-if="c.page_start" class="pr-page">P{{ c.page_start }}</span></div>
                <div class="pr-chunk-content">{{ c.content }}</div>
              </div>
            </template>
          </div>

          <!-- 待审核：通过入库 / 拒绝 -->
          <div v-if="d.status === 'pending'" class="review-bar">
            <input v-model="reviewComment[d.id]" class="tech-input" placeholder="审核意见（拒绝时必填）" />
            <button class="btn-primary btn-sm" :disabled="acting === d.id" @click="approveDoc(d)">
              <span v-if="acting === d.id"><span class="loading-dot">◉</span> 正在向量化入库…</span>
              <span v-else>✓ 通过入库</span>
            </button>
            <button class="btn-danger btn-sm" :disabled="acting === d.id" @click="rejectDoc(d)">✗ 拒绝</button>
          </div>
          <!-- 已入库：下架删除（含知识库清理，问题 #1） -->
          <div v-else-if="d.status === 'approved'" class="review-bar">
            <button class="btn-danger btn-sm" :disabled="acting === d.id" @click="deleteDoc(d)">
              <span v-if="acting === d.id"><span class="loading-dot">◉</span> 处理中…</span>
              <span v-else><AppIcon name="trash"/> 下架并从知识库移除</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ Tab③ 反馈采纳 ============ -->
    <div v-show="tab === 'fb'" class="tech-card table-card">
      <div class="toolbar-hint" style="margin-bottom:12px">采纳后的人工修正会在后续诊断中作为「已采纳经验」注入大模型，闭合反馈环。</div>
      <div v-if="fbLoading" class="loading-state"><span class="loading-dot">◉</span> 加载中...</div>
      <div v-if="!fbLoading && feedbacks.length === 0" class="empty-row">暂无待采纳反馈</div>
      <div class="audit-list">
        <div v-for="f in feedbacks" :key="f.id" class="review-item">
          <div class="fb-type">类型：{{ fbTypeLabel(f.correction_type) }} · {{ formatDate(f.created_at) }}</div>
          <div v-if="f.original_output" class="fb-block">
            <div class="fb-label">原始输出</div>
            <div class="fb-text muted">{{ (f.original_output || '').slice(0, 200) }}…</div>
          </div>
          <div class="fb-block">
            <div class="fb-label">人工修正</div>
            <div class="fb-text">{{ f.user_correction }}</div>
          </div>
          <div class="review-bar">
            <button class="btn-primary btn-sm" :disabled="acting === f.id" @click="adoptFb(f)">✓ 采纳并注入诊断</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ Tab④ 作业指引申请 ============ -->
    <div v-show="tab === 'wf'" class="tech-card table-card">
      <div class="table-toolbar">
        <select v-model="wfStatus" class="tech-input filter-sel" @change="loadReqs">
          <option value="pending">待审批</option>
          <option value="published">已发布</option>
          <option value="rejected">已驳回</option>
        </select>
        <span class="toolbar-hint">一线申请新作业指引 → 此处「AI 生成草稿」→ 审核编辑后「发布」为可执行模板（全程留痕）。</span>
      </div>
      <div v-if="wfLoading" class="loading-state"><span class="loading-dot">◉</span> 加载中...</div>
      <div v-if="!wfLoading && reqs.length === 0" class="empty-row">暂无申请</div>
      <div class="audit-list">
        <div v-for="rq in reqs" :key="rq.id" class="review-item">
          <div class="review-head">
            <div>
              <span class="doc-item-title">{{ rq.title }}</span>
              <span class="tech-tag" :class="reqStatusClass(rq.status)" style="margin-left:8px">{{ reqStatusLabel(rq.status) }}</span>
              <div class="doc-sub">{{ rq.device_type_name || '通用' }} · {{ levelLabel(rq.repair_level) }} · 申请人 {{ rq.requester_name || '—' }} · {{ formatDate(rq.created_at) }}</div>
              <div v-if="rq.description" class="req-desc">{{ rq.description }}</div>
            </div>
          </div>
          <div v-if="rq.status === 'pending'" class="review-bar">
            <button class="btn-primary btn-sm" :disabled="acting === rq.id" @click="genDraft(rq)">
              <span v-if="acting === rq.id"><span class="loading-dot">◉</span> AI 生成中…</span>
              <span v-else><AppIcon name="robot"/> AI 生成草稿并编辑</span>
            </button>
            <button class="btn-danger btn-sm" :disabled="acting === rq.id" @click="rejectReq(rq)">✗ 驳回</button>
          </div>
          <div v-else-if="rq.status === 'rejected'" class="doc-sub">驳回意见：{{ rq.review_comment || '—' }}</div>
          <div v-else class="doc-sub green">已发布为作业模板，一线可执行</div>
        </div>
      </div>
    </div>

    <!-- 作业指引草稿编辑 / 发布抽屉 -->
    <van-popup v-model:show="showEditor" position="right" :style="{ width: '640px', height: '100%', maxWidth: '100vw' }">
      <div class="editor-panel" v-if="editReq">
        <div class="detail-topbar">
          <button @click="showEditor = false" class="close-btn"><AppIcon name="x"/> 关闭</button>
          <span class="tech-tag orange">编辑并发布</span>
        </div>
        <div class="editor-scroll">
          <div class="form-row">
            <label class="ed-label">作业指引名称</label>
            <input v-model="draft.name" class="tech-input" placeholder="作业指引名称" />
          </div>
          <div class="ed-row2">
            <div class="form-row">
              <label class="ed-label">检修等级</label>
              <select v-model="draft.repair_level" class="tech-input">
                <option value="daily">日常保养</option>
                <option value="minor">小修</option>
                <option value="major">大修</option>
                <option value="emergency">急修</option>
              </select>
            </div>
            <div class="form-row">
              <label class="ed-label">预计耗时（分钟）</label>
              <input v-model.number="draft.estimated_duration" type="number" class="tech-input" placeholder="如 60" />
            </div>
          </div>

          <div class="ed-steps-head">
            <span>作业步骤（{{ draft.steps.length }}）</span>
            <button class="btn-mini" @click="addStep">＋ 添加步骤</button>
          </div>

          <div v-for="(s, i) in draft.steps" :key="i" class="ed-step">
            <div class="ed-step-top">
              <span class="ed-step-no">STEP {{ i + 1 }}</span>
              <input v-model="s.title" class="tech-input ed-step-title" placeholder="步骤标题" />
              <button class="btn-mini danger" @click="removeStep(i)">删除</button>
            </div>
            <textarea v-model="s.desc" class="tech-input" rows="2" placeholder="操作说明（怎么做）"></textarea>
            <div class="ed-grid">
              <div>
                <label class="ed-sub">合规/安全检查项（每行一条，执行时必须勾选）</label>
                <textarea v-model="s._checks" class="tech-input" rows="2" placeholder="如：已关闭点火开关&#10;已断开蓄电池负极"></textarea>
              </div>
              <div>
                <label class="ed-sub">所需工具（每行一条）</label>
                <textarea v-model="s._tools" class="tech-input" rows="2" placeholder="如：十字螺丝刀&#10;扭力扳手"></textarea>
              </div>
            </div>
            <div class="form-row">
              <label class="ed-sub">本步风险（选填）</label>
              <input v-model="s.risk" class="tech-input" placeholder="如：触电/烫伤" />
            </div>
          </div>
        </div>
        <div class="editor-actions">
          <input v-model="editComment" class="tech-input" placeholder="审核备注（选填）" />
          <button class="btn-primary" :disabled="publishing" @click="publishDraft">
            <span v-if="publishing"><span class="loading-dot">◉</span> 发布中…</span>
            <span v-else><AppIcon name="check-circle"/> 通过并发布</span>
          </button>
        </div>
      </div>
    </van-popup>

    <!-- 案例详情弹窗 -->
    <van-popup v-model:show="showDetail" position="right" :style="{ width: '560px', height: '100%', maxWidth: '100vw' }">
      <div class="detail-panel" v-if="currentItem">
        <div class="detail-topbar">
          <button @click="showDetail = false" class="close-btn"><AppIcon name="x"/> 关闭</button>
          <span class="tech-tag" :class="statusTagClass(currentItem.status)">{{ statusLabel(currentItem.status) }}</span>
        </div>
        <div class="detail-scroll">
          <h3 class="detail-title">{{ currentItem.title }}</h3>
          <div class="detail-section">
            <div class="ds-label">故障现象</div>
            <div class="ds-content">{{ currentItem.fault_phenomenon }}</div>
          </div>
          <div class="detail-section" v-if="currentItem.fault_reason">
            <div class="ds-label">故障原因</div>
            <div class="ds-content">{{ currentItem.fault_reason }}</div>
          </div>
          <div class="detail-section">
            <div class="ds-label">解决方案</div>
            <div class="ds-content">{{ currentItem.solution }}</div>
          </div>
          <div class="detail-section" v-if="currentItem.tools_used?.length">
            <div class="ds-label">使用工具</div>
            <div class="tool-list"><span v-for="t in currentItem.tools_used" :key="t" class="tech-tag">{{ t }}</span></div>
          </div>
          <div class="detail-section" v-if="currentItem.images?.length">
            <div class="ds-label">现场图片</div>
            <div class="img-grid"><img v-for="url in currentItem.images" :key="url" :src="url" class="d-img" @click="previewImg(url)" /></div>
          </div>
        </div>
        <div v-if="currentItem.status === 'pending'" class="detail-actions">
          <textarea v-model="reviewCommentCase" class="tech-input review-comment" placeholder="审核意见（拒绝时必填）..." rows="2"></textarea>
          <div class="action-row">
            <button class="btn-danger" @click="rejectCase(currentItem)"><AppIcon name="x-circle"/> 拒绝</button>
            <button class="btn-primary" @click="approveCase(currentItem)"><AppIcon name="check-circle"/> 通过并入库</button>
          </div>
        </div>
      </div>
    </van-popup>

    <!-- 拒绝弹窗 -->
    <van-popup v-model:show="showReject" round position="bottom" :style="{ height: '40%' }">
      <div class="reject-popup">
        <div class="popup-title">拒绝原因</div>
        <textarea v-model="reviewCommentCase" class="tech-input reject-ta" placeholder="请填写拒绝原因（将展示给提交者）..." rows="4"></textarea>
        <div class="popup-actions">
          <button class="btn-outline" @click="showReject = false">取消</button>
          <button class="btn-danger" @click="confirmReject">确认拒绝</button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { auditApi, documentsApi, feedbackApi, workflowApi } from '@/api'
import { showToast, showDialog } from 'vant'

const tab = ref('case')
const counts = reactive({ case: 0, doc: 0, fb: 0, wf: 0 })

function statusLabel(s)    { return { pending: '待审核', approved: '已通过', rejected: '已拒绝' }[s] || s }
function statusTagClass(s) { return { pending: 'orange', approved: 'green', rejected: 'red' }[s] || '' }
function fbTypeLabel(t)    { return { error: '有误', incomplete: '不完整', optimization: '优化建议' }[t] || t }
function formatDate(t)     { return t ? new Date(t).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '' }
function levelLabel(v)     { return { daily: '日常保养', minor: '小修', major: '大修', emergency: '急修' }[v] || v }
function reqStatusLabel(s) { return { pending: '待审批', published: '已发布', rejected: '已驳回' }[s] || s }
function reqStatusClass(s) { return { pending: 'orange', published: 'green', rejected: 'red' }[s] || '' }

// ---------- 案例审核 ----------
const cases         = ref([])
const loading       = ref(false)
const total         = ref(0)
const page          = ref(1)
const pageSize      = 10
const keyword       = ref('')
const filterStatus  = ref('pending')
const selected      = ref(new Set())
const showDetail    = ref(false)
const showReject    = ref(false)
const currentItem   = ref(null)
const reviewCommentCase = ref('')

async function loadCases() {
  loading.value = true
  selected.value.clear()
  try {
    const r = await auditApi.pending({ page: page.value, size: pageSize, status: filterStatus.value || undefined, keyword: keyword.value || undefined })
    cases.value = r.items || []
    total.value = r.total || 0
  } catch {} finally { loading.value = false }
}
function toggleSelect(id) {
  const s = new Set(selected.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selected.value = s
}
function openDetail(item) { currentItem.value = item; reviewCommentCase.value = ''; showDetail.value = true }
function openReject(item) { currentItem.value = item; reviewCommentCase.value = ''; showReject.value = true }

async function approveCase(item) {
  try {
    await auditApi.approve(item.id, reviewCommentCase.value)
    showToast({ message: '已通过，知识已入库', type: 'success' })
    showDetail.value = false; loadCases(); refreshCounts()
  } catch { showToast('操作失败') }
}
async function rejectCase(item) {
  if (!reviewCommentCase.value.trim()) { showToast('请填写拒绝原因'); return }
  try {
    await auditApi.reject(item.id, reviewCommentCase.value)
    showToast({ message: '已拒绝', type: 'success' })
    showDetail.value = false; showReject.value = false; loadCases(); refreshCounts()
  } catch {}
}
async function confirmReject() { await rejectCase(currentItem.value) }
async function batchApprove() {
  if (selected.value.size === 0) return
  await showDialog({ title: `批量通过 ${selected.value.size} 条案例？`, message: '通过后将自动写入知识库' })
  let ok = 0
  for (const id of [...selected.value]) { try { await auditApi.approve(id, '批量通过'); ok++ } catch {} }
  showToast({ message: `已通过 ${ok} 条`, type: 'success' })
  loadCases(); refreshCounts()
}
function previewImg(url) { window.open(url, '_blank') }
function prevPage() { page.value--; loadCases() }
function nextPage() { page.value++; loadCases() }

// ---------- 文档审核（#2 迁入 + #3 进度反馈 + #1 下架删除）----------
const docs          = ref([])
const docLoading    = ref(false)
const docStatus     = ref('pending')
const expanded      = ref(null)
const detailChunks  = ref([])
const loadingChunks = ref(false)
const reviewComment = reactive({})
const acting        = ref(null)

async function loadDocs() {
  docLoading.value = true
  try { docs.value = (await documentsApi.pending({ page: 1, size: 50, status: docStatus.value })).items || [] }
  catch {} finally { docLoading.value = false }
}
async function toggleExpand(id) {
  if (expanded.value === id) { expanded.value = null; return }
  expanded.value = id; loadingChunks.value = true; detailChunks.value = []
  try { detailChunks.value = ((await documentsApi.detail(id)).chunks || []).slice(0, 30) }
  catch {} finally { loadingChunks.value = false }
}
async function approveDoc(d) {
  acting.value = d.id
  try {
    const r = await documentsApi.approve(d.id, reviewComment[d.id] || '')
    showToast({ message: r.idempotent ? '该文档已入库（无需重复）' : `已入库 ${r.ingested_count} 条知识`, type: 'success' })
    loadDocs(); refreshCounts()
  } catch { showToast('入库失败，请重试') } finally { acting.value = null }
}
async function rejectDoc(d) {
  if (!(reviewComment[d.id] || '').trim()) { showToast('拒绝时请填写意见'); return }
  acting.value = d.id
  try { await documentsApi.reject(d.id, reviewComment[d.id]); showToast('已拒绝'); loadDocs(); refreshCounts() }
  catch {} finally { acting.value = null }
}
async function deleteDoc(d) {
  try {
    await showDialog({ title: '确认下架该知识文档？', message: `将删除文档「${d.title}」，并从知识库移除其入库的 ${d.ingested_count || 0} 条知识，不可恢复。`, showCancelButton: true })
  } catch { return }   // 用户取消
  acting.value = d.id
  try {
    const r = await documentsApi.delete(d.id)
    showToast({ message: `已下架，移除知识 ${r.removed_knowledge ?? 0} 条`, type: 'success' })
    loadDocs()
  } catch { showToast('删除失败') } finally { acting.value = null }
}

// ---------- 反馈采纳 ----------
const feedbacks = ref([])
const fbLoading = ref(false)
async function loadFeedbacks() {
  fbLoading.value = true
  try { feedbacks.value = (await feedbackApi.pending({ page: 1, size: 50 })).items || [] }
  catch {} finally { fbLoading.value = false }
}
async function adoptFb(f) {
  acting.value = f.id
  try { await feedbackApi.adopt(f.id); showToast({ message: '已采纳', type: 'success' }); loadFeedbacks(); refreshCounts() }
  catch {} finally { acting.value = null }
}

// ---------- 作业指引申请：审批 + AI 生成 + 发布 ----------
const reqs        = ref([])
const wfLoading   = ref(false)
const wfStatus    = ref('pending')
const showEditor  = ref(false)
const editReq     = ref(null)
const editComment = ref('')
const publishing  = ref(false)
const draft = reactive({ name: '', repair_level: 'daily', estimated_duration: null, device_type_id: null, steps: [] })

async function loadReqs() {
  wfLoading.value = true
  try { reqs.value = (await workflowApi.listRequests({ page: 1, size: 50, status: wfStatus.value })).items || [] }
  catch {} finally { wfLoading.value = false }
}
async function genDraft(rq) {
  acting.value = rq.id
  try {
    const d = await workflowApi.generateDraft({
      title: rq.title, repair_level: rq.repair_level,
      device_type_id: rq.device_type_id || null, description: rq.description || null,
    })
    editReq.value = rq
    draft.name = rq.title
    draft.repair_level = rq.repair_level
    draft.device_type_id = rq.device_type_id || null
    draft.estimated_duration = d.estimated_duration || null
    // 把 checks/tools 数组转成每行一条的可编辑文本
    draft.steps = (d.steps || []).map(s => ({
      title: s.title || '', desc: s.desc || '', risk: s.risk || '',
      _checks: (s.checks || []).join('\n'), _tools: (s.tools || []).join('\n'),
    }))
    editComment.value = ''
    showEditor.value = true
  } catch { showToast('AI 生成失败，请重试') } finally { acting.value = null }
}
function addStep() { draft.steps.push({ title: '', desc: '', risk: '', _checks: '', _tools: '' }) }
function removeStep(i) { draft.steps.splice(i, 1) }
async function rejectReq(rq) {
  const comment = window.prompt('请填写驳回原因（将展示给申请人）：', '')
  if (comment === null) return
  if (!comment.trim()) { showToast('请填写驳回原因'); return }
  acting.value = rq.id
  try { await workflowApi.rejectRequest(rq.id, comment.trim()); showToast('已驳回'); loadReqs(); refreshCounts() }
  catch {} finally { acting.value = null }
}
function _lines(s) { return (s || '').split('\n').map(x => x.trim()).filter(Boolean) }
async function publishDraft() {
  if (!draft.name.trim()) { showToast('请填写作业指引名称'); return }
  if (!draft.steps.length) { showToast('至少需要一个步骤'); return }
  const steps = draft.steps.map((s, i) => ({
    step: i + 1, title: s.title.trim() || `步骤${i+1}`, desc: s.desc.trim(),
    checks: _lines(s._checks), risk: (s.risk || '').trim(), tools: _lines(s._tools),
  }))
  publishing.value = true
  try {
    await workflowApi.approveRequest(editReq.value.id, {
      name: draft.name.trim(), steps,
      repair_level: draft.repair_level, device_type_id: draft.device_type_id || null,
      estimated_duration: draft.estimated_duration || null, comment: editComment.value.trim(),
    })
    showToast({ message: '已发布为作业模板', type: 'success' })
    showEditor.value = false; loadReqs(); refreshCounts()
  } catch { showToast('发布失败，请重试') } finally { publishing.value = false }
}

// ---------- 待审角标 ----------
async function refreshCounts() {
  try { counts.case = (await auditApi.pending({ page: 1, size: 1, status: 'pending' })).total || 0 } catch {}
  try { counts.doc  = (await documentsApi.pending({ page: 1, size: 1, status: 'pending' })).total || 0 } catch {}
  try { counts.fb   = (await feedbackApi.pending({ page: 1, size: 1 })).total || 0 } catch {}
  try { counts.wf   = (await workflowApi.listRequests({ page: 1, size: 1, status: 'pending' })).total || 0 } catch {}
}

// Tab 切换时懒加载
watch(tab, (t) => {
  if (t === 'doc' && docs.value.length === 0) loadDocs()
  if (t === 'fb'  && feedbacks.value.length === 0) loadFeedbacks()
  if (t === 'wf'  && reqs.value.length === 0) loadReqs()
})

loadCases()
refreshCounts()
</script>

<style scoped>
.audit-page { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }

.audit-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.header-left  { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.header-title { font-size: 16px; font-weight: 700; }
.header-sub   { font-size: 13px; color: var(--text-muted); }

.audit-tabs { display: flex; gap: 8px; flex-wrap: wrap; padding: 8px; }
.atab {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: transparent;
  color: var(--text-secondary); font-size: 15px; cursor: pointer; transition: all 0.2s;
}
.atab:hover  { color: var(--text-primary); }
.atab.active { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(34,221,255,0.08); }
.tab-badge { background: var(--accent-red); color: #fff; font-size: 12px; font-weight: 700; padding: 0 7px; border-radius: 10px; min-width: 18px; text-align: center; }

.table-toolbar { display: flex; gap: 10px; margin-bottom: 14px; align-items: center; flex-wrap: wrap; }
.search-kw  { flex: 1; min-width: 160px; }
.filter-sel { width: 130px; }
.toolbar-hint { font-size: 13px; color: var(--text-muted); }

.loading-state { padding: 40px; text-align: center; color: var(--accent-cyan); }
.empty-row     { padding: 40px; text-align: center; color: var(--text-muted); }

.audit-list { display: flex; flex-direction: column; gap: 8px; }
.audit-row {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); transition: all 0.2s;
}
.audit-row:hover    { border-color: rgba(34,221,255,0.2); background: rgba(34,221,255,0.02); }
.audit-row.selected { border-color: var(--accent-cyan); background: rgba(34,221,255,0.04); }
.row-check { accent-color: var(--accent-cyan); cursor: pointer; }
.row-body  { flex: 1; }
.row-header { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
.row-title  { font-size: 16px; font-weight: 600; color: var(--text-primary); flex: 1; }
.row-meta   { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
.meta-item  { font-size: 13px; color: var(--text-secondary); }
.row-preview { font-size: 14px; color: var(--text-muted); }
.row-actions { display: flex; gap: 6px; flex-direction: column; min-width: 80px; }
.action-btn {
  padding: 5px 10px; border-radius: var(--radius-sm); font-size: 14px;
  border: 1px solid; cursor: pointer; background: transparent; white-space: nowrap; transition: all 0.2s;
}
.action-btn.view    { border-color: var(--border-color); color: var(--text-secondary); }
.action-btn.approve { border-color: rgba(0,255,157,0.4); color: var(--accent-green); }
.action-btn.reject  { border-color: rgba(255,71,87,0.4); color: var(--accent-red); }
.action-btn:hover   { filter: brightness(1.2); background: rgba(255,255,255,0.03); }

.pagination { display: flex; align-items: center; justify-content: center; gap: 12px; padding-top: 14px; border-top: 1px solid var(--border-color); margin-top: 10px; }
.page-info  { font-size: 14px; color: var(--text-secondary); }
.btn-outline.sm { padding: 5px 12px; }

/* 文档审核行 */
.review-item { padding: 14px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-secondary); }
.review-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.review-actions { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.doc-item-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.doc-sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
.doc-sub .green, .green { color: var(--accent-green); }
.link { color: var(--accent-cyan); font-size: 14px; text-decoration: none; }
.link:hover { text-decoration: underline; }
.chunks-preview { margin: 12px 0; max-height: 320px; overflow-y: auto; padding: 4px; }
.pr-chunk { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 10px; margin-bottom: 8px; }
.pr-chunk-title { font-size: 14px; font-weight: 600; color: var(--accent-cyan); margin-bottom: 4px; }
.pr-page { margin-left: 8px; font-size: 12px; color: var(--text-muted); border: 1px solid var(--border-color); border-radius: 8px; padding: 0 6px; }
.pr-chunk-content { font-size: 14px; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap; }
.empty-hint { color: var(--text-muted); font-size: 14px; padding: 12px 0; text-align: center; }
.review-bar { display: flex; gap: 10px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
.review-bar .tech-input { flex: 1; min-width: 200px; }
.btn-sm { padding: 8px 16px; font-size: 15px; flex-shrink: 0; }
.btn-mini { background: transparent; border: 1px solid var(--border-color); color: var(--text-secondary); border-radius: var(--radius-sm); padding: 4px 12px; font-size: 14px; cursor: pointer; }
.btn-mini:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

/* 反馈块 */
.fb-type { font-size: 13px; color: var(--text-muted); margin-bottom: 8px; }
.fb-block { margin-bottom: 8px; }
.fb-label { font-size: 13px; color: var(--text-secondary); margin-bottom: 3px; }
.fb-text  { font-size: 14px; color: var(--text-primary); line-height: 1.6; white-space: pre-wrap; }
.fb-text.muted { color: var(--text-muted); }

/* 详情面板 */
.detail-panel { height: 100%; display: flex; flex-direction: column; background: var(--bg-card); }
.detail-topbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border-color); }
.close-btn { background: none; border: none; color: var(--text-secondary); font-size: 15px; cursor: pointer; }
.detail-scroll { flex: 1; overflow-y: auto; padding: 18px; }
.detail-title  { font-size: 16px; font-weight: 700; color: var(--text-primary); margin-bottom: 16px; }
.detail-section { margin-bottom: 14px; }
.ds-label   { font-size: 13px; color: var(--text-muted); margin-bottom: 4px; letter-spacing: 0.05em; }
.ds-content { font-size: 15px; color: var(--text-secondary); line-height: 1.7; }
.tool-list  { display: flex; gap: 6px; flex-wrap: wrap; }
.img-grid   { display: flex; gap: 8px; flex-wrap: wrap; }
.d-img { width: 120px; height: 90px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-color); cursor: pointer; }
.detail-actions { padding: 14px 18px; border-top: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 8px; }
.review-comment { resize: none; }
.action-row { display: flex; gap: 10px; justify-content: flex-end; }

/* 作业指引申请 + 编辑器 */
.req-desc { font-size: 14px; color: var(--text-secondary); margin-top: 6px; line-height: 1.6; }
.editor-panel { height: 100%; display: flex; flex-direction: column; background: var(--bg-card); }
.editor-scroll { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; }
.ed-label { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; display: block; }
.ed-sub   { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; display: block; }
.ed-row2  { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.ed-steps-head { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 600; color: var(--text-primary); margin-top: 8px; padding-top: 10px; border-top: 1px solid var(--border-color); }
.ed-step { border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; background: var(--bg-secondary); display: flex; flex-direction: column; gap: 8px; }
.ed-step-top { display: flex; align-items: center; gap: 8px; }
.ed-step-no { background: var(--gradient-btn); color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 700; white-space: nowrap; }
.ed-step-title { flex: 1; }
.ed-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.btn-mini.danger { color: var(--accent-red); border-color: rgba(255,71,87,0.4); }
.editor-actions { padding: 14px 18px; border-top: 1px solid var(--border-color); display: flex; gap: 10px; align-items: center; }
.editor-actions .tech-input { flex: 1; }
@media (max-width: 600px) { .ed-grid, .ed-row2 { grid-template-columns: 1fr; } }

.reject-popup { padding: 24px; display: flex; flex-direction: column; gap: 14px; height: 100%; }
.popup-title  { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.reject-ta    { flex: 1; resize: none; }
.popup-actions { display: flex; gap: 10px; justify-content: flex-end; }
</style>
