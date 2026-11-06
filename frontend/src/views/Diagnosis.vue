<template>
  <div class="diagnosis-page">
    <!-- 页面头部 -->
    <div class="page-header tech-card" style="margin-bottom:20px">
      <div class="header-left">
        <div class="header-icon"><AppIcon name="bolt"/></div>
        <div>
          <h2 class="header-title">故障智能诊断</h2>
          <p class="header-desc">输入故障描述与现场图片，AI 多模态分析给出诊断报告</p>
        </div>
      </div>
      <div class="header-stats">
        <div class="stat-item">
          <div class="stat-val">{{ stats.today }}</div>
          <div class="stat-label">今日诊断</div>
        </div>
        <div class="stat-item">
          <div class="stat-val">{{ stats.total }}</div>
          <div class="stat-label">累计案例</div>
        </div>
      </div>
    </div>

    <div class="diagnosis-layout">
      <!-- 左：输入面板 -->
      <div class="input-panel">
        <div class="tech-card">
          <div class="panel-title">
            <span class="glow-dot"></span> 故障信息输入
          </div>

          <!-- 设备选择 -->
          <div class="form-row">
            <label class="form-label">设备类型</label>
            <select v-model="form.deviceTypeId" class="tech-input">
              <option value="">选择设备类型</option>
              <option v-for="d in deviceTypes" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
            <div v-if="noKnowledgeDevices" class="field-hint">
              <AppIcon name="warning"/> 知识库暂无任一设备的知识，已回退显示全部设备；诊断将主要依赖大模型。
            </div>
            <div v-else class="field-hint">仅列出知识库中确有知识的设备（诊断以知识库为准）。</div>
          </div>

          <!-- 故障描述 -->
          <div class="form-row">
            <label class="form-label">
              故障描述 <span class="required">*</span>
              <button
                v-if="recognitionSupported"
                type="button" class="mic-btn" :class="{ on: listening }"
                @click="toggleMic" :title="listening ? '点击停止' : '语音输入'"
              ><AppIcon :name="listening ? 'dot' : 'mic'"/> {{ listening ? ' 录音中…点此停止' : ' 语音输入' }}</button>
            </label>
            <textarea
              v-model="form.description"
              class="tech-input desc-textarea"
              placeholder="请详细描述故障现象，例如：发动机启动困难，转动起动机有反应但不发火，已更换火花塞无效..."
              rows="5"
            ></textarea>
            <div class="char-count">{{ form.description.length }} / 1000</div>
          </div>

          <!-- 图片上传 -->
          <div class="form-row">
            <label class="form-label">故障现场图片（选填，最多3张）</label>
            <div class="upload-grid">
              <div
                v-for="(img, idx) in previewImages"
                :key="idx"
                class="upload-item preview-item"
              >
                <img :src="img" class="preview-img" />
                <button class="remove-btn" @click="removeImage(idx)"><AppIcon name="x"/></button>
              </div>
              <label
                v-if="previewImages.length < 3"
                class="upload-item upload-btn"
              >
                <span><AppIcon name="camera"/></span>
                <span style="font-size:13px;margin-top:4px">上传图片</span>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  style="display:none"
                  @change="handleImageUpload"
                />
              </label>
            </div>
            <div class="upload-hint">支持 JPG/PNG，单张 &lt; 5MB</div>
          </div>

          <!-- 提交按钮 -->
          <button
            class="btn-primary analyze-btn"
            :disabled="!form.description || analyzing"
            @click="startAnalysis"
          >
            <span v-if="analyzing">
              <span class="loading-dot">◉</span> AI 分析中...
            </span>
            <span v-else><AppIcon name="bolt"/> 开始智能诊断</span>
          </button>
        </div>

        <!-- 历史记录 -->
        <div class="tech-card history-card" v-if="history.length > 0">
          <div class="panel-title"><span class="glow-dot"></span> 近期诊断</div>
          <div class="history-list">
            <div
              v-for="h in history"
              :key="h.id"
              class="history-item"
              @click="openHistory(h)"
            >
              <div class="history-title">{{ h.fault_description?.slice(0, 40) }}...</div>
              <div class="history-meta">
                <span class="tech-tag">{{ h.device_type_name || '未知设备' }}</span>
                <span class="history-time">{{ formatTime(h.started_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：结果面板 -->
      <div class="result-panel">
        <!-- 等待状态 -->
        <div v-if="!result && !analyzing" class="empty-result tech-card">
          <div class="empty-icon"><AppIcon name="robot"/></div>
          <div class="empty-title">等待诊断输入</div>
          <div class="empty-desc">填写故障描述后点击「开始智能诊断」，AI 将为您生成详细诊断报告</div>
        </div>

        <!-- 分析中动画 -->
        <div v-if="analyzing" class="analyzing-card tech-card">
          <div class="scan-container">
            <div class="scan-ring r1"></div>
            <div class="scan-ring r2"></div>
            <div class="scan-ring r3"></div>
            <div class="scan-center">AI</div>
          </div>
          <div class="analyzing-steps">
            <div v-for="(step, i) in analysisSteps" :key="i" class="analyze-step" :class="{ done: i < currentStep, active: i === currentStep }">
              <span class="step-icon">{{ i < currentStep ? '✓' : i === currentStep ? '◉' : '○' }}</span>
              <span>{{ step }}</span>
            </div>
          </div>
        </div>

        <!-- 诊断结果 -->
        <div v-if="result" class="result-card tech-card">
          <div class="result-header">
            <div class="result-title">
              <span class="glow-dot green"></span>
              <span>诊断报告</span>
              <span class="result-time">{{ new Date().toLocaleString('zh-CN') }}</span>
            </div>
            <div class="result-actions">
              <button class="btn-outline" @click="copyResult"><AppIcon name="clipboard"/> 复制</button>
              <button class="btn-outline" @click="saveAsCase"><AppIcon name="save"/> 存为案例</button>
            </div>
          </div>

          <!-- Markdown 渲染区（[来源N] 可点击溯源，创新点 A） -->
          <div class="result-content" v-html="renderedResult" @click="onAnswerClick"></div>

          <!-- 引用来源（创新点 A：答案可溯源） -->
          <div v-if="citedSources.length" class="cite-section">
            <div class="cite-head"><AppIcon name="pin"/> 诊断依据（点击查看手册/案例原文）</div>
            <div class="cite-list">
              <button
                v-for="s in citedSources" :key="s.id"
                class="cite-chip" @click="openSource(s)"
              >
                <span class="cite-no">[{{ s.ref_no }}]</span>
                <span class="cite-title">{{ s.title }}</span>
                <span v-if="s.page_no" class="cite-page">手册 P{{ s.page_no }}</span>
                <span class="cite-src">{{ s.source_type === 'manual' ? '手册' : (s.source_type === 'case' ? '案例' : '知识') }}</span>
              </button>
            </div>
          </div>

          <!-- 知识图谱推理子图（创新点 B：GraphRAG）-->
          <!-- 用 v-if 而不是 v-show：v-show 隐藏时容器 0×0，echarts 拿不到尺寸画不出来 -->
          <div v-if="result.kg_graph && result.kg_graph.entities && result.kg_graph.entities.length" class="kg-section">
            <div class="kg-head"><AppIcon name="web"/> 知识图谱关联推理（症状 → 原因 → 处置）</div>
            <div class="kg-tip">蓝色大圈＝本次故障命中的关键词；其余圆点＝相关实体（按颜色分类，见下方图例）；连线上的文字＝实体间关系（如"由…引起""可通过…解决"）。可拖动节点、滚轮缩放查看。</div>
            <div ref="kgChartRef" class="kg-chart"></div>
            <div class="kg-legend">
              <span><i style="background:#ff6b81"></i>症状</span>
              <span><i style="background:#ffa94d"></i>原因</span>
              <span><i style="background:#2ee6a8"></i>处置</span>
              <span><i style="background:#22ddff"></i>工具</span>
              <span><i style="background:#7c8aa3"></i>部件</span>
            </div>
          </div>

          <!-- 分步检修指引入口 -->
          <div class="guide-cta">
            <div class="guide-cta-text">
              <span class="guide-cta-icon"><AppIcon name="compass"/></span>
              <div>
                <div class="guide-cta-title">按步骤检修指引</div>
                <div class="guide-cta-desc">系统逐步给出检查点，你边修边反馈，自动排除并锁定根因</div>
              </div>
            </div>
            <button class="btn-primary" @click="startGuide">开始指引</button>
          </div>

          <!-- 相关案例 -->
          <div v-if="result.sources?.length > 0" class="related-cases">
            <div class="related-title"><AppIcon name="book"/> 相关历史案例</div>
            <div class="case-cards">
              <div
                v-for="src in result.sources"
                :key="src.id"
                class="case-card"
              >
                <div class="case-score">
                  <div class="score-bar" :style="{ width: (src.score * 100) + '%' }"></div>
                  <span>{{ (src.score * 100).toFixed(0) }}% 匹配</span>
                </div>
                <div class="case-title">{{ src.title }}</div>
                <div class="case-content">{{ src.content?.slice(0, 100) }}...</div>
              </div>
            </div>
          </div>

          <!-- 反馈区 -->
          <div class="feedback-bar">
            <span class="feedback-label">诊断结果是否准确？</span>
            <button @click="openFeedback('error')" class="fb-btn red"><AppIcon name="x-circle"/> 有误</button>
            <button @click="openFeedback('incomplete')" class="fb-btn orange"><AppIcon name="warning"/> 不完整</button>
            <button @click="openFeedback('optimization')" class="fb-btn green"><AppIcon name="edit"/> 优化建议</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 维修工单留痕（排查定论后的现场维修，与「作业指引」的标准化作业分开管理） -->
    <div class="tech-card rp-card">
      <div class="rp-head">
        <div class="panel-title">
          <span class="glow-dot"></span>
          {{ rpScope === 'all' ? '全员维修工单（核查）' : '我的维修工单' }}
        </div>
        <div class="rp-head-right">
          <div v-if="isAdmin" class="rp-seg">
            <button class="seg" :class="{ on: rpScope === 'mine' }" @click="setRpScope('mine')">我的</button>
            <button class="seg" :class="{ on: rpScope === 'all' }"  @click="setRpScope('all')">全部人员</button>
          </div>
          <select v-model="rpStatus" class="tech-input rp-status" @change="loadRepairRecords">
            <option value="">全部状态</option>
            <option value="completed">已完成</option>
            <option value="in_progress">进行中</option>
          </select>
        </div>
      </div>
      <div class="rp-hint">
        由分步排查定论后的「开始维修」产生，依据根本原因即时生成、不入模板库；
        标准化作业（保养/清洗/巡检）的执行留痕请见「作业指引」页。
      </div>

      <div v-if="rpLoading" class="rp-empty">加载中…</div>
      <div v-else-if="repairRecords.length === 0" class="rp-empty">
        暂无维修工单（在分步排查得到结论后点「开始维修」，执行过程会自动留痕）
      </div>
      <div v-else class="rp-list">
        <div v-for="r in repairRecords" :key="r.id" class="rp-item" @click="openRepairRecord(r)">
          <div class="rp-main">
            <div class="rp-title">
              <span class="rp-name">{{ r.template_name }}</span>
              <span class="tech-tag" :class="r.status === 'completed' ? 'green' : 'orange'">
                {{ r.status === 'completed' ? '已完成' : (r.status === 'in_progress' ? '进行中' : r.status) }}
              </span>
            </div>
            <div v-if="r.root_cause" class="rp-cause"><AppIcon name="target"/> {{ r.root_cause }}</div>
            <div class="rp-meta">
              <span v-if="rpScope === 'all'" class="tech-tag"><AppIcon name="user"/> {{ r.worker_name || '—' }}</span>
              <span class="tech-tag">{{ r.device_type_name || '通用' }}</span>
              <span class="rp-time"><AppIcon name="clock"/> {{ formatTime(r.started_at) }}</span>
              <span class="rp-badge">✓ 合规 {{ r.checks_done }}/{{ r.checks_total }}</span>
              <span class="rp-badge"><AppIcon name="camera"/> {{ r.photo_count }} 张</span>
            </div>
          </div>
          <span class="rp-arrow">查看留痕 ›</span>
        </div>
      </div>
    </div>

    <!-- 维修工单留痕详情 -->
    <van-popup v-model:show="showRpDetail" position="right" :style="{ width: '600px', height: '100%', maxWidth: '100vw' }">
      <div class="rp-detail" v-if="curRp">
        <div class="rp-detail-top">
          <button class="close-btn" @click="showRpDetail = false"><AppIcon name="x"/> 关闭</button>
          <span class="tech-tag" :class="curRp.status === 'completed' ? 'green' : 'orange'">
            {{ curRp.status === 'completed' ? '已完成' : '进行中' }}
          </span>
        </div>
        <div class="rp-detail-scroll">
          <h3 class="rp-detail-title">{{ curRp.template_name }}</h3>
          <div v-if="curRpCause" class="rp-cause-box">
            <span>已确认的根本原因</span>{{ curRpCause }}
          </div>
          <div class="rp-meta-grid">
            <div v-if="curRp.worker_name"><span>维修人</span>{{ curRp.worker_name }}</div>
            <div><span>设备</span>{{ curRp.device_type_name || '通用' }}</div>
            <div><span>开始</span>{{ formatTime(curRp.started_at) }}</div>
            <div v-if="curRp.completed_at"><span>完成</span>{{ formatTime(curRp.completed_at) }}</div>
          </div>
          <div v-if="rpDetailLoading" class="rp-empty">加载中…</div>
          <template v-else>
            <div v-for="(st, i) in curRpSteps" :key="i" class="rps-step">
              <div class="rps-head">
                <span class="rps-no">{{ st.step || i + 1 }}</span>
                <span class="rps-title">{{ st.title }}</span>
                <span v-if="st.done" class="rps-done">✓ 完成</span>
              </div>
              <div v-if="st.checks && st.checks.length" class="rps-checks">
                <span v-for="(c, ci) in st.checks" :key="ci" class="rps-check" :class="{ ok: c.checked }">
                  {{ c.checked ? '✓' : '✗' }} {{ c.label }}
                </span>
              </div>
              <div v-if="st.note" class="rps-note"><AppIcon name="note"/> {{ st.note }}</div>
              <div v-if="st.photos && st.photos.length" class="rps-photos">
                <img v-for="(ph, pi) in st.photos" :key="pi" :src="ph" class="rps-photo" @click="previewRpPhoto(ph)" />
              </div>
            </div>
            <div v-if="curRpSteps.length === 0" class="rp-empty">该工单暂无留痕步骤</div>
          </template>
        </div>
      </div>
    </van-popup>

    <!-- 分步检修指引弹窗（右侧大抽屉，可拖左边缘调宽） -->
    <van-popup
      v-model:show="guideShow"
      position="right"
      class="guide-modal"
      :style="{ width: guideWidth + 'px', maxWidth: '100vw', height: '100%' }"
    >
      <div class="guide-popup">
        <!-- 左边缘拖拽手柄：向左拖动变大 -->
        <div class="guide-resizer" @mousedown.prevent="startGuideResize" title="拖动调整宽度"></div>
        <div class="guide-header">
          <div class="guide-h-title"><span><AppIcon name="compass"/></span> 检修指引</div>
          <div class="guide-h-actions">
            <button
              v-if="synthSupported"
              class="voice-toggle" :class="{ on: voiceGuide }"
              @click="toggleVoiceGuide" :title="voiceGuide ? '关闭语音播报' : '开启语音播报'"
            ><AppIcon :name="voiceGuide ? 'volume-on' : 'volume-off'"/> {{ voiceGuide ? ' 语音开' : ' 语音关' }}</button>
            <button class="guide-close" @click="cancelSpeak(); guideShow = false"><AppIcon name="x"/></button>
          </div>
        </div>

        <div class="guide-body" ref="guideBodyRef">
          <!-- 已完成步骤 + 当前步骤的时间线 -->
          <div v-for="(s, i) in guideSteps" :key="i" class="guide-step">
            <!-- 系统给出的检查点 / 最终结论 -->
            <div class="g-row sys">
              <div class="g-avatar">AI</div>
              <div class="g-bubble">
                <template v-if="!s.is_final">
                  <div class="g-step-no">第 {{ s.step_no }} 步</div>
                  <div v-if="s.ruled_out?.length" class="g-ruled">
                    <span v-for="(r, ri) in s.ruled_out" :key="ri" class="g-ruled-tag">✗ 已排除：{{ r }}</span>
                  </div>
                  <div class="g-action">{{ s.action }}</div>
                  <div v-if="s.purpose"  class="g-meta"><AppIcon name="target"/> 目的：{{ s.purpose }}</div>
                  <div v-if="s.expected" class="g-meta"><AppIcon name="eye"/> 判断：{{ s.expected }}</div>
                </template>
                <template v-else>
                  <div v-if="s.ruled_out?.length" class="g-ruled">
                    <span v-for="(r, ri) in s.ruled_out" :key="ri" class="g-ruled-tag">✗ 已排除：{{ r }}</span>
                  </div>
                  <div class="g-final-title"><AppIcon name="check-circle"/> 排查完成 · 结论</div>
                  <div class="g-conclusion">{{ s.conclusion }}</div>
                  <div v-if="s.final_tools?.length" class="g-final-sec">
                    <div class="g-final-label">所需工具</div>
                    <span v-for="(t, ti) in s.final_tools" :key="ti" class="tech-tag">{{ t }}</span>
                  </div>
                  <div v-if="s.final_safety?.length" class="g-final-sec">
                    <div class="g-final-label">安全注意</div>
                    <div v-for="(r, ri) in s.final_safety" :key="ri" class="g-safety"><AppIcon name="warning"/> {{ r }}</div>
                  </div>
                </template>
              </div>
            </div>
            <!-- 用户对该步的反馈 -->
            <div v-if="s.feedback" class="g-row user">
              <div class="g-bubble user-bubble">
                <span class="g-fb-tag" :class="fbClass(s.feedback.result)">{{ fbLabel(s.feedback.result) }}</span>
                <span v-if="s.feedback.note" class="g-fb-note">{{ s.feedback.note }}</span>
              </div>
            </div>
          </div>

          <!-- 加载中 -->
          <div v-if="guideLoading" class="g-loading">
            <span class="loading-dot">◉</span> AI 正在分析反馈，生成下一步…
          </div>
        </div>

        <!-- 当前步骤的反馈输入区（未完成时显示） -->
        <div v-if="curStep && !curStep.is_final && !guideLoading" class="guide-input">
          <div class="g-input-hint">完成上述检查后，反馈结果：</div>
          <div class="g-fb-btns">
            <button
              v-for="opt in fbOptions" :key="opt.v"
              class="g-fb-btn" :class="[opt.cls, { active: guideFb.result === opt.v }]"
              @click="guideFb.result = opt.v"
            >{{ opt.label }}</button>
          </div>
          <input v-model="guideFb.note" class="tech-input" placeholder="补充说明（选填，如具体读数/现象）" />
          <button class="btn-primary g-next-btn" :disabled="!guideFb.result" @click="submitGuideStep">
            提交并获取下一步 →
          </button>
        </div>

        <!-- 完成态 -->
        <div v-if="curStep && curStep.is_final" class="guide-input">
          <div class="g-repair-hint">已锁定根本原因，可直接进入现场维修作业</div>
          <div class="g-final-btns">
            <button class="btn-outline g-close-btn" @click="cancelSpeak(); guideShow = false">仅关闭</button>
            <button class="btn-primary g-next-btn" @click="startRepair">
              <AppIcon name="wrench"/> 开始维修
            </button>
          </div>
        </div>
      </div>
    </van-popup>

    <!-- 引用来源原文抽屉（创新点 A） -->
    <van-popup v-model:show="showSource" position="right" :style="{ width: '520px', height: '100%', maxWidth: '100vw' }">
      <div class="source-panel" v-if="curSource">
        <div class="detail-topbar">
          <button @click="showSource = false" class="close-btn"><AppIcon name="x"/> 关闭</button>
          <span class="tech-tag">{{ curSource.source_type === 'manual' ? '检修手册' : (curSource.source_type === 'case' ? '历史案例' : '知识') }}</span>
        </div>
        <div class="source-scroll">
          <h3 class="source-title">
            <span v-if="curSource.ref_no" class="cite-no">[{{ curSource.ref_no }}]</span>
            {{ curSource.title }}
          </h3>
          <div class="source-meta">
            <span v-if="curSource.page_no" class="src-tag"><AppIcon name="book"/> 手册第 {{ curSource.page_no }} 页</span>
            <span v-if="curSource.device_model" class="src-tag"><AppIcon name="monitor"/> {{ curSource.device_model }}</span>
            <span v-if="curSource.score != null" class="src-tag">匹配度 {{ (curSource.score * 100).toFixed(0) }}%</span>
          </div>
          <div class="source-body">{{ curSource.content }}</div>
        </div>
      </div>
    </van-popup>

    <!-- 历史诊断详情抽屉 -->
    <van-popup v-model:show="showHistDetail" position="right" :style="{ width: '560px', height: '100%', maxWidth: '100vw' }">
      <div class="source-panel" v-if="curHist">
        <div class="detail-topbar">
          <button @click="showHistDetail = false" class="close-btn"><AppIcon name="x"/> 关闭</button>
          <span class="tech-tag">{{ curHist.device_type_name || '未指定设备' }}</span>
        </div>
        <div class="source-scroll">
          <div class="hist-label">故障描述</div>
          <div class="hist-desc">{{ curHist.fault_description || '（无）' }}</div>
          <div class="hist-label" style="margin-top:14px">诊断报告</div>
          <div class="hist-md" v-html="renderHist"></div>

          <!-- 分步检修指引过程 + 最终结论 -->
          <template v-if="histGuide">
            <div class="hist-label" style="margin-top:16px">分步检修指引</div>
            <div class="hist-guide">
              <div v-for="(h, i) in (histGuide.guide_history || [])" :key="i" class="hg-step">
                <span class="hg-no">{{ i + 1 }}</span>
                <span class="hg-action">{{ h.action }}</span>
                <span class="hg-res" :class="fbClass(h.result)">{{ h.result }}</span>
                <span v-if="h.note" class="hg-note">（{{ h.note }}）</span>
              </div>
              <div v-if="histGuideConclusion" class="hg-conclusion">
                <div class="hg-conc-title"><AppIcon name="check-circle"/> 最终结论</div>
                <div class="hg-conc-body">{{ histGuideConclusion }}</div>
              </div>
            </div>
          </template>

          <div class="hist-time"><AppIcon name="clock"/> {{ formatTime(curHist.started_at) }}</div>
          <button class="btn-outline" style="margin-top:16px;width:100%" @click="reuseHistory"><AppIcon name="back"/> 用此描述重新诊断</button>
        </div>
      </div>
    </van-popup>

    <!-- 反馈弹窗 -->
    <van-popup v-model:show="showFeedback" round position="bottom" :style="{ height: '50%' }">
      <div class="feedback-popup">
        <div class="popup-title">提交反馈</div>
        <textarea v-model="feedbackText" class="tech-input feedback-textarea" placeholder="请输入您的修正意见..."></textarea>
        <div class="popup-actions">
          <button class="btn-outline" @click="showFeedback = false">取消</button>
          <button class="btn-primary" @click="submitFeedback">提交反馈</button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { diagnosisApi, devicesApi, feedbackApi, workflowApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { marked } from 'marked'
import { showToast, showImagePreview } from 'vant'
import * as echarts from 'echarts'
import { useRouter } from 'vue-router'
import { useSpeech } from '@/composables/useSpeech'

const router = useRouter()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

const form = reactive({
  deviceTypeId: '',
  description: '',
})
const imageFiles     = ref([])
const previewImages  = ref([])
const analyzing      = ref(false)
const result         = ref(null)
const history        = ref([])
const deviceTypes    = ref([])
const noKnowledgeDevices = ref(false)   // #5：知识库为空时回退全量并提示
const stats          = reactive({ today: 0, total: 0 })
const showFeedback   = ref(false)
const feedbackText   = ref('')
const feedbackType   = ref('error')
const currentStep    = ref(0)

// 创新点 C：语音
const { recognitionSupported, synthSupported, listening, startListening, stopListening, speak, cancelSpeak } = useSpeech()
function toggleMic() {
  if (listening.value) { stopListening(); return }
  startListening((text) => { form.description = text })
}

// 创新点 A：引用溯源
const showSource = ref(false)
const curSource  = ref(null)
const citedSources = computed(() => {
  const cites = result.value?.citations || []
  const srcs  = result.value?.sources || []
  if (cites.length) return cites.map(n => srcs[n - 1]).filter(Boolean)
  return srcs   // 模型未显式给 citations 时，退化为展示全部召回来源
})
function openSourceByRef(n) {
  const s = (result.value?.sources || [])[n - 1]
  if (s) { curSource.value = s; showSource.value = true }
}
function openSource(s) { curSource.value = s; showSource.value = true }
// 把答案 HTML 中的 [来源N] 替换为可点击角标
// 关键：marked 偶发会把 [来源N] 当作 Markdown 链接/引用语法吃掉或转义，导致正则替换失败、角标点不开。
// 解法：marked 之前先把 [来源N] 换成不会被 markdown 干扰的占位符；marked.parse 之后再换成 <sup>。
const renderedResult = computed(() => {
  if (!result.value?.answer) return ''
  const placeheld = result.value.answer.replace(/\[来源(\d+)\]/g, (_, n) => `§§CITE${n}§§`)
  let html = marked.parse(placeheld)
  html = html.replace(/§§CITE(\d+)§§/g, (_, n) => `<sup class="cite-badge" data-ref="${n}">[来源${n}]</sup>`)
  return html
})
function onAnswerClick(e) {
  const t = e.target
  if (t && t.classList && t.classList.contains('cite-badge')) {
    const n = parseInt(t.getAttribute('data-ref'), 10)
    if (n) openSourceByRef(n)
  }
}

// 创新点 B：知识图谱推理子图（ECharts 力导向图）
const kgChartRef = ref(null)
let kgChart = null
const ENTITY_COLOR = {
  symptom: '#ff6b81', cause: '#ffa94d', solution: '#2ee6a8', tool: '#22ddff',
  component: '#7c8aa3', device: '#5b8cff', part: '#b08cff',
}
function renderKgGraph() {
  const g = result.value?.kg_graph
  if (!g || !g.entities?.length) return
  // 关键：第二次诊断时 DOM 会被 v-if 销毁/重建，旧 kgChart 实例指向已被卸载的 div，导致画不出来或一闪而过。
  // 因此每次都先销毁旧实例，再用最新的 kgChartRef 重新 init。配合外层 v-if，保证 DOM 已挂载。
  nextTick(() => {
    if (!kgChartRef.value) return
    if (kgChart) {
      try { kgChart.dispose() } catch {}
      kgChart = null
    }
    kgChart = echarts.init(kgChartRef.value)
    const nodes = g.entities.map(e => ({
      id: e.id, name: e.name,
      symbolSize: e.is_seed ? 48 : 30,
      // 命中关键词（种子）统一用蓝色高亮大圈；其余实体按类型着色
      itemStyle: e.is_seed
        ? { color: '#3b82f6', borderColor: '#9ec5ff', borderWidth: 2 }
        : { color: ENTITY_COLOR[e.type] || '#7c8aa3' },
    }))
    const links = (g.relations || []).map(r => ({
      source: r.subject, target: r.object, value: r.predicate_zh,
      label: { show: true, formatter: r.predicate_zh, fontSize: 11, color: '#9fb0c9' },
      lineStyle: { color: '#3a4a66', curveness: 0.15 },
    }))
    kgChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { formatter: p => p.dataType === 'edge' ? p.data.value : p.name },
      series: [{
        type: 'graph', layout: 'force', roam: true, draggable: true,
        force: { repulsion: 260, edgeLength: 120 },
        edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 8,
        data: nodes, links,
        label: { show: true, position: 'right', color: '#eaf2ff', fontSize: 13, fontWeight: 600 },
        lineStyle: { width: 1.4, opacity: 0.9 },
        emphasis: { focus: 'adjacency', label: { fontSize: 15 } },
      }],
    })
    kgChart.resize()
  })
}

// ===== 分步检修指引 =====
const guideShow    = ref(false)
// 抽屉宽度 + 左边缘拖拽调宽
const guideWidth   = ref(680)
function startGuideResize() {
  const move = (ev) => {
    const w = window.innerWidth - ev.clientX
    guideWidth.value = Math.min(Math.max(w, 460), Math.floor(window.innerWidth * 0.96))
  }
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
    document.body.style.userSelect = ''
  }
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}
const guideSteps   = ref([])      // [{...step, feedback?}]
const guideLoading = ref(false)
const guideFb      = reactive({ result: '', note: '' })
const guideBodyRef = ref(null)

const fbOptions = [
  { v: '正常',   label: '✓ 正常',   cls: 'green'  },
  { v: '异常',   label: '✗ 异常',   cls: 'red'    },
  { v: '不确定', label: '? 不确定', cls: 'orange' },
]
const curStep = computed(() => guideSteps.value[guideSteps.value.length - 1] || null)
const fbLabel = (v) => ({ '正常': '✓ 正常', '异常': '✗ 异常', '不确定': '? 不确定' }[v] || v)
const fbClass = (v) => ({ '正常': 'green', '异常': 'red', '不确定': 'orange' }[v] || '')

function scrollGuideBottom() {
  nextTick(() => {
    const el = guideBodyRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function fetchGuideStep() {
  guideLoading.value = true
  try {
    const history = guideSteps.value
      .filter(s => s.feedback)
      .map(s => ({ action: s.action, result: s.feedback.result, note: s.feedback.note || '' }))
    const step = await diagnosisApi.guideStep({
      record_id:         result.value?.record_id || null,
      fault_description: form.description,
      fault_analysis:    result.value?.fault_analysis || '',
      repair_steps:      result.value?.repair_steps || [],
      history,
    })
    guideSteps.value.push(step)
    guideFb.result = ''
    guideFb.note   = ''
    scrollGuideBottom()
    if (voiceGuide.value) speakStep(step)   // 创新点 C：自动语音播报本步
  } catch (e) {
    showToast('获取检修指引失败，请重试')
  } finally {
    guideLoading.value = false
  }
}

// 创新点 C：步骤语音播报
const voiceGuide = ref(false)
function speakStep(s) {
  if (!s) return
  const text = s.is_final
    ? `排查完成。结论：${s.conclusion || ''}`
    : `第${s.step_no}步。${s.action || ''}。${s.expected ? '判断：' + s.expected : ''}`
  speak(text)
}
function toggleVoiceGuide() {
  voiceGuide.value = !voiceGuide.value
  if (voiceGuide.value) { if (curStep.value) speakStep(curStep.value) }
  else cancelSpeak()
}

// ===== 维修工单留痕（source=diagnosis，与作业指引的标准化作业分列） =====
const repairRecords  = ref([])
const rpLoading      = ref(false)
const rpScope        = ref('mine')     // mine | all（all 仅管理员）
const rpStatus       = ref('')
const showRpDetail   = ref(false)
const curRp          = ref(null)
const curRpSteps     = ref([])
const rpDetailLoading = ref(false)
const curRpCause = computed(() =>
  curRp.value?.root_cause || curRp.value?.steps_data?.root_cause || '')

async function loadRepairRecords() {
  rpLoading.value = true
  try {
    repairRecords.value = (await workflowApi.records({
      scope: rpScope.value, status: rpStatus.value || undefined,
      source: 'diagnosis', page: 1, size: 50,
    })).items || []
  } catch { repairRecords.value = [] } finally { rpLoading.value = false }
}
function setRpScope(v) { if (rpScope.value === v) return; rpScope.value = v; loadRepairRecords() }
async function openRepairRecord(r) {
  curRp.value = r; curRpSteps.value = []; showRpDetail.value = true; rpDetailLoading.value = true
  try {
    const full = await workflowApi.getRecord(r.id)
    curRp.value = { ...r, ...full }
    curRpSteps.value = (full.steps_data && full.steps_data.executed) || []
  } catch {} finally { rpDetailLoading.value = false }
}
function previewRpPhoto(url) { showImagePreview([url]) }
loadRepairRecords()

// 排查定论 → 现场维修作业：把定论上下文交给独立的「维修执行」页
// 该页与「作业指引」的标准化模板执行相互独立：标准作业面向可预期的重复任务、
// 由管理员审核发布模板；此处面向突发故障，依据本次排查结论即时生成，不落模板库。
function startRepair() {
  const cs = curStep.value
  if (!cs || !cs.is_final) return
  cancelSpeak()
  const history = guideSteps.value
    .filter(s => s.feedback)
    .map(s => ({ action: s.action, result: s.feedback.result, note: s.feedback.note || '' }))
  // 跳去维修页会卸载本组件，result 随之丢失，回来后「存为案例」入口就没了。
  // 这里连同表单一起做快照，回到诊断页时还原，保证经验回流链路不断。
  try {
    sessionStorage.setItem('diag_snapshot', JSON.stringify({
      result: result.value,
      form: { deviceTypeId: form.deviceTypeId, description: form.description },
    }))
  } catch {}
  sessionStorage.setItem('repair_ctx', JSON.stringify({
    record_id:         result.value?.record_id || null,
    device_type_id:    form.deviceTypeId || null,
    fault_description: form.description || '',
    root_cause:        cs.conclusion || '',
    history,
  }))
  guideShow.value = false
  router.push('/repair')
}

function startGuide() {
  if (!result.value) return
  guideShow.value  = true
  guideSteps.value = []
  guideFb.result   = ''
  guideFb.note     = ''
  fetchGuideStep()
}

function submitGuideStep() {
  if (!curStep.value || !guideFb.result) return
  // 把反馈挂到当前步骤，再请求下一步
  curStep.value.feedback = { result: guideFb.result, note: guideFb.note.trim() }
  scrollGuideBottom()
  fetchGuideStep()
}

const analysisSteps = [
  '解析故障描述...',
  '图片特征提取...',
  '知识库向量检索...',
  'AI 多模态分析...',
  '生成诊断报告...',
]

// 加载设备类型（#5：诊断只列"知识库中确有知识"的设备；为空则回退全量并提示）
devicesApi.list({ has_knowledge: 1, page: 1, size: 100 })
  .then(r => {
    const items = r.items || []
    if (items.length === 0) {
      noKnowledgeDevices.value = true
      return devicesApi.list({ page: 1, size: 100 }).then(r2 => { deviceTypes.value = r2.items || [] })
    }
    deviceTypes.value = items
  })
  .catch(() => {})

// 从维修执行页返回时还原上一次诊断结果，「存为案例」等操作照常可用
try {
  const _snap = JSON.parse(sessionStorage.getItem('diag_snapshot') || 'null')
  if (_snap && _snap.result) {
    result.value = _snap.result
    form.deviceTypeId = _snap.form?.deviceTypeId || ''
    form.description = _snap.form?.description || ''
    nextTick(renderKgGraph)
  }
} catch {}

// 加载历史
diagnosisApi.history({ page: 1, size: 5 })
  .then(r => {
    history.value = r.items || []
    stats.today = r.today_count || 0
    stats.total = r.total || 0
  }).catch(() => {})

function handleImageUpload(e) {
  const files = Array.from(e.target.files)
  files.forEach(f => {
    if (imageFiles.value.length >= 3) return
    if (f.size > 5 * 1024 * 1024) { showToast('图片超过 5MB'); return }
    imageFiles.value.push(f)
    const reader = new FileReader()
    reader.onload = ev => previewImages.value.push(ev.target.result)
    reader.readAsDataURL(f)
  })
  e.target.value = ''
}

function removeImage(idx) {
  imageFiles.value.splice(idx, 1)
  previewImages.value.splice(idx, 1)
}

async function startAnalysis() {
  analyzing.value = true
  currentStep.value = 0
  result.value = null
  sessionStorage.removeItem('diag_snapshot')   // 开新一轮，旧快照作废

  // 模拟步骤推进
  const stepTimer = setInterval(() => {
    if (currentStep.value < analysisSteps.length - 1) currentStep.value++
  }, 1200)

  try {
    const fd = new FormData()
    fd.append('description', form.description)
    if (form.deviceTypeId) fd.append('device_type_id', form.deviceTypeId)
    imageFiles.value.forEach(f => fd.append('images', f))

    result.value = await diagnosisApi.analyze(fd)
    nextTick(renderKgGraph)   // 创新点 B：渲染知识图谱推理子图
  } catch (e) {
    showToast('诊断失败，请检查网络或稍后重试')
  } finally {
    clearInterval(stepTimer)
    analyzing.value = false
  }
}

// 点开近期诊断 → 查看该次完整诊断报告
const showHistDetail = ref(false)
const curHist = ref(null)
const renderHist = computed(() =>
  curHist.value?.diagnosis_result
    ? marked.parse(curHist.value.diagnosis_result)
    : '<span style="color:var(--text-muted)">（该记录无报告内容）</span>'
)
function openHistory(h) { curHist.value = h; showHistDetail.value = true }
// 该次诊断若做过分步检修指引，取出过程与最终结论
const histGuide = computed(() => {
  const sd = curHist.value?.steps_data
  return (sd && (sd.guide_history || sd.current_step)) ? sd : null
})
const histGuideConclusion = computed(() => {
  const cs = histGuide.value?.current_step
  return cs && cs.is_final ? (cs.conclusion || '') : ''
})
function reuseHistory() {
  if (!curHist.value) return
  form.description  = curHist.value.fault_description || ''
  form.deviceTypeId = curHist.value.device_type_id || ''
  showHistDetail.value = false
}

function copyResult() {
  navigator.clipboard?.writeText(result.value?.answer || '')
    .then(() => showToast({ message: '已复制', type: 'success' }))
}

function saveAsCase() {
  if (!result.value) return
  const d = result.value
  const solution = (d.repair_steps && d.repair_steps.length)
    ? d.repair_steps.map((s, i) => `${i + 1}. ${s}`).join('\n')
    : (d.answer || '')
  // 把诊断内容带入提交案例页（CaseNew 会自动读取 case_draft 草稿并预填）
  const draft = {
    title: (form.description || '').trim().slice(0, 40) || '故障诊断生成的案例',
    device_type_id: form.deviceTypeId || '',
    fault_phenomenon: form.description || '',
    fault_reason: d.fault_analysis || '',
    solution,
    tools: (d.required_tools || []).join(', '),
  }
  localStorage.setItem('case_draft', JSON.stringify(draft))
  showToast({ message: '已带入诊断内容，确认后即可提交', type: 'success' })
  router.push('/cases/new')
}

function openFeedback(type) {
  feedbackType.value = type
  feedbackText.value = ''
  showFeedback.value = true
}

async function submitFeedback() {
  if (!feedbackText.value.trim()) { showToast('请填写反馈内容'); return }
  try {
    await feedbackApi.submit({
      original_output:  result.value?.answer || '',
      user_correction:  feedbackText.value,
      correction_type:  feedbackType.value,
    })
    showToast({ message: '反馈已提交，感谢您的贡献', type: 'success' })
    showFeedback.value = false
  } catch {}
}

function formatTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
}
</script>

<style scoped>
.diagnosis-page { max-width: 1400px; margin: 0 auto; }

.page-header { display: flex; align-items: center; justify-content: space-between; }
.header-left { display: flex; align-items: center; gap: 14px; }
.header-icon { font-size: 32px; filter: drop-shadow(0 0 8px var(--accent-cyan)); }
.header-title { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.header-desc  { font-size: 14px; color: var(--text-secondary); margin-top: 3px; }

.header-stats { display: flex; gap: 24px; }
.stat-item { text-align: center; }
.stat-val   { font-size: 24px; font-weight: 700; color: var(--accent-cyan); font-family: monospace; }
.stat-label { font-size: 13px; color: var(--text-muted); margin-top: 2px; }

.diagnosis-layout { display: grid; grid-template-columns: 420px 1fr; gap: 20px; }
@media (max-width: 1100px) { .diagnosis-layout { grid-template-columns: 1fr; } }

.input-panel { display: flex; flex-direction: column; gap: 16px; }

.panel-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 14px; letter-spacing: 0.04em;
}

.form-row { margin-bottom: 14px; }
.form-label { display: block; font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.required { color: var(--accent-red); }

.desc-textarea { resize: vertical; min-height: 100px; font-family: inherit; }
.char-count { font-size: 13px; color: var(--text-muted); text-align: right; margin-top: 3px; }

.upload-grid { display: flex; gap: 10px; flex-wrap: wrap; }
.upload-item {
  width: 80px; height: 80px; border-radius: var(--radius-sm);
  border: 1px dashed var(--border-color);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  cursor: pointer; position: relative; overflow: hidden;
  transition: border-color 0.2s;
}
.upload-btn:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.upload-btn span:first-child { font-size: 20px; }
.preview-img { width: 100%; height: 100%; object-fit: cover; }
.remove-btn {
  position: absolute; top: 2px; right: 2px;
  background: rgba(0,0,0,0.6); color: #fff; border: none;
  border-radius: 50%; width: 18px; height: 18px; font-size: 13px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.upload-hint { font-size: 13px; color: var(--text-muted); margin-top: 6px; }

.analyze-btn { width: 100%; padding: 13px; font-size: 15px; margin-top: 4px; }

.history-card { }
.history-list { display: flex; flex-direction: column; gap: 8px; }
.history-item {
  padding: 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); cursor: pointer; transition: all 0.2s;
}
.history-item:hover { border-color: var(--accent-cyan); background: rgba(34,221,255,0.03); }
.history-title { font-size: 15px; color: var(--text-primary); margin-bottom: 6px; }
.history-meta  { display: flex; align-items: center; justify-content: space-between; }
.history-time  { font-size: 13px; color: var(--text-muted); }

/* 结果面板 */
.result-panel { min-height: 400px; }

.empty-result {
  height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px; text-align: center; min-height: 400px;
}
.empty-icon  { font-size: 48px; opacity: 0.3; }
.empty-title { font-size: 16px; color: var(--text-secondary); }
.empty-desc  { font-size: 15px; color: var(--text-muted); max-width: 300px; }

/* 分析动画 */
.analyzing-card {
  min-height: 400px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 32px;
}
.scan-container {
  position: relative; width: 120px; height: 120px;
  display: flex; align-items: center; justify-content: center;
}
.scan-ring {
  position: absolute; border-radius: 50%; border: 1px solid var(--accent-cyan);
  animation: scan-pulse 2s ease-in-out infinite;
}
.r1 { width: 120px; height: 120px; animation-delay: 0s;    opacity: 0.3; }
.r2 { width: 80px;  height: 80px;  animation-delay: 0.4s; opacity: 0.5; }
.r3 { width: 40px;  height: 40px;  animation-delay: 0.8s; opacity: 0.8; }
.scan-center { font-size: 16px; font-weight: 700; color: var(--accent-cyan); z-index: 1; }
@keyframes scan-pulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50%       { transform: scale(1.1); opacity: 0.8; }
}

.analyzing-steps { display: flex; flex-direction: column; gap: 8px; }
.analyze-step {
  display: flex; align-items: center; gap: 10px;
  font-size: 15px; color: var(--text-muted); transition: all 0.3s;
}
.analyze-step.done   { color: var(--accent-green); }
.analyze-step.active { color: var(--accent-cyan); font-weight: 600; }
.step-icon { font-size: 16px; width: 16px; text-align: center; }

/* 结果卡片 */
.result-card { }
.result-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px; flex-wrap: wrap; gap: 8px;
}
.result-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 600; color: var(--text-primary);
}
.result-time { font-size: 13px; color: var(--text-muted); margin-left: 4px; }
.result-actions { display: flex; gap: 8px; }

.result-content {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 16px;
  line-height: 1.8;
  font-size: 16px;
  color: var(--text-primary);
  max-height: 400px;
  overflow-y: auto;
}
.result-content :deep(h1),
.result-content :deep(h2),
.result-content :deep(h3) { color: var(--accent-cyan); margin: 12px 0 6px; }
.result-content :deep(strong) { color: var(--text-primary); }
.result-content :deep(ul),
.result-content :deep(ol)   { padding-left: 20px; }
.result-content :deep(code) {
  background: rgba(34,221,255,0.08);
  padding: 2px 6px; border-radius: 3px;
  font-family: monospace; color: var(--accent-cyan);
}

/* #5 字段提示 + 语音按钮 */
.field-hint { font-size: 12px; color: var(--text-muted); margin-top: 5px; }
.mic-btn {
  margin-left: 10px; padding: 2px 10px; font-size: 13px; cursor: pointer;
  border: 1px solid var(--border-color); border-radius: 14px; background: transparent;
  color: var(--accent-cyan); transition: all 0.2s;
}
.mic-btn:hover { border-color: var(--accent-cyan); }
.mic-btn.on { color: var(--accent-red); border-color: var(--accent-red); background: rgba(255,71,87,0.08); animation: micpulse 1.2s infinite; }
@keyframes micpulse { 0%,100% { opacity: 1; } 50% { opacity: 0.55; } }

/* 创新点 A：引用溯源 */
.result-content :deep(.cite-badge) {
  color: var(--accent-cyan); cursor: pointer; font-weight: 700;
  padding: 0 2px; border-radius: 3px; background: rgba(34,221,255,0.12);
}
.result-content :deep(.cite-badge:hover) { background: rgba(34,221,255,0.28); }
.cite-section { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-color); }
.cite-head { font-size: 14px; color: var(--text-secondary); margin-bottom: 10px; }
.cite-list { display: flex; flex-direction: column; gap: 8px; }
.cite-chip {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; text-align: left;
  padding: 8px 12px; border: 1px solid var(--border-color); border-radius: var(--radius-sm);
  background: var(--bg-secondary); color: var(--text-primary); cursor: pointer; transition: all 0.2s;
}
.cite-chip:hover { border-color: var(--accent-cyan); background: rgba(34,221,255,0.04); }
.cite-no   { color: var(--accent-cyan); font-weight: 700; font-family: monospace; }
.cite-title { flex: 1; font-size: 14px; }
.cite-page { font-size: 12px; color: var(--accent-orange); border: 1px solid rgba(255,159,67,0.4); border-radius: 8px; padding: 0 8px; }
.cite-src  { font-size: 12px; color: var(--text-muted); border: 1px solid var(--border-color); border-radius: 8px; padding: 0 8px; }

