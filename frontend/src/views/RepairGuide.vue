<template>
  <div class="repair-page">

    <!-- 生成中 -->
    <div v-if="loading" class="tech-card gen-card">
      <div class="gen-icon"><span class="loading-dot">◉</span></div>
      <div class="gen-title">正在依据手册生成维修作业方案…</div>
      <div class="gen-desc">
        系统正在检索《检修手册》中与「{{ shortCause }}」相关的拆装章节与规格数值，
        并据此编排现场可执行的分步作业。
      </div>
      <div class="gen-tip">云端通道约 10～20 秒；断网降级至本地模型时可能需要数分钟，请勿关闭页面。</div>
    </div>

    <!-- 生成失败 -->
    <div v-else-if="error" class="tech-card gen-card">
      <div class="gen-icon err"><AppIcon name="warning"/></div>
      <div class="gen-title">维修方案生成失败</div>
      <div class="gen-desc">{{ error }}</div>
      <div class="gen-actions">
        <button class="btn-outline" @click="goBack">返回诊断</button>
        <button class="btn-primary" @click="fetchPlan">重试</button>
      </div>
    </div>

    <!-- 维修执行向导 -->
    <div v-else-if="steps.length" class="wizard-view">
      <div class="wizard-header tech-card">
        <button class="back-btn btn-outline" @click="goBack">← 退出</button>
        <button v-if="synthSupported" class="voice-btn btn-outline" :class="{ on: voiceOn }" @click="toggleVoice">
          <AppIcon :name="voiceOn ? 'volume-on' : 'volume-off'"/> {{ voiceOn ? ' 语音开' : ' 语音关' }}
        </button>
        <div class="wizard-info">
          <div class="wizard-title">
            {{ plan.plan_title || '现场维修作业' }}
            <span class="src-tag">来自分步排查定论</span>
            <span v-if="recordId" class="wo-no">工单 {{ recordId.slice(0, 8) }}</span>
          </div>
          <div class="wizard-progress-text">
            步骤 {{ currentStepIdx + 1 }} / {{ steps.length }}
            <span v-if="plan.estimated_duration"> · 预计 {{ plan.estimated_duration }} 分钟</span>
          </div>
        </div>
        <div class="wizard-progress-bar">
          <div class="wizard-progress-fill"
               :style="{ width: ((currentStepIdx + 1) / steps.length * 100) + '%' }"></div>
        </div>
      </div>

      <!-- 根本原因回顾 -->
      <div class="cause-card tech-card">
        <div class="cause-label"><AppIcon name="target"/> 已确认的根本原因</div>
        <div class="cause-text">{{ rootCause }}</div>
      </div>

      <div class="wizard-body">
        <!-- 左侧步骤列表 -->
        <div class="steps-sidebar">
          <div
            v-for="(s, i) in steps" :key="i"
            class="step-item"
            :class="{ done: stepDone[i], active: i === currentStepIdx, pending: i > currentStepIdx && !stepDone[i] }"
            @click="jumpToStep(i)"
          >
            <div class="si-num">{{ stepDone[i] ? '✓' : s.step }}</div>
            <div class="si-title">{{ s.title }}</div>
          </div>
        </div>

        <!-- 右侧当前步骤 -->
        <div class="step-content tech-card">
          <div v-if="currentStep" class="step-inner">
            <div class="step-title-row">
              <div class="step-badge">STEP {{ currentStep.step }}</div>
              <div class="step-name">{{ currentStep.title }}</div>
              <span v-if="currentStep.risk" class="risk-tag"><AppIcon name="warning"/> {{ currentStep.risk }}</span>
            </div>

            <div class="step-desc">{{ currentStep.desc }}</div>

            <div v-if="currentStep.tools?.length" class="step-tools">
              <div class="tool-label">所需工具：</div>
              <div class="tool-tags">
                <span v-for="t in currentStep.tools" :key="t" class="tech-tag"><AppIcon name="wrench"/> {{ t }}</span>
              </div>
            </div>

            <div v-if="currentStep.checks?.length" class="checks-section">
              <div class="checks-title">安全与质量确认（全部勾选才能继续）</div>
              <div class="checks-list">
                <label
                  v-for="(chk, ci) in currentStep.checks" :key="ci"
                  class="check-item" :class="{ checked: checkedItems[ci] }"
                >
                  <input type="checkbox" v-model="checkedItems[ci]" class="check-box" />
                  <span class="check-label">{{ chk }}</span>
                </label>
              </div>
              <div v-if="!allChecked" class="checks-warning">
                <AppIcon name="warning"/> 必须完成所有确认项才能进入下一步
              </div>
            </div>

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

            <div class="step-note">
              <textarea
                v-model="stepNotes[currentStepIdx]" class="tech-input note-input"
                placeholder="记录本步骤备注（如实测数值、更换件批号）..." rows="2"
                @blur="persist('in_progress')"
              ></textarea>
            </div>

            <div class="step-nav">
              <button class="btn-outline" :disabled="currentStepIdx === 0" @click="prevStep">◀ 上一步</button>
              <button v-if="currentStepIdx < steps.length - 1" class="btn-primary"
                      :disabled="!canNext" @click="nextStep">下一步 ▶</button>
              <button v-else class="btn-primary complete-btn" :disabled="!canNext" @click="completeRepair">
                <AppIcon name="flag"/> 完成维修
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 完成工单 -->
    <van-popup v-model:show="showReport" round :style="{ width: '90%', maxWidth: '560px' }">
      <div class="report-popup">
        <div class="report-icon"><AppIcon name="flag"/></div>
        <div class="report-title">维修作业完成</div>
        <div class="report-sub">{{ plan.plan_title }}</div>
        <div class="report-grid">
          <div class="rp-row"><span>工单编号</span><b>{{ recordId ? recordId.slice(0, 8).toUpperCase() : '—' }}</b></div>
          <div class="rp-row"><span>根本原因</span><b>{{ shortCause }}</b></div>
          <div class="rp-row"><span>执行步骤</span><b>{{ steps.length }} 步全部完成</b></div>
          <div class="rp-row"><span>合规确认</span><b class="ok">全部确认</b></div>
          <div class="rp-row"><span>留证照片</span><b>{{ totalPhotos }} 张</b></div>
          <div class="rp-row"><span>完成时间</span><b>{{ finishTime }}</b></div>
        </div>
        <div class="report-actions">
          <button class="btn-outline" @click="printReport">打印工单</button>
          <button class="btn-primary" @click="showReport = false; goBack()">完成并返回</button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
