<template>
  <div class="workflow-page">
    <!-- 未开始状态：选择模板 -->
    <div v-if="!activeRecord" class="template-select">
      <div class="select-header tech-card">
        <div class="sh-icon"><AppIcon name="clipboard"/></div>
        <div class="sh-text">
          <h2 class="sh-title">标准化作业指引</h2>
          <p class="sh-desc">选择已发布的作业流程，按步骤执行、合规留痕；无现成流程可向管理员申请新建</p>
        </div>
        <button class="btn-primary sh-apply" @click="openApply">＋ 申请新作业指引</button>
      </div>

      <div class="filters tech-card">
        <div class="filter-row">
          <div class="filter-group">
            <label class="filter-label">设备类型</label>
            <select v-model="filterDevice" class="tech-input" @change="loadTemplates">
              <option value="">全部设备</option>
              <option v-for="d in deviceTypes" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </div>
          <div class="filter-group">
            <label class="filter-label">检修等级</label>
            <div class="level-btns">
              <button
                v-for="lv in levels"
                :key="lv.value"
                class="level-btn"
                :class="{ active: filterLevel === lv.value }"
                @click="filterLevel = lv.value; loadTemplates()"
              >
                <span><AppIcon :name="lv.icon"/></span>
                <span>{{ lv.label }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 模板列表 -->
      <div v-if="templates.length === 0" class="empty-state tech-card">
        <div class="empty-icon"><AppIcon name="folder-open"/></div>
        <div class="empty-title">暂无作业模板</div>
        <div v-if="isAdmin">
          <button class="btn-primary" @click="showCreate = true"><AppIcon name="plus"/> 创建模板</button>
        </div>
      </div>

      <div class="template-grid">
        <div
          v-for="tpl in templates"
          :key="tpl.id"
          class="tpl-card tech-card"
          @click="startWorkflow(tpl)"
        >
          <div class="tpl-header">
            <div class="tpl-name">{{ tpl.name }}</div>
            <span class="tech-tag" :class="levelClass(tpl.repair_level)">
              {{ levelLabel(tpl.repair_level) }}
            </span>
          </div>
          <div class="tpl-meta">
            <span>{{ tpl.device_type_name || '通用' }}</span>
            <span>{{ (tpl.steps || []).length }} 步骤</span>
            <span v-if="tpl.estimated_duration">约 {{ tpl.estimated_duration }} 分钟</span>
          </div>
          <div class="tpl-steps-preview">
            <div v-for="(s, i) in (tpl.steps || []).slice(0, 3)" :key="i" class="step-preview">
              <span class="sp-num">{{ s.step }}</span>
              <span class="sp-title">{{ s.title }}</span>
            </div>
            <div v-if="(tpl.steps || []).length > 3" class="step-more">
              + {{ tpl.steps.length - 3 }} 步骤
            </div>
          </div>
          <button class="tpl-start-btn btn-primary">▶ 开始作业</button>
        </div>
      </div>

      <!-- 我的作业指引申请 -->
      <div v-if="myReqs.length" class="tech-card myreq-card">
        <div class="myreq-title"><span class="glow-dot"></span> 我的作业指引申请</div>
        <div class="myreq-list">
          <div v-for="r in myReqs" :key="r.id" class="myreq-item">
            <div class="myreq-main">
              <span class="myreq-name">{{ r.title }}</span>
              <span class="tech-tag" :class="reqStatusClass(r.status)">{{ reqStatusLabel(r.status) }}</span>
              <span class="myreq-sub">{{ r.device_type_name || '通用' }} · {{ levelLabel(r.repair_level) }}</span>
            </div>
            <div v-if="r.status === 'published'" class="myreq-hint green"><AppIcon name="check-circle"/> 已发布，可在上方模板列表中找到并执行</div>
            <div v-else-if="r.status === 'rejected'" class="myreq-hint red">已驳回：{{ r.review_comment || '—' }}</div>
            <div v-else class="myreq-hint"><AppIcon name="hourglass"/> 等待管理员审批生成…</div>
          </div>
        </div>
      </div>

      <!-- 作业留痕历史 -->
      <div class="tech-card rec-card">
        <div class="rec-card-head">
          <div class="myreq-title"><span class="glow-dot"></span> {{ recordScope === 'all' ? '全员作业留痕（核查）' : '我的作业记录' }}</div>
          <div class="rec-head-right">
            <div v-if="isAdmin" class="scope-toggle">
              <button class="seg" :class="{ on: recordScope === 'mine' }" @click="setRecordScope('mine')">我的</button>
              <button class="seg" :class="{ on: recordScope === 'all' }" @click="setRecordScope('all')">全部人员</button>
            </div>
            <select v-model="recordStatus" class="tech-input rec-status" @change="loadRecords">
              <option value="">全部状态</option>
              <option value="completed">已完成</option>
              <option value="in_progress">进行中</option>
            </select>
          </div>
        </div>
        <div v-if="recordsLoading" class="rec-empty">加载中…</div>
        <div v-else-if="records.length === 0" class="rec-empty">暂无作业记录（执行一次作业指引后即可在此追溯）</div>
        <div v-else class="rec-list">
          <div v-for="w in records" :key="w.id" class="rec-item" @click="openRecord(w)">
            <div class="rec-main">
              <div class="rec-title">
                {{ w.template_name }}
                <span class="tech-tag" :class="w.status === 'completed' ? 'green' : 'orange'">
                  {{ w.status === 'completed' ? '已完成' : (w.status === 'in_progress' ? '进行中' : w.status) }}
                </span>
              </div>
              <div class="rec-meta">
                <span v-if="recordScope === 'all'" class="tech-tag"><AppIcon name="user"/> {{ w.worker_name || '—' }}</span>
                <span class="tech-tag">{{ w.device_type_name || '通用' }}</span>
                <span class="rec-time"><AppIcon name="clock"/> {{ fmtTime(w.started_at) }}</span>
                <span class="rec-badge">✓ 合规 {{ w.checks_done }}/{{ w.checks_total }}</span>
                <span class="rec-badge"><AppIcon name="camera"/> {{ w.photo_count }} 张</span>
              </div>
            </div>
            <span class="rec-arrow">查看留痕 ›</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 作业执行向导 -->
    <div v-if="activeRecord" class="wizard-view">
      <div class="wizard-header tech-card">
        <button class="back-btn btn-outline" @click="exitWizard">← 退出</button>
        <button v-if="synthSupported" class="voice-btn btn-outline" :class="{ on: voiceOn }" @click="toggleVoice">
          <AppIcon :name="voiceOn ? 'volume-on' : 'volume-off'"/> {{ voiceOn ? ' 语音开' : ' 语音关' }}
        </button>
        <div class="wizard-info">
          <div class="wizard-title">{{ activeTemplate?.name }}
            <span v-if="recordId" class="wo-no">工单 {{ recordId.slice(0, 8) }}</span>
          </div>
          <div class="wizard-progress-text">
            步骤 {{ currentStepIdx + 1 }} / {{ steps.length }}
          </div>
        </div>
        <div class="wizard-progress-bar">
          <div
            class="wizard-progress-fill"
            :style="{ width: ((currentStepIdx + 1) / steps.length * 100) + '%' }"
          ></div>
        </div>
      </div>

      <div class="wizard-body">
        <!-- 左侧步骤列表 -->
        <div class="steps-sidebar">
          <div
            v-for="(s, i) in steps"
            :key="i"
            class="step-item"
            :class="{
              done:    stepDone[i],
              active:  i === currentStepIdx,
              pending: i > currentStepIdx && !stepDone[i]
            }"
            @click="jumpToStep(i)"
          >
            <div class="si-num">{{ stepDone[i] ? '✓' : s.step }}</div>
            <div class="si-title">{{ s.title }}</div>
          </div>
        </div>

        <!-- 右侧当前步骤内容 -->
        <div class="step-content tech-card">
          <div v-if="currentStep" class="step-inner">
            <div class="step-title-row">
              <div class="step-badge">STEP {{ currentStep.step }}</div>
              <div class="step-name">{{ currentStep.title }}</div>
              <span v-if="currentStep.risk" class="risk-tag"><AppIcon name="warning"/> {{ currentStep.risk }}</span>
            </div>

            <div class="step-desc">{{ currentStep.desc }}</div>

            <!-- 工具列表 -->
            <div v-if="currentStep.tools?.length" class="step-tools">
              <div class="tool-label">所需工具：</div>
              <div class="tool-tags">
                <span v-for="t in currentStep.tools" :key="t" class="tech-tag"><AppIcon name="wrench"/> {{ t }}</span>
              </div>
            </div>

            <!-- 安全检查项 -->
            <div v-if="currentStep.checks?.length" class="checks-section">
              <div class="checks-title">安全检查（全部勾选才能继续）</div>
              <div class="checks-list">
                <label
                  v-for="(chk, ci) in currentStep.checks"
                  :key="ci"
                  class="check-item"
                  :class="{ checked: checkedItems[ci] }"
                >
                  <input type="checkbox" v-model="checkedItems[ci]" class="check-box" />
                  <span class="check-label">{{ chk }}</span>
                </label>
              </div>
              <div v-if="!allChecked" class="checks-warning">
                <AppIcon name="warning"/> 必须完成所有安全检查项才能进入下一步
              </div>
            </div>

            <!-- 拍照留证（创新点 D：合规留痕） -->
            <div class="photo-section">
              <div class="photo-label"><AppIcon name="camera"/> 拍照留证（留痕，可多张）</div>
              <div class="photo-grid">
                <div v-for="(url, pi) in (stepPhotos[currentStepIdx] || [])" :key="pi" class="photo-item">
                  <img :src="url" class="photo-img" @click="previewPhoto(url)" />
                  <button class="photo-remove" @click="removeStepPhoto(pi)"><AppIcon name="x"/></button>
                </div>
                <label class="photo-add">
                  <input type="file" accept="image/*" multiple style="display:none" @change="onStepPhoto" />
                  <span v-if="uploadingPhoto"><span class="loading-dot">◉</span></span>
                  <span v-else>＋</span>
                </label>
              </div>
            </div>

            <!-- 备注输入 -->
            <div class="step-note">
              <textarea
                v-model="stepNotes[currentStepIdx]"
                class="tech-input note-input"
                placeholder="记录本步骤备注（可选）..."
                rows="2"
                @blur="persist('in_progress')"
              ></textarea>
            </div>

            <!-- 步骤导航 -->
            <div class="step-nav">
              <button class="btn-outline" :disabled="currentStepIdx === 0" @click="prevStep">◀ 上一步</button>
              <button
                v-if="currentStepIdx < steps.length - 1"
                class="btn-primary"
                :disabled="!canNext"
                @click="nextStep"
              >
                下一步 ▶
              </button>
              <button
                v-else
                class="btn-primary complete-btn"
                :disabled="!canNext"
                @click="completeWorkflow"
              >
                <AppIcon name="flag"/> 完成作业
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 申请新作业指引弹窗 -->
    <van-popup v-model:show="showApply" round :style="{ width: '90%', maxWidth: '520px' }">
      <div class="apply-popup">
        <div class="apply-title">申请新作业指引</div>
        <p class="apply-desc">提交后由管理员审批并用 AI 基于检修手册生成标准流程，发布后即可执行。</p>
        <div class="form-row">
          <label class="form-label">作业任务名 <span class="required">*</span></label>
          <input v-model="applyForm.title" class="tech-input" placeholder="如：化油器定期清洗 / 机油更换保养" />
        </div>
        <div class="form-row">
          <label class="form-label">设备类型</label>
          <select v-model="applyForm.deviceTypeId" class="tech-input">
            <option value="">通用 / 不指定</option>
            <option v-for="d in deviceTypes" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label class="form-label">检修等级</label>
          <select v-model="applyForm.level" class="tech-input">
            <option value="daily">日常保养</option>
            <option value="minor">小修</option>
            <option value="major">大修</option>
            <option value="emergency">急修</option>
          </select>
        </div>
        <div class="form-row">
          <label class="form-label">作业说明（选填）</label>
          <textarea v-model="applyForm.description" class="tech-input" rows="3" placeholder="说明这项作业的目的、范围或特殊要求…"></textarea>
        </div>
        <div class="apply-actions">
          <button class="btn-outline" @click="showApply = false">取消</button>
          <button class="btn-primary" :disabled="applying" @click="submitApply">
            <span v-if="applying"><span class="loading-dot">◉</span> 提交中…</span>
            <span v-else>提交申请</span>
          </button>
        </div>
      </div>
    </van-popup>

    <!-- 作业留痕详情 -->
    <van-popup v-model:show="showRecord" position="right" :style="{ width: '600px', height: '100%', maxWidth: '100vw' }">
      <div class="rec-detail" v-if="curRecord">
        <div class="rec-detail-top">
          <button class="close-btn" @click="showRecord = false"><AppIcon name="x"/> 关闭</button>
          <span class="tech-tag" :class="curRecord.status === 'completed' ? 'green' : 'orange'">
            {{ curRecord.status === 'completed' ? '已完成' : '进行中' }}
          </span>
        </div>
        <div class="rec-detail-scroll">
          <h3 class="rec-detail-title">{{ curRecord.template_name }}</h3>
          <div class="rec-meta-grid">
            <div v-if="curRecord.worker_name"><span>作业人</span>{{ curRecord.worker_name }}</div>
            <div><span>设备</span>{{ curRecord.device_type_name || '通用' }}</div>
            <div><span>开始</span>{{ fmtTime(curRecord.started_at) }}</div>
            <div v-if="curRecord.completed_at"><span>完成</span>{{ fmtTime(curRecord.completed_at) }}</div>
          </div>
          <div v-if="loadingRecord" class="rec-empty">加载中…</div>
          <template v-else>
            <div v-for="(s, i) in curRecordSteps" :key="i" class="ws-step">
              <div class="ws-head">
                <span class="ws-no">{{ s.step || i + 1 }}</span>
                <span class="ws-title">{{ s.title }}</span>
                <span v-if="s.done" class="ws-done">✓ 完成</span>
              </div>
              <div v-if="s.checks && s.checks.length" class="ws-checks">
                <span v-for="(c, ci) in s.checks" :key="ci" class="ws-check" :class="{ ok: c.checked }">
                  {{ c.checked ? '✓' : '✗' }} {{ c.label }}
                </span>
              </div>
              <div v-if="s.note" class="ws-note"><AppIcon name="note"/> {{ s.note }}</div>
              <div v-if="s.photos && s.photos.length" class="ws-photos">
                <img v-for="(p, pi) in s.photos" :key="pi" :src="p" class="ws-photo" @click="previewPhoto(p)" />
              </div>
            </div>
            <div v-if="curRecordSteps.length === 0" class="rec-empty">该记录暂无留痕步骤</div>
          </template>
        </div>
      </div>
    </van-popup>

    <!-- 完成报告弹窗 -->
    <van-popup v-model:show="showReport" round :style="{ width: '90%', maxWidth: '560px' }">
      <div class="report-popup">
        <div class="report-icon"><AppIcon name="flag"/></div>
        <div class="report-title">检修作业完成</div>
        <div class="report-info">
          <div class="ri-row" v-if="recordId">
            <span>工单号</span>
            <span>{{ recordId }}</span>
          </div>
          <div class="ri-row">
            <span>模板</span>
            <span>{{ activeTemplate?.name }}</span>
          </div>
          <div class="ri-row">
            <span>步骤数</span>
            <span>{{ steps.length }} 步（全部完成）</span>
          </div>
          <div class="ri-row">
            <span>合规校验</span>
            <span class="ri-ok">✓ 全部通过</span>
          </div>
          <div class="ri-row">
            <span>拍照留证</span>
            <span>{{ photoCount }} 张</span>
          </div>
          <div class="ri-row">
            <span>完成时间</span>
            <span>{{ new Date().toLocaleString('zh-CN') }}</span>
          </div>
        </div>
        <div class="report-hint" v-if="recordId"><AppIcon name="check-circle"/> 本次作业的合规勾选、备注与照片已留痕入库，可在「个人中心 / 检修记录」追溯。</div>
        <div class="report-hint" v-else><AppIcon name="warning"/> 未连接后端工单，本次作业未留痕（仅本地执行）。</div>
        <div class="report-actions">
          <button class="btn-outline" @click="printWorkOrder"><AppIcon name="printer"/> 打印工单</button>
          <button class="btn-primary" @click="showReport = false; exitWizard()">关闭</button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { workflowApi, devicesApi, uploadApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { useSpeech } from '@/composables/useSpeech'
import { showToast } from 'vant'

const store       = useUserStore()
const isAdmin     = computed(() => store.isAdmin)
const templates   = ref([])
const deviceTypes = ref([])
const filterDevice = ref('')
const filterLevel  = ref('')
const activeRecord   = ref(null)
const recordId       = ref(null)        // 创新点 D：后端检修工单 id（留痕）
const activeTemplate = ref(null)
const currentStepIdx = ref(0)
const stepDone   = ref([])
const stepNotes  = ref([])
const stepPhotos = ref([])              // 每步拍照留证 [[url,...], ...]
const checkedItems = ref([])
const uploadingPhoto = ref(false)
const showReport = ref(false)
const showCreate = ref(false)

// 作业指引申请（一线）
const myReqs    = ref([])
const showApply = ref(false)
const applying  = ref(false)
const applyForm = reactive({ title: '', deviceTypeId: '', level: 'daily', description: '' })
function reqStatusLabel(s) { return { pending: '待审批', published: '已发布', rejected: '已驳回' }[s] || s }
function reqStatusClass(s) { return { pending: 'orange', published: 'green', rejected: 'red' }[s] || '' }
function openApply() {
  applyForm.title = ''; applyForm.deviceTypeId = filterDevice.value || ''
  applyForm.level = 'daily'; applyForm.description = ''
  showApply.value = true
}
async function submitApply() {
  if (!applyForm.title.trim()) { showToast('请填写作业任务名'); return }
  applying.value = true
  try {
    await workflowApi.createRequest({
      title: applyForm.title.trim(),
      repair_level: applyForm.level,
      device_type_id: applyForm.deviceTypeId || null,
      description: applyForm.description.trim() || null,
    })
    showToast({ message: '申请已提交，等待管理员审批', type: 'success' })
    showApply.value = false
    loadMyReqs()
  } catch { showToast('提交失败，请重试') } finally { applying.value = false }
}
async function loadMyReqs() {
  try { myReqs.value = (await workflowApi.myRequests({ page: 1, size: 20 })).items || [] } catch {}
}

// ===== 作业留痕历史（我的 / 管理员可看全部） =====
const records      = ref([])
const recordsLoading = ref(false)
const recordScope  = ref('mine')
const recordStatus = ref('')
const showRecord   = ref(false)
const curRecord    = ref(null)
const curRecordSteps = ref([])
const loadingRecord  = ref(false)
function fmtTime(t) { return t ? new Date(t).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '' }
async function loadRecords() {
  recordsLoading.value = true
  try {
    records.value = (await workflowApi.records({
      scope: recordScope.value, status: recordStatus.value || undefined,
      source: 'workflow', page: 1, size: 50,   // 本页只列标准化作业；排查后维修的工单在「故障诊断」页
    })).items || []
  } catch {} finally { recordsLoading.value = false }
}
function setRecordScope(s) { if (recordScope.value === s) return; recordScope.value = s; loadRecords() }
async function openRecord(w) {
  curRecord.value = w; curRecordSteps.value = []; showRecord.value = true; loadingRecord.value = true
  try {
    const full = await workflowApi.getRecord(w.id)
    curRecord.value = { ...w, ...full }
    curRecordSteps.value = (full.steps_data && full.steps_data.executed) || []
  } catch {} finally { loadingRecord.value = false }
}

// 创新点 C：步骤语音播报
const { synthSupported, speak, cancelSpeak } = useSpeech()
const voiceOn = ref(false)
function speakCurrentStep() {
  const s = currentStep.value
  if (!s) return
  speak(`第${s.step}步，${s.title}。${s.desc || ''}`)
}
function toggleVoice() {
  voiceOn.value = !voiceOn.value
  if (voiceOn.value) speakCurrentStep(); else cancelSpeak()
}

const levels = [
  { value: '',          label: '全部',   icon: 'clipboard' },
  { value: 'daily',     label: '日常',   icon: 'wrench' },
  { value: 'minor',     label: '小修',   icon: 'gear' },
  { value: 'major',     label: '大修',   icon: 'screw' },
  { value: 'emergency', label: '急修',   icon: 'siren' },
]

function levelLabel(v) { return levels.find(l => l.value === v)?.label || v }
function levelClass(v) { return { daily: '', minor: '', major: 'orange', emergency: 'red' }[v] || '' }

const steps       = computed(() => activeTemplate.value?.steps || [])
const currentStep = computed(() => steps.value[currentStepIdx.value])
const allChecked  = computed(() => {
  const chks = currentStep.value?.checks || []
  return chks.length === 0 || chks.every((_, i) => checkedItems.value[i])
})
const canNext = computed(() => allChecked.value)

devicesApi.list({ page: 1, size: 100 }).then(r => { deviceTypes.value = r.items || [] }).catch(() => {})

async function loadTemplates() {
  try {
    const r = await workflowApi.list({ device_type_id: filterDevice.value || undefined, repair_level: filterLevel.value || undefined })
    templates.value = r.items || []
  } catch {}
}

async function startWorkflow(tpl) {
  activeTemplate.value  = tpl
  activeRecord.value    = { id: 'local' }
  currentStepIdx.value  = 0
  const n = tpl.steps?.length || 0
  stepDone.value        = new Array(n).fill(false)
  stepNotes.value       = new Array(n).fill('')
  stepPhotos.value      = Array.from({ length: n }, () => [])
  initChecks()
  // 创新点 D：在后端建检修工单，开始留痕
  recordId.value = null
  try {
    const r = await workflowApi.startRecord({
      workflow_template_id: tpl.id,
      device_type_id: filterDevice.value || tpl.device_type_id || null,
      fault_description: `标准化作业：${tpl.name}`,
    })
    recordId.value = r.id
  } catch { /* 无网/失败时仍可本地执行，但不留痕 */ }
  if (voiceOn.value) speakCurrentStep()
}

function initChecks() {
  const chks = currentStep.value?.checks || []
  checkedItems.value = new Array(chks.length).fill(false)
}

// 创新点 D：汇总当前执行留痕（合规勾选 + 备注 + 照片）
function buildStepsData() {
  const steps = activeTemplate.value?.steps || []
  return {
    template_name: activeTemplate.value?.name,
    current_idx: currentStepIdx.value,
    executed: steps.map((s, i) => ({
      step: s.step, title: s.title,
      done: !!stepDone.value[i],
      checks: (s.checks || []).map((label, ci) => ({
        label, checked: i === currentStepIdx.value ? !!checkedItems.value[ci] : !!stepDone.value[i],
      })),
      note: stepNotes.value[i] || '',
      photos: stepPhotos.value[i] || [],
    })),
  }
}

async function persist(status) {
  if (!recordId.value) return
  try { await workflowApi.updateRecord(recordId.value, { steps_data: buildStepsData(), status }) }
  catch { /* 留痕失败不阻断现场作业 */ }
}

async function onStepPhoto(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  if (!files.length) return
  uploadingPhoto.value = true
  try {
    for (const f of files) {
      if (f.size > 5 * 1024 * 1024) { showToast('图片超过 5MB'); continue }
      const fd = new FormData(); fd.append('file', f)
      const r = await uploadApi.file(fd)
      if (r?.url) stepPhotos.value[currentStepIdx.value].push(r.url)
    }
    persist('in_progress')
  } catch { showToast('上传失败') } finally { uploadingPhoto.value = false }
}
function removeStepPhoto(i) { stepPhotos.value[currentStepIdx.value].splice(i, 1); persist('in_progress') }

function jumpToStep(i) {
  if (i > currentStepIdx.value && !stepDone.value[currentStepIdx.value]) return
  currentStepIdx.value = i
  initChecks()
  if (voiceOn.value) speakCurrentStep()
}

function nextStep() {
  if (!canNext.value) return
  stepDone.value[currentStepIdx.value] = true
  currentStepIdx.value++
  initChecks()
  persist('in_progress')
  if (voiceOn.value) speakCurrentStep()
}

function prevStep() {
  if (currentStepIdx.value === 0) return
  currentStepIdx.value--
  initChecks()
  if (voiceOn.value) speakCurrentStep()
}

async function completeWorkflow() {
  if (!canNext.value) return
  stepDone.value[currentStepIdx.value] = true
  await persist('completed')
  cancelSpeak()
  showReport.value = true
  loadRecords()   // 刷新作业留痕列表
}

function exitWizard() {
  cancelSpeak()
  activeRecord.value   = null
  activeTemplate.value = null
  recordId.value       = null
  showReport.value     = false
}

// 工单完成后：统计留痕概况
const photoCount = computed(() => stepPhotos.value.reduce((s, arr) => s + (arr?.length || 0), 0))
function previewPhoto(url) { window.open(url, '_blank') }
function printWorkOrder() { window.print() }

loadTemplates()
loadMyReqs()
loadRecords()
</script>

<style scoped>
.workflow-page { max-width: 1200px; margin: 0 auto; }

/* 作业留痕历史 */
.rec-card { margin-top: 16px; }
.rec-card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.rec-head-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.scope-toggle { display: flex; }
.seg { padding: 6px 12px; border: 1px solid var(--border-color); background: transparent; color: var(--text-secondary); cursor: pointer; font-size: 13px; }
.seg:first-child { border-radius: var(--radius-sm) 0 0 var(--radius-sm); }
.seg:last-child { border-radius: 0 var(--radius-sm) var(--radius-sm) 0; border-left: none; }
.seg.on { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(34,221,255,0.08); }
.rec-status { width: 120px; }
.rec-empty { padding: 24px; text-align: center; color: var(--text-muted); font-size: 14px; }
.rec-list { display: flex; flex-direction: column; gap: 8px; }
.rec-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s; }
.rec-item:hover { border-color: var(--accent-cyan); background: rgba(34,221,255,0.03); }
.rec-main { flex: 1; min-width: 0; }
.rec-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rec-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rec-time { font-size: 13px; color: var(--text-muted); }
.rec-badge { font-size: 13px; color: var(--text-secondary); border: 1px solid var(--border-color); border-radius: 10px; padding: 0 8px; }
.rec-arrow { font-size: 14px; color: var(--accent-cyan); white-space: nowrap; }