/* 创新点 B：知识图谱 */
.kg-section { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-color); }
.kg-head { font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }
.kg-tip { font-size: 12px; color: var(--text-muted); line-height: 1.6; margin-bottom: 10px; }
.kg-chart { width: 100%; height: 340px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); }
.kg-legend { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: var(--text-muted); }
.kg-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }

/* 历史诊断详情抽屉 */
.hist-label { font-size: 13px; color: var(--text-muted); margin-bottom: 4px; }
.hist-desc { font-size: 15px; color: var(--text-secondary); line-height: 1.7; }
.hist-md { font-size: 15px; color: var(--text-primary); line-height: 1.85; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px; }
.hist-md :deep(h2) { font-size: 16px; color: var(--accent-cyan); margin: 10px 0 6px; }
.hist-md :deep(ul), .hist-md :deep(ol) { padding-left: 20px; }
.hist-time { margin-top: 14px; font-size: 13px; color: var(--text-muted); }
.hist-guide { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; }
.hg-step { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; padding: 5px 0; font-size: 14px; color: var(--text-secondary); border-bottom: 1px dashed var(--border-color); }
.hg-step:last-of-type { border-bottom: none; }
.hg-no { width: 20px; height: 20px; flex-shrink: 0; border-radius: 50%; background: rgba(34,221,255,0.12); color: var(--accent-cyan); display: inline-flex; align-items: center; justify-content: center; font-size: 12px; }
.hg-action { flex: 1; color: var(--text-primary); }
.hg-res { font-weight: 600; }
.hg-res.green { color: var(--accent-green); }
.hg-res.red { color: var(--accent-red); }
.hg-res.orange { color: var(--accent-orange); }
.hg-note { color: var(--text-muted); font-size: 13px; }
.hg-conclusion { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color); }
.hg-conc-title { font-size: 14px; font-weight: 700; color: var(--accent-green); margin-bottom: 4px; }
.hg-conc-body { font-size: 15px; color: var(--text-primary); line-height: 1.7; white-space: pre-wrap; }