// ref / computed / onMounted / onBeforeUnmount / useRouter 由 unplugin-auto-import 自动注入
// AppIcon 已在 main.js 全局注册，无需局部引入（与 Workflow.vue 保持一致）
import { diagnosisApi, workflowApi, uploadApi } from '@/api'
import { useSpeech } from '@/composables/useSpeech'
import { showToast, showImagePreview } from 'vant'

const router = useRouter()
const { synthSupported, speak, cancelSpeak } = useSpeech()

const loading  = ref(true)
const error    = ref('')
const plan     = ref({})
const recordId = ref(null)
const voiceOn  = ref(false)
const showReport = ref(false)
const uploadingPhoto = ref(false)
const finishTime = ref('')

const currentStepIdx = ref(0)
const stepDone     = ref([])
const stepNotes    = ref([])
const stepPhotos   = ref([])
const checkedItems = ref([])

// 由诊断页写入的上下文
const ctx = JSON.parse(sessionStorage.getItem('repair_ctx') || '{}')
const rootCause = computed(() => ctx.root_cause || '')
const shortCause = computed(() => {
  const t = rootCause.value.replace(/^根本原因[:：]\s*/, '')
  return t.length > 28 ? t.slice(0, 28) + '…' : t
})

const steps       = computed(() => plan.value.steps || [])
const currentStep = computed(() => steps.value[currentStepIdx.value])
const allChecked  = computed(() => {
  const chks = currentStep.value?.checks || []
  return chks.length === 0 || chks.every((_, i) => checkedItems.value[i])
})
const canNext = computed(() => allChecked.value)
const totalPhotos = computed(() => stepPhotos.value.reduce((n, a) => n + (a?.length || 0), 0))

