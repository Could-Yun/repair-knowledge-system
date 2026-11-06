<template>
  <div class="login-page tech-bg">
    <!-- 背景装饰 -->
    <div class="bg-circles">
      <div class="circle c1"></div>
      <div class="circle c2"></div>
      <div class="circle c3"></div>
    </div>

    <div class="login-container">
      <!-- 左侧品牌区 -->
      <div class="login-brand">
        <div class="brand-logo">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
            <circle cx="32" cy="32" r="28" stroke="#22ddff" stroke-width="1.5" opacity="0.4"/>
            <circle cx="32" cy="32" r="20" stroke="#22ddff" stroke-width="1.5" opacity="0.7"/>
            <circle cx="32" cy="32" r="10" fill="#22ddff" opacity="0.9"/>
            <line x1="32" y1="2" x2="32" y2="12" stroke="#22ddff" stroke-width="2"/>
            <line x1="32" y1="52" x2="32" y2="62" stroke="#22ddff" stroke-width="2"/>
            <line x1="2" y1="32" x2="12" y2="32" stroke="#22ddff" stroke-width="2"/>
            <line x1="52" y1="32" x2="62" y2="32" stroke="#22ddff" stroke-width="2"/>
          </svg>
        </div>
        <h1 class="brand-title">设备检修智能作业系统</h1>
        <p class="brand-subtitle">INTELLIGENT EQUIPMENT MAINTENANCE SYSTEM</p>
        <div class="brand-features">
          <div class="feature-item" v-for="f in features" :key="f.text">
            <span class="glow-dot green"></span>
            <span>{{ f.text }}</span>
          </div>
        </div>
        <div class="brand-badge">
          <span class="team-tag">EWBO</span>
          <span>战队 · 倾力打造</span>
        </div>
      </div>

      <!-- 右侧表单区 -->
      <div class="login-form-wrap">
        <div class="form-header">
          <h2>系统登录</h2>
          <p>SYSTEM LOGIN</p>
        </div>

        <form @submit.prevent="handleLogin" class="login-form">
          <div class="form-group">
            <label>用户名</label>
            <div class="input-wrap">
              <span class="input-icon"><AppIcon name="user"/></span>
              <input
                v-model="form.username"
                class="tech-input"
                placeholder="请输入用户名"
                autocomplete="username"
              />
            </div>
          </div>

          <div class="form-group">
            <label>密码</label>
            <div class="input-wrap">
              <span class="input-icon"><AppIcon name="lock"/></span>
              <input
                v-model="form.password"
                :type="showPwd ? 'text' : 'password'"
                class="tech-input"
                placeholder="请输入密码"
                autocomplete="current-password"
              />
              <button type="button" class="pwd-toggle" @click="showPwd = !showPwd">
                <AppIcon :name="showPwd ? 'eye-off' : 'eye'"/>
              </button>
            </div>
          </div>

          <div v-if="errorMsg" class="error-msg">
            <span><AppIcon name="warning"/> {{ errorMsg }}</span>
          </div>

          <button type="submit" class="btn-primary submit-btn" :disabled="loading">
            <span v-if="loading" class="loading-dot">◉ 登录中...</span>
            <span v-else>▶ 登 录</span>
          </button>
        </form>
      </div>
    </div>

    <!-- 底部 -->
    <div class="login-footer">
      EWBO 战队 · 设备检修知识检索与作业系统
    </div>
  </div>
</template>

<script setup>
import { authApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'

const store  = useUserStore()
const router = useRouter()

const form    = reactive({ username: '', password: '' })
const loading = ref(false)
const showPwd = ref(false)
const errorMsg = ref('')

const features = [
  { text: '多模态智能诊断，故障秒级定位' },
  { text: '海量检修知识，一问即得方案' },
  { text: '标准化作业指引，新手也能规范操作' },
  { text: '现场经验数字沉淀，老师傅手艺不失传' },
]

async function handleLogin() {
  if (!form.username || !form.password) {
    errorMsg.value = '请填写用户名和密码'
    return
  }
  loading.value  = true
  errorMsg.value = ''
  try {
    const res = await authApi.login({ username: form.username, password: form.password })
    store.setToken(res.access_token)
    await store.fetchMe()
    showToast({ message: '登录成功', type: 'success' })
    router.push('/')
  } catch (e) {
    errorMsg.value = e?.response?.data?.detail || '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  padding: 20px;
}

.bg-circles .circle {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(34,221,255,0.08);
  animation: slow-rotate 20s linear infinite;
}
.c1 { width: 600px; height: 600px; top: -200px; right: -200px; }
.c2 { width: 400px; height: 400px; bottom: -100px; left: -100px; animation-direction: reverse; }
.c3 { width: 200px; height: 200px; top: 50%; left: 30%; animation-duration: 30s; }
@keyframes slow-rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.login-container {
  display: flex;
  max-width: 900px;
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-card), 0 0 60px rgba(34,221,255,0.05);
  position: relative;
  z-index: 1;
}

/* 左侧品牌 */
.login-brand {
  flex: 1;
  background: linear-gradient(135deg, #243150 0%, #2c3c61 100%);
  border-right: 1px solid var(--border-color);
  padding: 48px 36px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.brand-logo {
  filter: drop-shadow(0 0 12px rgba(34,221,255,0.5));
}
.brand-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.4;
}
.brand-subtitle {
  font-size: 13px;
  color: var(--accent-cyan);
  letter-spacing: 0.15em;
  opacity: 0.7;
}
.brand-features { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
.feature-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  color: var(--text-secondary);
}
.brand-badge {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(34,221,255,0.06);
  border: 1px solid rgba(34,221,255,0.2);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  font-size: 14px;
  color: var(--text-secondary);
  letter-spacing: 0.05em;
}
.team-tag {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.18em;
  color: var(--accent-cyan);
  text-shadow: 0 0 12px rgba(34,221,255,0.5);
}

/* 右侧表单 */
.login-form-wrap {
  width: 360px;
  padding: 48px 36px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.form-header h2 { font-size: 22px; font-weight: 700; color: var(--text-primary); }
.form-header p  { font-size: 13px; color: var(--text-muted); letter-spacing: 0.15em; margin-top: 4px; }

.login-form { display: flex; flex-direction: column; gap: 16px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 14px; color: var(--text-secondary); letter-spacing: 0.05em; }

.input-wrap { position: relative; display: flex; align-items: center; }
.input-icon { position: absolute; left: 12px; font-size: 16px; }
.input-wrap .tech-input { padding-left: 36px; }
.pwd-toggle {
  position: absolute; right: 10px;
  background: none; border: none; cursor: pointer; font-size: 16px; padding: 2px;
}

.error-msg {
  background: rgba(255,71,87,0.08);
  border: 1px solid rgba(255,71,87,0.3);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 14px;
  color: var(--accent-red);
}

.submit-btn { width: 100%; padding: 12px; font-size: 15px; letter-spacing: 0.1em; margin-top: 4px; }

.login-footer {
  margin-top: 24px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  letter-spacing: 0.05em;
  position: relative;
  z-index: 1;
}

@media (max-width: 768px) {
  .login-brand { display: none; }
  .login-form-wrap { width: 100%; }
}
</style>