/* 留痕详情抽屉 */
.rec-detail { height: 100%; display: flex; flex-direction: column; background: var(--bg-card); }
.rec-detail-top { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border-color); }
.close-btn { background: none; border: none; color: var(--text-secondary); font-size: 15px; cursor: pointer; }
.rec-detail-scroll { flex: 1; overflow-y: auto; padding: 18px; }
.rec-detail-title { font-size: 16px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }
.rec-meta-grid { display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 14px; font-size: 14px; color: var(--text-primary); }
.rec-meta-grid span { color: var(--text-muted); margin-right: 6px; }
.ws-step { border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; margin-bottom: 10px; background: var(--bg-secondary); }
.ws-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ws-no { width: 22px; height: 22px; border-radius: 50%; background: rgba(34,221,255,0.12); color: var(--accent-cyan); display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
.ws-title { font-size: 15px; font-weight: 600; color: var(--text-primary); flex: 1; }
.ws-done { font-size: 12px; color: var(--accent-green); }
.ws-checks { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.ws-check { font-size: 13px; color: var(--accent-red); }
.ws-check.ok { color: var(--accent-green); }
.ws-note { font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }
.ws-photos { display: flex; gap: 8px; flex-wrap: wrap; }
.ws-photo { width: 86px; height: 86px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-color); cursor: pointer; }

.select-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.sh-icon  { font-size: 28px; }
.sh-text  { flex: 1; }
.sh-title { font-size: 18px; font-weight: 700; }
.sh-desc  { font-size: 14px; color: var(--text-secondary); margin-top: 3px; }
.sh-apply { white-space: nowrap; flex-shrink: 0; }

/* 我的申请 */
.myreq-card { margin-top: 16px; }
.myreq-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
.myreq-list { display: flex; flex-direction: column; gap: 10px; }
.myreq-item { padding: 10px 12px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); }
.myreq-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.myreq-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.myreq-sub  { font-size: 13px; color: var(--text-muted); }
.myreq-hint { font-size: 13px; margin-top: 6px; color: var(--text-secondary); }
.myreq-hint.green { color: var(--accent-green); }
.myreq-hint.red   { color: var(--accent-red); }

