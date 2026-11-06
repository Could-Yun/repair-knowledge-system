<template>
  <div class="case-new-page">
    <div class="tech-card form-card">
      <div class="form-title">
        <span class="glow-dot"></span> 提交检修案例
        <span class="form-subtitle">审核通过后自动纳入知识库与知识图谱</span>
      </div>

      <form @submit.prevent="submitCase" class="case-form">
        <!-- 基础信息 -->
        <div class="form-section">
          <div class="section-title"><AppIcon name="clipboard"/> 基础信息</div>
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">案例标题 <span class="required">*</span></label>
              <input v-model="form.title" class="tech-input" placeholder="如：CB125T化油器堵塞导致启动困难" />
            </div>
            <div class="form-group">
              <label class="form-label">设备类型</label>
              <select v-model="form.device_type_id" class="tech-input">
                <option value="">请选择设备类型</option>
                <option v-for="d in deviceTypes" :key="d.id" :value="d.id">{{ d.name }}</option>
              </select>
            </div>
          </div>
        </div>

        <!-- 故障描述 -->
        <div class="form-section">
          <div class="section-title"><AppIcon name="bolt"/> 故障描述</div>
          <div class="form-group">
            <label class="form-label">故障现象 <span class="required">*</span></label>
            <textarea v-model="form.fault_phenomenon" class="tech-input" rows="3" placeholder="详细描述看到/听到/感受到的故障现象..."></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">故障原因分析</label>
            <textarea v-model="form.fault_reason" class="tech-input" rows="3" placeholder="排查后确认的故障根本原因..."></textarea>
          </div>
        </div>

        <!-- 解决方案 -->
        <div class="form-section">
          <div class="section-title"><AppIcon name="check-circle"/> 解决方案</div>
          <div class="form-group">
            <label class="form-label">解决方案 <span class="required">*</span></label>
            <textarea v-model="form.solution" class="tech-input" rows="4" placeholder="步骤化描述解决过程，包含关键操作与注意事项..."></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">使用工具（逗号分隔）</label>
            <input v-model="toolsInput" class="tech-input" placeholder="如：十字螺丝刀, 万用表, 拉马" />
            <div class="tool-tags" v-if="parsedTools.length > 0">
              <span v-for="t in parsedTools" :key="t" class="tech-tag">{{ t }}</span>
            </div>
          </div>
        </div>

        <!-- 图片上传 -->
        <div class="form-section">
          <div class="section-title"><AppIcon name="image"/> 现场图片（最多6张）</div>
          <div class="upload-grid-large">
            <div v-for="(img, idx) in previewImages" :key="idx" class="upload-cell preview-cell">
              <img :src="img" class="cell-img" />
              <button type="button" class="remove-btn" @click="removeImg(idx)"><AppIcon name="x"/></button>
            </div>
            <label v-if="previewImages.length < 6" class="upload-cell add-cell">
              <span class="add-icon"><AppIcon name="camera"/></span>
              <span class="add-text">添加图片</span>
              <input type="file" accept="image/*" multiple style="display:none" @change="addImages" />
            </label>
          </div>
          <div class="upload-hint">JPG/PNG，单张 &lt; 5MB，最多 6 张</div>
        </div>

        <!-- 操作 -->
        <div class="form-actions">
          <button type="button" class="btn-outline" @click="saveDraft"><AppIcon name="note"/> 保存草稿</button>
          <button type="submit" class="btn-primary submit-btn" :disabled="submitting">
            <AppIcon name="rocket"/> {{ submitting ? ' 提交中...' : ' 提交审核' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { casesApi, devicesApi, uploadApi } from '@/api'
import { showToast } from 'vant'
import { useRouter } from 'vue-router'

const router = useRouter()
const form = reactive({
  title: '', device_type_id: '',
  fault_phenomenon: '', fault_reason: '', solution: '',
})
const toolsInput    = ref('')
const imageFiles    = ref([])
const previewImages = ref([])
const submitting    = ref(false)
const deviceTypes   = ref([])

const parsedTools = computed(() =>
  toolsInput.value.split(/[,，]/).map(t => t.trim()).filter(Boolean)
)

devicesApi.list({ page: 1, size: 100 }).then(r => { deviceTypes.value = r.items || [] }).catch(() => {})

function addImages(e) {
  Array.from(e.target.files).forEach(f => {
    if (imageFiles.value.length >= 6) return
    if (f.size > 5 * 1024 * 1024) { showToast('图片超过5MB'); return }
    imageFiles.value.push(f)
    const r2 = new FileReader()
    r2.onload = ev => previewImages.value.push(ev.target.result)
    r2.readAsDataURL(f)
  })
  e.target.value = ''
}

function removeImg(idx) {
  imageFiles.value.splice(idx, 1)
  previewImages.value.splice(idx, 1)
}

function saveDraft() {
  localStorage.setItem('case_draft', JSON.stringify({ ...form, tools: toolsInput.value }))
  showToast({ message: '草稿已保存', type: 'success' })
}

async function submitCase() {
  if (!form.title.trim()) { showToast('请填写案例标题'); return }
  if (!form.fault_phenomenon.trim()) { showToast('请填写故障现象'); return }
  if (!form.solution.trim()) { showToast('请填写解决方案'); return }

  submitting.value = true
  try {
    const fd = new FormData()
    Object.entries(form).forEach(([k, v]) => { if (v) fd.append(k, v) })
    parsedTools.value.forEach(t => fd.append('tools_used', t))
    imageFiles.value.forEach(f => fd.append('images', f))
    await casesApi.create(fd)
    showToast({ message: '案例已提交，等待管理员审核', type: 'success' })
    localStorage.removeItem('case_draft')
    router.push('/cases/my')
  } catch {
    showToast('提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

// 恢复草稿
const draft = localStorage.getItem('case_draft')
if (draft) {
  try {
    const d = JSON.parse(draft)
    Object.assign(form, d)
    toolsInput.value = d.tools || ''
  } catch {}
}
</script>

<style scoped>
.case-new-page { max-width: 900px; margin: 0 auto; }
.form-card { }
.form-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 16px; font-weight: 700; color: var(--text-primary);
  margin-bottom: 24px;
}
.form-subtitle { font-size: 14px; color: var(--text-muted); margin-left: 4px; }

.case-form { display: flex; flex-direction: column; gap: 24px; }
.form-section { }
.section-title {
  font-size: 15px; font-weight: 600; color: var(--accent-cyan);
  padding-bottom: 8px; margin-bottom: 14px;
  border-bottom: 1px solid var(--border-color);
  letter-spacing: 0.04em;
}

.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 600px) { .form-grid { grid-template-columns: 1fr; } }

.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 14px; color: var(--text-secondary); }
.required { color: var(--accent-red); }
.tech-input { font-family: inherit; }

.tool-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }

.upload-grid-large { display: flex; gap: 10px; flex-wrap: wrap; }
.upload-cell {
  width: 100px; height: 100px; border-radius: var(--radius-sm);
  border: 1px dashed var(--border-color);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  position: relative; overflow: hidden; cursor: pointer; transition: all 0.2s;
}
.preview-cell { border-style: solid; }
.add-cell:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.add-icon { font-size: 22px; }
.add-text { font-size: 13px; margin-top: 4px; color: var(--text-muted); }
.cell-img { width: 100%; height: 100%; object-fit: cover; }
.remove-btn {
  position: absolute; top: 3px; right: 3px;
  background: rgba(0,0,0,0.65); color: #fff; border: none;
  border-radius: 50%; width: 18px; height: 18px;
  font-size: 9px; cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.upload-hint { font-size: 13px; color: var(--text-muted); margin-top: 6px; }

.form-actions { display: flex; justify-content: flex-end; gap: 12px; padding-top: 8px; border-top: 1px solid var(--border-color); }
.submit-btn { padding: 10px 32px; }
</style>