onMounted(() => {
  if (!ctx.root_cause) {
    error.value = '缺少排查结论，请先在故障诊断页完成分步排查'
    loading.value = false
    return
  }
  fetchPlan()
})
onBeforeUnmount(() => cancelSpeak())

async function fetchPlan() {
  loading.value = true; error.value = ''
  try {
    const r = await diagnosisApi.repairPlan({
      record_id:         ctx.record_id || null,
      device_type_id:    ctx.device_type_id || null,
      fault_description: ctx.fault_description || '',
      root_cause:        ctx.root_cause,
      history:           ctx.history || [],
    })
    plan.value = r
    const n = r.steps?.length || 0
    currentStepIdx.value = 0
    stepDone.value   = new Array(n).fill(false)
    stepNotes.value  = new Array(n).fill('')
    stepPhotos.value = Array.from({ length: n }, () => [])
    initChecks()
    await startRecord()
    if (voiceOn.value) speakCurrentStep()
  } catch (e) {
    error.value = e?.response?.data?.detail || '生成失败，请检查网络或稍后重试'
  } finally {
    loading.value = false
  }
}

// 复用作业留痕引擎：在 repair_records 建单，来源标记为 diagnosis
async function startRecord() {
  recordId.value = null
  try {
    const r = await workflowApi.startRecord({
      device_type_id:    ctx.device_type_id || null,
      fault_description: `维修作业（来自排查定论）：${shortCause.value}`,
    })
    recordId.value = r.id
  } catch { /* 留痕失败不阻断现场作业 */ }
}

function initChecks() {
  checkedItems.value = new Array(currentStep.value?.checks?.length || 0).fill(false)
}

