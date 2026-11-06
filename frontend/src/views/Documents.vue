<template>
  <div class="documents-page">
    <!-- 头部 -->
    <div class="page-header tech-card" style="margin-bottom:20px">
      <div class="header-left">
        <div class="header-icon"><AppIcon name="doc"/></div>
        <div>
          <h2 class="header-title">知识文档</h2>
          <p class="header-desc">上传检修手册等 PDF 文档，审核通过后并入知识库，供诊断与检索调用</p>
        </div>
      </div>
    </div>

    <div class="doc-layout">
      <!-- 左：上传 -->
      <div class="tech-card upload-card">
        <div class="panel-title"><span class="glow-dot"></span> 上传知识文档</div>

        <div class="form-row">
          <label class="form-label">文档标题</label>
          <input v-model="form.title" class="tech-input" placeholder="如：摩托车发动机维修手册（留空则用文件名）" />
        </div>

        <div class="form-row">
          <label class="form-label">所属设备类型（选填）</label>
          <select v-model="form.deviceTypeId" class="tech-input">
            <option value="">不指定</option>
            <option v-for="d in deviceTypes" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>

        <div class="form-row">
          <label class="form-label">PDF 文件 <span class="required">*</span></label>
          <label class="file-drop" :class="{ has: file }">
            <input type="file" accept="application/pdf" style="display:none" @change="onPick" />
            <template v-if="!file">
              <span class="fd-icon"><AppIcon name="up"/></span>
              <span>点击选择 PDF 文件（≤ 50MB）</span>
            </template>
            <template v-else>
              <span class="fd-icon"><AppIcon name="book"/></span>
              <span class="fd-name">{{ file.name }}</span>
              <span class="fd-size">{{ (file.size/1024/1024).toFixed(1) }} MB</span>
            </template>
          </label>
        </div>

        <button class="btn-primary upload-btn" :disabled="!file || uploading" @click="doUpload">
          <span v-if="uploading"><span class="loading-dot">◉</span> 解析上传中…</span>
          <span v-else><AppIcon name="up"/> 上传并提交审核</span>
        </button>

        <!-- 解析结果预览 -->
        <div v-if="lastResult" class="parse-result">
          <div class="pr-head"><AppIcon name="check-circle"/> 已提交审核</div>
          <div class="pr-stat">
            <span class="tech-tag">{{ lastResult.page_count ?? '?' }} 页</span>
            <span class="tech-tag green">{{ lastResult.chunk_count }} 个知识块</span>
            <span class="tech-tag orange">待管理员审核</span>
          </div>
          <div v-if="lastResult.preview?.length" class="pr-preview">
            <div class="pr-preview-title">解析预览：</div>
            <div v-for="(p, i) in lastResult.preview" :key="i" class="pr-chunk">
              <div class="pr-chunk-title">{{ p.title }}</div>
              <div class="pr-chunk-content">{{ p.content }}…</div>
            </div>
          </div>
          <div v-else class="pr-warn"><AppIcon name="warning"/> 未解析出有效内容，管理员可能会拒绝，请确认 PDF 是否为可复制文本。</div>
        </div>
      </div>

      <!-- 右：我的提交 -->
      <div class="tech-card my-card">
        <div class="panel-title"><span class="glow-dot"></span> 我的提交</div>
        <div v-if="myDocs.length === 0" class="empty-hint">暂无提交记录</div>
        <div v-else class="doc-list">
          <div v-for="d in myDocs" :key="d.id" class="doc-item">
            <div class="doc-item-main">
              <div class="doc-item-title">{{ d.title }}</div>
              <div class="doc-item-meta">
                <span class="tech-tag" :class="statusClass(d.status)">{{ statusLabel(d.status) }}</span>
                <span class="doc-sub">{{ d.chunk_count }} 块 · {{ d.page_count ?? '?' }} 页</span>
                <span v-if="d.status==='approved'" class="doc-sub green">已入库 {{ d.ingested_count }} 条</span>
              </div>
              <div v-if="d.review_comment" class="doc-comment">审核意见：{{ d.review_comment }}</div>
            </div>
            <button v-if="d.status==='pending'" class="btn-mini" @click="removeDoc(d)">删除</button>
          </div>
        </div>
        <!-- 提交与审核分离：审核统一在「审核面板」进行（问题 #2） -->
        <div v-if="store.isAdmin" class="admin-hint">
          ℹ 你是管理员：文档审核已统一收到左侧「审核面板 → 知识文档」标签页。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { documentsApi, devicesApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { showToast } from 'vant'

const store = useUserStore()

const form = reactive({ title: '', deviceTypeId: '' })
const file        = ref(null)
const uploading   = ref(false)
const lastResult  = ref(null)
const deviceTypes = ref([])
const myDocs      = ref([])

devicesApi.list({ page: 1, size: 100 }).then(r => { deviceTypes.value = r.items || [] }).catch(() => {})
loadMine()

function statusLabel(s) { return { pending: '待审核', approved: '已通过', rejected: '已拒绝' }[s] || s }
function statusClass(s) { return { pending: 'orange', approved: 'green', rejected: 'red' }[s] || '' }

function onPick(e) {
  const f = e.target.files[0]
  if (!f) return
  if (f.type !== 'application/pdf') { showToast('仅支持 PDF'); return }
  if (f.size > 50 * 1024 * 1024) { showToast('文件超过 50MB'); return }
  file.value = f
  if (!form.title) form.title = f.name.replace(/\.pdf$/i, '')
}

async function doUpload() {
  if (!file.value) return
  uploading.value = true
  lastResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    if (form.title) fd.append('title', form.title)
    if (form.deviceTypeId) fd.append('device_type_id', form.deviceTypeId)
    lastResult.value = await documentsApi.upload(fd)
    showToast({ message: '已提交审核', type: 'success' })
    file.value = null
    form.title = ''
    loadMine()
  } catch (e) {
    showToast('上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

async function loadMine() {
  try { myDocs.value = (await documentsApi.my({ page: 1, size: 50 })).items || [] } catch {}
}

async function removeDoc(d) {
  try { await documentsApi.delete(d.id); showToast('已删除'); loadMine() } catch {}
}
</script>

<style scoped>
.documents-page { max-width: 1400px; margin: 0 auto; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.header-left { display: flex; align-items: center; gap: 14px; }
.header-icon { font-size: 32px; filter: drop-shadow(0 0 8px var(--accent-cyan)); }
.header-title { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.header-desc  { font-size: 14px; color: var(--text-secondary); margin-top: 3px; }

.doc-layout { display: grid; grid-template-columns: 440px 1fr; gap: 20px; margin-bottom: 20px; }
@media (max-width: 1100px) { .doc-layout { grid-template-columns: 1fr; } }

.panel-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 16px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 16px; letter-spacing: 0.04em;
}
.count-badge { margin-left: 8px; background: var(--accent-orange); color: #1c2435; font-size: 13px; font-weight: 700; padding: 1px 8px; border-radius: 10px; }

.form-row { margin-bottom: 14px; }
.form-label { display: block; font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.required { color: var(--accent-red); }

.file-drop {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  border: 1px dashed var(--border-color); border-radius: var(--radius-md);
  padding: 22px; cursor: pointer; color: var(--text-secondary); transition: all 0.2s; text-align: center;
}
.file-drop:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.file-drop.has { border-style: solid; border-color: var(--accent-cyan); }
.fd-icon { font-size: 26px; }
.fd-name { color: var(--text-primary); font-weight: 600; word-break: break-all; }
.fd-size { font-size: 13px; color: var(--text-muted); }

.upload-btn { width: 100%; margin-top: 6px; }

.parse-result { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border-color); }
.pr-head { font-size: 15px; font-weight: 600; color: var(--accent-green); margin-bottom: 10px; }
.pr-stat { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.pr-preview-title { font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.pr-chunk { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 10px; margin-bottom: 8px; }
.pr-chunk-title { font-size: 14px; font-weight: 600; color: var(--accent-cyan); margin-bottom: 4px; }
.pr-chunk-content { font-size: 14px; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap; }
.pr-warn { font-size: 14px; color: var(--accent-orange); }

.empty-hint { color: var(--text-muted); font-size: 15px; padding: 16px 0; text-align: center; }
.doc-list { display: flex; flex-direction: column; gap: 10px; }
.doc-item { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px;
  padding: 12px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); }
.doc-item-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.doc-item-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.doc-sub { font-size: 13px; color: var(--text-muted); }
.doc-sub.green { color: var(--accent-green); }
.doc-comment { font-size: 13px; color: var(--text-secondary); margin-top: 6px; }

.btn-mini { background: transparent; border: 1px solid var(--border-color); color: var(--text-secondary);
  border-radius: var(--radius-sm); padding: 4px 12px; font-size: 14px; cursor: pointer; flex-shrink: 0; }
.btn-mini:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.admin-hint { margin-top: 12px; padding: 10px 12px; font-size: 13px; color: var(--text-secondary);
  background: rgba(34,221,255,0.05); border: 1px dashed var(--border-color); border-radius: var(--radius-sm); }

.admin-card { }
.review-item { padding: 14px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-secondary); }
.review-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.review-actions { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.link { color: var(--accent-cyan); font-size: 14px; text-decoration: none; }
.link:hover { text-decoration: underline; }
.chunks-preview { margin: 12px 0; max-height: 320px; overflow-y: auto; padding: 4px; }
.review-bar { display: flex; gap: 10px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
.review-bar .tech-input { flex: 1; min-width: 200px; }
.btn-sm { padding: 8px 16px; font-size: 15px; flex-shrink: 0; }
</style>