/* 来源原文抽屉 */
.source-panel { height: 100%; display: flex; flex-direction: column; background: var(--bg-card); }
.source-scroll { flex: 1; overflow-y: auto; padding: 18px; }
.source-title { font-size: 16px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; line-height: 1.5; }
.source-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.src-tag { font-size: 13px; color: var(--text-secondary); border: 1px solid var(--border-color); border-radius: 10px; padding: 2px 10px; }
.source-body { font-size: 15px; color: var(--text-secondary); line-height: 1.9; white-space: pre-wrap; }
.detail-topbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border-color); }
.close-btn { background: none; border: none; color: var(--text-secondary); font-size: 15px; cursor: pointer; }

/* 指引语音开关 */
.guide-h-actions { display: flex; align-items: center; gap: 8px; }
.voice-toggle {
  padding: 3px 10px; font-size: 13px; cursor: pointer; border-radius: 14px;
  border: 1px solid var(--border-color); background: transparent; color: var(--text-secondary); transition: all 0.2s;
}
.voice-toggle.on { color: var(--accent-cyan); border-color: var(--accent-cyan); background: rgba(34,221,255,0.08); }

.related-cases { margin-top: 16px; }
.related-title { font-size: 14px; color: var(--text-secondary); margin-bottom: 10px; }
.case-cards { display: flex; flex-direction: column; gap: 8px; }
.case-card {
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-sm); padding: 10px;
}
.case-score { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.score-bar  {
  height: 4px; border-radius: 2px;
  background: linear-gradient(90deg, var(--accent-blue), var(--accent-cyan));
  max-width: 120px;
}
.case-score span { font-size: 13px; color: var(--accent-cyan); }
.case-title   { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.case-content { font-size: 14px; color: var(--text-secondary); }

.feedback-bar {
  display: flex; align-items: center; gap: 10px;
  margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--border-color);
  flex-wrap: wrap;
}
.feedback-label { font-size: 14px; color: var(--text-muted); margin-right: 4px; }
.fb-btn {
  padding: 4px 12px; border-radius: 20px; font-size: 14px;
  border: 1px solid; cursor: pointer; background: transparent; transition: all 0.2s;
}
.fb-btn.red    { border-color: rgba(255,71,87,0.4);  color: var(--accent-red);    }
.fb-btn.orange { border-color: rgba(255,159,67,0.4); color: var(--accent-orange); }
.fb-btn.green  { border-color: rgba(0,255,157,0.4);  color: var(--accent-green);  }
.fb-btn:hover  { filter: brightness(1.3); }

/* 分步指引入口 CTA */
.guide-cta {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-top: 16px; padding: 14px 16px;
  background: linear-gradient(135deg, rgba(43,123,255,0.10), rgba(34,221,255,0.06));
  border: 1px solid rgba(34,221,255,0.25);
  border-radius: var(--radius-md);
  flex-wrap: wrap;
}
.guide-cta-text { display: flex; align-items: center; gap: 12px; }
.guide-cta-icon { font-size: 28px; filter: drop-shadow(0 0 6px var(--accent-cyan)); }
.guide-cta-title { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.guide-cta-desc  { font-size: 14px; color: var(--text-secondary); margin-top: 2px; }

/* 指引弹窗（右侧大抽屉，可拖左边缘调宽，配色对齐主题） */
.guide-modal { background: var(--bg-card) !important; overflow: hidden; }
.guide-popup { position: relative; display: flex; flex-direction: column; height: 100%; background: var(--bg-card); }
.guide-resizer {
  position: absolute; left: 0; top: 0; width: 8px; height: 100%;
  cursor: ew-resize; z-index: 5; background: transparent;
}
.guide-resizer:hover { background: rgba(34,221,255,0.25); }
.guide-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px 16px 24px; border-bottom: 1px solid var(--border-color); flex-shrink: 0;
  background: var(--gradient-header);
}
.guide-h-title { font-size: 17px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
.guide-close {
  background: none; border: none; color: var(--text-muted);
  font-size: 18px; cursor: pointer; padding: 4px 8px;
}
.guide-close:hover { color: var(--text-primary); }

.guide-body { flex: 1; overflow-y: auto; padding: 18px 20px; display: flex; flex-direction: column; gap: 14px; }
.guide-step { display: flex; flex-direction: column; gap: 8px; }

.g-row { display: flex; gap: 10px; }
.g-row.user { justify-content: flex-end; }
.g-avatar {
  width: 34px; height: 34px; flex-shrink: 0; border-radius: 50%;
  background: var(--gradient-btn); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700;
}
.g-bubble {
  max-width: 80%;
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: 12px; padding: 12px 14px; font-size: 16px; line-height: 1.6;
  color: var(--text-primary);
}
.user-bubble {
  background: rgba(34,221,255,0.10); border-color: rgba(34,221,255,0.3);
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.g-step-no { font-size: 13px; color: var(--accent-cyan); font-weight: 700; margin-bottom: 4px; }
.g-action  { font-size: 17px; font-weight: 600; color: var(--text-primary); }
.g-meta    { font-size: 14px; color: var(--text-secondary); margin-top: 6px; }
.g-ruled   { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.g-ruled-tag {
  font-size: 13px; color: var(--text-muted);
  background: rgba(124,138,163,0.12); border: 1px solid var(--border-color);
  border-radius: 12px; padding: 2px 10px; text-decoration: line-through;
}
.g-fb-tag { font-size: 14px; font-weight: 600; padding: 2px 10px; border-radius: 12px; }
.g-fb-tag.green  { color: var(--accent-green);  background: rgba(46,230,168,0.12); }
.g-fb-tag.red    { color: var(--accent-red);    background: rgba(255,94,108,0.12); }
.g-fb-tag.orange { color: var(--accent-orange); background: rgba(255,171,87,0.12); }
.g-fb-note { font-size: 15px; color: var(--text-secondary); }

.g-final-title { font-size: 16px; font-weight: 700; color: var(--accent-green); margin-bottom: 6px; }
/* ===== 维修工单留痕 ===== */
.rp-card { margin-top: 20px; max-width: 100%; overflow: hidden; }
.rp-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.rp-head-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.rp-seg { display: flex; flex-shrink: 0; border: 1px solid var(--border-color); border-radius: var(--radius-sm); overflow: hidden; }
.rp-seg .seg {
  padding: 6px 14px; font-size: 13px; line-height: 1.4; background: transparent; border: none;
  color: var(--text-secondary); cursor: pointer;
  white-space: nowrap;   /* 不加会被挤成竖排一字一行 */
}
.rp-seg .seg + .seg { border-left: 1px solid var(--border-color); }
.rp-seg .seg.on { background: rgba(34,221,255,0.10); color: var(--accent-cyan); }
/* .tech-input 全局是 width:100%，此处必须显式收窄，否则会把左边的分段按钮压扁 */
.rp-status { width: 120px; flex-shrink: 0; padding: 6px 10px; font-size: 13px; }
.rp-hint { font-size: 13px; color: var(--text-muted); line-height: 1.7; margin: 8px 0 12px; }
.rp-empty { padding: 22px; text-align: center; color: var(--text-muted); font-size: 14px; }
.rp-list { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.rp-item {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  max-width: 100%;
  padding: 12px 14px; border: 1px solid var(--border-color);
  border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s;
}
.rp-item:hover { border-color: var(--accent-cyan); background: rgba(34,221,255,0.03); }
.rp-main { flex: 1; min-width: 0; }
.rp-title {
  font-size: 15px; font-weight: 600; color: var(--text-primary);
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  min-width: 0; overflow-wrap: anywhere;
}
.rp-name {
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; max-width: 100%;
}
.rp-cause {
  font-size: 13px; color: var(--text-secondary); margin-top: 4px;
  /* 不能用 nowrap+ellipsis：根本原因常有两三百字，不换行会把整个布局撑宽 */
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; overflow-wrap: anywhere; line-height: 1.6; max-height: 2.9em;
}
.rp-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.rp-time, .rp-badge { font-size: 13px; color: var(--text-muted); }
.rp-arrow { font-size: 14px; color: var(--accent-cyan); white-space: nowrap; }

.rp-detail {
  height: 100%; display: flex; flex-direction: column;
  /* main.js 里 vant/lib/index.css 在 global.css 之后引入，同特异性下 .van-popup 的白底会胜出，
     所以与页面其它抽屉一样，在面板根元素上显式套深色底 */
  background: var(--bg-card); color: var(--text-primary);
}
.rp-detail-top {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid var(--border-color);
  background: var(--bg-card);
}
.rp-detail .close-btn { background: none; border: none; color: var(--text-secondary); font-size: 15px; cursor: pointer; }
.rp-detail-scroll { flex: 1; overflow-y: auto; padding: 18px; }
.rp-detail-title { font-size: 17px; font-weight: 700; color: var(--text-primary); margin: 0 0 10px; }
.rp-cause-box {
  padding: 10px 12px; border-radius: var(--radius-sm); background: var(--bg-secondary);
  border: 1px solid var(--border-color); font-size: 14px; color: var(--text-primary); line-height: 1.7;
}
.rp-cause-box span { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 4px; }
.rp-meta-grid { display: flex; gap: 18px; flex-wrap: wrap; margin: 12px 0 16px; }
.rp-meta-grid div { font-size: 14px; color: var(--text-primary); }
.rp-meta-grid span { color: var(--text-muted); margin-right: 6px; }
.rps-step { padding: 12px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); margin-bottom: 10px; background: var(--bg-secondary); }
.rps-head { display: flex; align-items: center; gap: 8px; }
.rps-no { width: 20px; height: 20px; border-radius: 50%; background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; font-size: 12px; }
.rps-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.rps-done { font-size: 13px; color: var(--accent-green); }
.rps-checks { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.rps-check { font-size: 13px; color: var(--text-muted); border: 1px solid var(--border-color); border-radius: 4px; padding: 1px 6px; }
.rps-check.ok { color: var(--accent-green); border-color: rgba(0,255,157,0.3); }
.rps-note { font-size: 14px; color: var(--text-secondary); margin-top: 8px; }
.rps-photos { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.rps-photo { width: 64px; height: 64px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-color); cursor: pointer; }

.g-repair-hint { font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }
.g-final-btns  { display: flex; gap: 10px; }
.g-close-btn   { flex: 0 0 auto; }
.g-final-btns .g-next-btn { flex: 1; }
.g-conclusion  { font-size: 16px; color: var(--text-primary); line-height: 1.7; white-space: pre-wrap; }
.g-final-sec   { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.g-final-label { font-size: 14px; color: var(--text-secondary); width: 100%; margin-bottom: 2px; }
.g-safety      { font-size: 15px; color: var(--accent-orange); width: 100%; }

.g-loading { color: var(--accent-cyan); font-size: 15px; display: flex; align-items: center; gap: 8px; padding: 6px 4px; }

.guide-input {
  flex-shrink: 0; border-top: 1px solid var(--border-color);
  padding: 14px 20px; display: flex; flex-direction: column; gap: 10px;
  background: var(--bg-card);
}
.g-input-hint { font-size: 14px; color: var(--text-muted); }
.g-fb-btns { display: flex; gap: 10px; flex-wrap: wrap; }
.g-fb-btn {
  flex: 1; min-width: 90px; padding: 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: transparent;
  font-size: 16px; cursor: pointer; transition: all 0.2s; color: var(--text-secondary);
}
.g-fb-btn.green.active  { border-color: var(--accent-green);  color: var(--accent-green);  background: rgba(46,230,168,0.10); }
.g-fb-btn.red.active    { border-color: var(--accent-red);    color: var(--accent-red);    background: rgba(255,94,108,0.10); }
.g-fb-btn.orange.active { border-color: var(--accent-orange); color: var(--accent-orange); background: rgba(255,171,87,0.10); }
.g-next-btn { width: 100%; }

/* 反馈弹窗 */
.feedback-popup {
  padding: 24px; display: flex; flex-direction: column; gap: 14px; height: 100%;
}
.popup-title { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.feedback-textarea { flex: 1; resize: none; min-height: 120px; font-family: inherit; }
.popup-actions { display: flex; gap: 10px; justify-content: flex-end; }
</style>