function buildStepsData() {
  return {
    source: 'diagnosis',
    plan_title: plan.value.plan_title,
    root_cause: rootCause.value,
    current_idx: currentStepIdx.value,
    executed: steps.value.map((s, i) => ({
      step: s.step, title: s.title,
      done: !!stepDone.value[i],
      checks: (s.checks || []).map((label, ci) => ({
        label,
        checked: i === currentStepIdx.value ? !!checkedItems.value[ci] : !!stepDone.value[i],
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
function previewPhoto(url) { showImagePreview([url]) }

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
async function completeRepair() {
  if (!canNext.value) return
  stepDone.value[currentStepIdx.value] = true
  await persist('completed')
  cancelSpeak()
  finishTime.value = new Date().toLocaleString('zh-CN')
  showReport.value = true
}

function speakCurrentStep() {
  const s = currentStep.value
  if (!s) return
  speak(`第${s.step}步，${s.title}。${s.desc}`)
}
function toggleVoice() {
  voiceOn.value = !voiceOn.value
  if (voiceOn.value) speakCurrentStep(); else cancelSpeak()
}
function printReport() { window.print() }

function goBack() {
  cancelSpeak()
  sessionStorage.removeItem('repair_ctx')
  router.push('/diagnosis')
}
</script>

<style scoped>
.repair-page { max-width: 1200px; margin: 0 auto; }

/* 生成中 / 失败 */
.gen-card { padding: 48px 32px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.gen-icon { font-size: 40px; color: var(--accent-cyan); }
.gen-icon.err { color: var(--accent-orange); }
.gen-title { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.gen-desc  { font-size: 15px; color: var(--text-secondary); max-width: 560px; line-height: 1.8; }
.gen-tip   { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
.gen-actions { display: flex; gap: 10px; margin-top: 12px; }

/* 根本原因回顾 */
.cause-card  { padding: 14px 18px; }
.cause-label { font-size: 14px; color: var(--text-muted); margin-bottom: 6px; }
.cause-text  { font-size: 15px; color: var(--text-primary); line-height: 1.8; }

/* 以下与作业执行页保持一致的视觉规范 */
.wizard-view { display: flex; flex-direction: column; gap: 16px; }
.wizard-header { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; position: relative; overflow: hidden; }
.back-btn { white-space: nowrap; }
.wizard-info { flex: 1; }
.wizard-title { font-size: 15px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.src-tag { font-size: 12px; color: var(--accent-cyan); border: 1px solid rgba(34,221,255,0.35); border-radius: 10px; padding: 0 8px; }
.wo-no   { font-size: 12px; color: var(--text-muted); }
.wizard-progress-text { font-size: 14px; color: var(--text-secondary); margin-top: 2px; }
.wizard-progress-bar  { position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: var(--border-color); }
.wizard-progress-fill { height: 100%; background: var(--gradient-btn); border-radius: 1.5px; transition: width 0.4s; }

.wizard-body { display: grid; grid-template-columns: 200px 1fr; gap: 16px; }
@media (max-width: 768px) { .wizard-body { grid-template-columns: 1fr; } }

.steps-sidebar { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 8px; display: flex; flex-direction: column; gap: 2px; }
.step-item { display: flex; align-items: center; gap: 8px; padding: 10px; border-radius: var(--radius-sm); cursor: pointer; color: var(--text-secondary); transition: all 0.2s; }
.step-item.done    { color: var(--accent-green); }
.step-item.active  { background: rgba(34,221,255,0.08); color: var(--accent-cyan); }
.step-item.pending { color: var(--text-muted); cursor: default; }
.si-num   { width: 22px; height: 22px; border-radius: 50%; background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
.si-title { font-size: 14px; }

.step-inner { display: flex; flex-direction: column; gap: 14px; }
.step-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.step-badge { background: var(--gradient-btn); color: #fff; padding: 2px 10px; border-radius: 20px; font-size: 13px; font-weight: 700; letter-spacing: 0.08em; }
.step-name  { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.risk-tag   { background: rgba(255,71,87,0.1); border: 1px solid rgba(255,71,87,0.3); color: var(--accent-red); padding: 2px 8px; border-radius: 4px; font-size: 14px; }
.step-desc  { font-size: 16px; color: var(--text-secondary); line-height: 1.8; padding: 12px; background: var(--bg-secondary); border-radius: var(--radius-sm); border: 1px solid var(--border-color); }
.tool-label { font-size: 14px; color: var(--text-muted); margin-bottom: 6px; }
.tool-tags  { display: flex; gap: 6px; flex-wrap: wrap; }

.checks-section { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px; }
.checks-title   { font-size: 14px; color: var(--text-secondary); margin-bottom: 10px; font-weight: 600; }
.checks-list    { display: flex; flex-direction: column; gap: 8px; }
.check-item     { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s; }
.check-item.checked { border-color: rgba(0,255,157,0.3); background: rgba(0,255,157,0.04); }
.check-box   { accent-color: var(--accent-green); cursor: pointer; }
.check-label { font-size: 15px; color: var(--text-primary); }
.checks-warning { font-size: 14px; color: var(--accent-orange); margin-top: 8px; }

.photo-section { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; }
.photo-label { font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }
.photo-grid  { display: flex; gap: 8px; flex-wrap: wrap; }
.photo-item  { position: relative; width: 72px; height: 72px; border-radius: var(--radius-sm); overflow: hidden; border: 1px solid var(--border-color); }
.photo-img   { width: 100%; height: 100%; object-fit: cover; cursor: pointer; }
.photo-remove{ position: absolute; top: 2px; right: 2px; width: 18px; height: 18px; border: none; border-radius: 50%; background: rgba(0,0,0,0.55); color: #fff; cursor: pointer; font-size: 11px; line-height: 1; }
.photo-add   { width: 72px; height: 72px; border: 1px dashed var(--border-color); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-muted); font-size: 22px; }

.note-input { width: 100%; resize: vertical; }
.step-nav   { display: flex; gap: 10px; justify-content: space-between; margin-top: 4px; }
.complete-btn { min-width: 160px; }

.report-popup { padding: 26px; display: flex; flex-direction: column; align-items: center; gap: 10px; }
.report-icon  { font-size: 34px; color: var(--accent-green); }
.report-title { font-size: 19px; font-weight: 700; color: var(--text-primary); }
.report-sub   { font-size: 14px; color: var(--text-secondary); }
.report-grid  { width: 100%; display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.rp-row { display: flex; justify-content: space-between; gap: 12px; font-size: 15px; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); }
.rp-row span { color: var(--text-muted); }
.rp-row b    { color: var(--text-primary); font-weight: 600; text-align: right; }
.rp-row b.ok { color: var(--accent-green); }
.report-actions { display: flex; gap: 10px; margin-top: 12px; }
</style>