/* 申请弹窗 */
.apply-popup { padding: 24px; display: flex; flex-direction: column; gap: 12px; }
.apply-title { font-size: 17px; font-weight: 700; color: var(--text-primary); }
.apply-desc  { font-size: 13px; color: var(--text-muted); margin-top: -4px; }
.apply-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 6px; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 14px; color: var(--text-secondary); }
.required { color: var(--accent-red); }

.filters { margin-bottom: 16px; }
.filter-row { display: flex; gap: 24px; flex-wrap: wrap; }
.filter-group { display: flex; flex-direction: column; gap: 6px; }
.filter-label { font-size: 14px; color: var(--text-secondary); }

.level-btns { display: flex; gap: 6px; }
.level-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent; color: var(--text-secondary);
  font-size: 14px; cursor: pointer; transition: all 0.2s;
}
.level-btn.active { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(34,221,255,0.06); }

.empty-state { padding: 60px 20px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.empty-icon  { font-size: 40px; opacity: 0.3; }
.empty-title { font-size: 16px; color: var(--text-secondary); }

.template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.tpl-card { cursor: pointer; transition: all 0.2s; }
.tpl-card:hover { border-color: var(--border-glow); transform: translateY(-2px); }
.tpl-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.tpl-name   { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.tpl-meta   { display: flex; gap: 12px; font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
.tpl-steps-preview { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.step-preview { display: flex; align-items: center; gap: 8px; }
.sp-num   { width: 20px; height: 20px; border-radius: 50%; background: rgba(34,221,255,0.1); border: 1px solid rgba(34,221,255,0.3); color: var(--accent-cyan); font-size: 13px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.sp-title { font-size: 14px; color: var(--text-secondary); }
.step-more { font-size: 13px; color: var(--text-muted); padding-left: 28px; }
.tpl-start-btn { width: 100%; }

/* 向导视图 */
.wizard-view { display: flex; flex-direction: column; gap: 16px; }
.wizard-header {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap; position: relative; overflow: hidden;
}
.back-btn { white-space: nowrap; }
.wizard-info { flex: 1; }
.wizard-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.wizard-progress-text { font-size: 14px; color: var(--text-secondary); margin-top: 2px; }
.wizard-progress-bar {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 3px; background: var(--border-color);
}
.wizard-progress-fill { height: 100%; background: var(--gradient-btn); border-radius: 1.5px; transition: width 0.4s; }

.wizard-body { display: grid; grid-template-columns: 200px 1fr; gap: 16px; }
@media (max-width: 768px) { .wizard-body { grid-template-columns: 1fr; } }

.steps-sidebar {
  background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: var(--radius-md); padding: 8px; display: flex; flex-direction: column; gap: 2px;
}
.step-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: var(--radius-sm);
  cursor: pointer; transition: all 0.2s;
}
.step-item.done    { color: var(--accent-green); }
.step-item.active  { background: rgba(34,221,255,0.08); color: var(--accent-cyan); }
.step-item.pending { color: var(--text-muted); cursor: default; }
.si-num  { width: 22px; height: 22px; border-radius: 50%; background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
.si-title { font-size: 14px; }

.step-content { }
.step-inner   { display: flex; flex-direction: column; gap: 14px; }
.step-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.step-badge { background: var(--gradient-btn); color: #fff; padding: 2px 10px; border-radius: 20px; font-size: 13px; font-weight: 700; letter-spacing: 0.08em; }
.step-name  { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.risk-tag   { background: rgba(255,71,87,0.1); border: 1px solid rgba(255,71,87,0.3); color: var(--accent-red); padding: 2px 8px; border-radius: 4px; font-size: 14px; }
.step-desc  { font-size: 16px; color: var(--text-secondary); line-height: 1.8; padding: 12px; background: var(--bg-secondary); border-radius: var(--radius-sm); border: 1px solid var(--border-color); }
.step-tools { }
.tool-label { font-size: 14px; color: var(--text-muted); margin-bottom: 6px; }
.tool-tags  { display: flex; gap: 6px; flex-wrap: wrap; }

.checks-section { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px; }
.checks-title   { font-size: 14px; color: var(--text-secondary); margin-bottom: 10px; font-weight: 600; }
.checks-list    { display: flex; flex-direction: column; gap: 8px; }
.check-item {
  display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 6px 10px;
  border-radius: var(--radius-sm); border: 1px solid var(--border-color); transition: all 0.2s;
}
.check-item.checked { border-color: rgba(0,255,157,0.3); background: rgba(0,255,157,0.04); }
.check-box  { accent-color: var(--accent-green); cursor: pointer; }
.check-label { font-size: 15px; color: var(--text-primary); }
.checks-warning { font-size: 14px; color: var(--accent-orange); margin-top: 8px; }

.voice-btn { white-space: nowrap; }
.voice-btn.on { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(34,221,255,0.08); }
.wo-no { margin-left: 8px; font-size: 12px; color: var(--text-muted); font-family: monospace; border: 1px solid var(--border-color); border-radius: 8px; padding: 0 6px; }

/* 创新点 D：拍照留证 */
.photo-section { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; }
.photo-label { font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }
.photo-grid { display: flex; gap: 8px; flex-wrap: wrap; }
.photo-item { position: relative; width: 72px; height: 72px; border-radius: var(--radius-sm); overflow: hidden; border: 1px solid var(--border-color); }
.photo-img { width: 100%; height: 100%; object-fit: cover; cursor: pointer; }
.photo-remove { position: absolute; top: 2px; right: 2px; width: 18px; height: 18px; border: none; border-radius: 50%; background: rgba(0,0,0,0.6); color: #fff; font-size: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.photo-add { width: 72px; height: 72px; border: 1px dashed var(--border-color); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-muted); font-size: 24px; }
.photo-add:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.ri-ok { color: var(--accent-green); }
.report-hint { font-size: 13px; color: var(--text-secondary); text-align: center; line-height: 1.6; }

.note-input { resize: none; font-family: inherit; }
.step-nav   { display: flex; gap: 10px; justify-content: flex-end; }
.complete-btn { background: linear-gradient(135deg, #00b09b, #22ddff); }

/* 报告弹窗 */
.report-popup { padding: 32px 24px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 16px; }
.report-icon  { font-size: 48px; }
.report-title { font-size: 20px; font-weight: 700; color: var(--text-primary); }
.report-info  { width: 100%; display: flex; flex-direction: column; gap: 8px; background: var(--bg-secondary); border-radius: var(--radius-sm); padding: 14px; }
.ri-row       { display: flex; justify-content: space-between; font-size: 15px; color: var(--text-secondary); }
.ri-row span:last-child { color: var(--text-primary); font-weight: 600; }
.report-actions { display: flex; gap: 10px; }
</style>
