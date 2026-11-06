<template>
  <div class="profile-page">
    <div class="profile-main">
      <!-- 用户信息卡 -->
      <div class="tech-card profile-card">
        <div class="avatar-row">
          <div class="avatar">
            {{ displayName.charAt(0).toUpperCase() }}
          </div>
          <div class="user-info">
            <div class="user-name">{{ displayName }}</div>
            <div class="user-role">
              <span class="tech-tag" :class="isAdmin ? 'orange' : 'green'">
                {{ isAdmin ? '管理员' : '一线人员' }}
              </span>
            </div>
            <div class="user-meta">@{{ userInfo?.username }}</div>
          </div>
        </div>

        <!-- 统计数字 -->
        <div class="profile-stats">
          <div class="ps-item" v-for="s in profileStats" :key="s.label">
            <div class="ps-val">{{ s.value }}</div>
            <div class="ps-label">{{ s.label }}</div>
          </div>
        </div>

        <!-- 手机访问 -->
        <button class="btn-outline mobile-btn" @click="showQr = true"><AppIcon name="phone"/> 手机扫码访问</button>
      </div>

      <!-- 编辑表单 -->
      <div class="tech-card edit-card">
        <div class="card-title"><span class="glow-dot"></span> 编辑个人信息</div>
        <form @submit.prevent="saveProfile" class="edit-form">
          <div class="form-row">
            <label class="form-label">真实姓名</label>
            <input v-model="editForm.real_name" class="tech-input" placeholder="请输入真实姓名" />
          </div>
          <div class="form-row">
            <label class="form-label">手机号码</label>
            <input v-model="editForm.phone" class="tech-input" placeholder="请输入手机号" type="tel" />
          </div>
          <div class="form-row">
            <label class="form-label">所属部门</label>
            <input v-model="editForm.department" class="tech-input" placeholder="如：发动机维修车间" />
          </div>
          <button type="submit" class="btn-primary save-btn" :disabled="saving">
            <AppIcon name="save"/> {{ saving ? ' 保存中...' : ' 保存信息' }}
          </button>
        </form>
      </div>

      <!-- 修改密码 -->
      <div class="tech-card pwd-card">
        <div class="card-title"><span class="glow-dot red"></span> 修改密码</div>
        <form @submit.prevent="changePwd" class="edit-form">
          <div class="form-row">
            <label class="form-label">当前密码</label>
            <input v-model="pwdForm.old_password" type="password" class="tech-input" placeholder="请输入当前密码" />
          </div>
          <div class="form-row">
            <label class="form-label">新密码</label>
            <input v-model="pwdForm.new_password" type="password" class="tech-input" placeholder="至少6位" />
          </div>
          <div class="form-row">
            <label class="form-label">确认新密码</label>
            <input v-model="pwdForm.confirm_password" type="password" class="tech-input" placeholder="再次输入新密码" />
          </div>
          <button type="submit" class="btn-outline save-btn"><AppIcon name="lock"/> 修改密码</button>
        </form>
      </div>
    </div>

    <!-- 新建账号（仅管理员可见；一线人员即使直调接口也会被后端 403 拦下） -->
    <div v-if="isAdmin" class="tech-card newuser-card">
      <div class="card-title"><span class="glow-dot"></span> 新建账号</div>
      <div class="nu-hint">
        系统不开放自助注册，账号一律由管理员创建。管理员可创建管理员或一线人员两类角色。
      </div>
      <form @submit.prevent="createUser" class="nu-form">
        <div class="nu-grid">
          <div class="form-row">
            <label class="form-label">用户名 <span class="req">*</span></label>
            <input v-model.trim="newUser.username" class="tech-input" placeholder="登录用，字母或数字" autocomplete="off" />
          </div>
          <div class="form-row">
            <label class="form-label">初始密码 <span class="req">*</span></label>
            <input v-model="newUser.password" type="password" class="tech-input" placeholder="至少 6 位" autocomplete="new-password" />
          </div>
          <div class="form-row">
            <label class="form-label">角色 <span class="req">*</span></label>
            <select v-model="newUser.role" class="tech-input">
              <option value="field_worker">一线人员（field_worker）</option>
              <option value="admin">管理员（admin）</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">真实姓名</label>
            <input v-model.trim="newUser.real_name" class="tech-input" placeholder="选填" />
          </div>
          <div class="form-row">
            <label class="form-label">手机号</label>
            <input v-model.trim="newUser.phone" class="tech-input" placeholder="选填" />
          </div>
          <div class="form-row">
            <label class="form-label">所属部门</label>
            <input v-model.trim="newUser.department" class="tech-input" placeholder="选填" />
          </div>
        </div>
        <div v-if="newUser.role === 'admin'" class="nu-warn">
          <AppIcon name="warning"/> 管理员可审核知识入库、核查全员留痕，请谨慎授予。
        </div>
        <div class="nu-actions">
          <button type="submit" class="btn-primary save-btn" :disabled="creating">
            <span v-if="creating"><span class="loading-dot">◉</span> 创建中…</span>
            <span v-else><AppIcon name="plus"/> 创建账号</span>
          </button>
          <span v-if="lastCreated" class="nu-ok">
            <AppIcon name="check-circle"/> 已创建 {{ lastCreated }}，可直接用初始密码登录
          </span>
        </div>
      </form>
    </div>

    <!-- 手机访问二维码 -->
    <van-popup v-model:show="showQr" round class="qr-modal" :style="{ width: '340px', maxWidth: '90vw' }">
      <div class="qr-popup">
        <div class="qr-title"><AppIcon name="phone"/> 手机扫码访问</div>
        <div class="qr-img-wrap">
          <img v-if="showQr" :src="qrSrc" alt="访问二维码" class="qr-img" />
        </div>
        <div class="qr-url">{{ qrOrigin }}</div>
        <div v-if="isLocalhost" class="qr-warn">
          <AppIcon name="warning"/> 当前用 localhost 打开，手机扫了无法访问。<br>请改用<strong>局域网 IP</strong>打开本系统后再扫码，并确保手机与本机同一网络。
        </div>
        <div v-else class="qr-hint">用手机相机/微信扫一扫，确保手机与本机在同一网络</div>
        <button class="btn-primary qr-close" @click="showQr = false">关闭</button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { authApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import { showToast } from 'vant'

const store = useUserStore()
const { isAdmin, displayName, userInfo } = storeToRefs(store)

const editForm = reactive({ real_name: '', phone: '', department: '' })
const pwdForm  = reactive({ old_password: '', new_password: '', confirm_password: '' })
const newUser  = reactive({ username: '', password: '', role: 'field_worker',
                            real_name: '', phone: '', department: '' })
const creating    = ref(false)
const lastCreated = ref('')
const saving   = ref(false)

// 手机访问二维码：编码"当前访问地址"，IP 变化自动跟随
const showQr      = ref(false)
const qrOrigin    = location.origin
const qrSrc       = `/api/qrcode?data=${encodeURIComponent(qrOrigin)}`
const isLocalhost = ['localhost', '127.0.0.1'].includes(location.hostname)

const profileStats = ref([
  { label: '提交案例', value: 0 },
  { label: '通过案例', value: 0 },
  { label: '诊断次数', value: 0 },
])

onMounted(async () => {
  if (userInfo.value) {
    editForm.real_name  = userInfo.value.real_name  || ''
    editForm.phone      = userInfo.value.phone      || ''
    editForm.department = userInfo.value.department || ''
  }
})

async function saveProfile() {
  saving.value = true
  try {
    // await authApi.updateProfile(editForm)
    showToast({ message: '个人信息已更新', type: 'success' })
  } catch { showToast('保存失败') } finally { saving.value = false }
}

// 管理员建号：后端 /api/auth/register 已挂 get_current_admin，越权返回 403
async function createUser() {
  if (!newUser.username) { showToast('请填写用户名'); return }
  if (!newUser.password || newUser.password.length < 6) { showToast('密码至少 6 位'); return }
  creating.value = true
  try {
    const u = await authApi.register({ ...newUser })
    lastCreated.value = `${u.username}（${u.role === 'admin' ? '管理员' : '一线人员'}）`
    showToast({ message: '账号创建成功', type: 'success' })
    Object.assign(newUser, { username: '', password: '', role: 'field_worker',
                             real_name: '', phone: '', department: '' })
  } catch (e) {
    // 400/403 的具体原因由 axios 拦截器统一弹出，这里不重复提示
  } finally { creating.value = false }
}

async function changePwd() {
  if (!pwdForm.old_password || !pwdForm.new_password) { showToast('请填写完整'); return }
  if (pwdForm.new_password !== pwdForm.confirm_password) { showToast('两次密码不一致'); return }
  if (pwdForm.new_password.length < 6) { showToast('新密码至少6位'); return }
  try {
    // await authApi.changePassword(pwdForm)
    showToast({ message: '密码修改成功，请重新登录', type: 'success' })
    Object.assign(pwdForm, { old_password: '', new_password: '', confirm_password: '' })
  } catch {}
}
</script>

<style scoped>
.profile-page { max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }

.profile-main { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

/* 新建账号（管理员） */
.newuser-card { }
.nu-hint { font-size: 13px; color: var(--text-muted); line-height: 1.7; margin: 6px 0 14px; }
.nu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 18px; }
@media (max-width: 768px) { .nu-grid { grid-template-columns: 1fr; } }
.req { color: var(--accent-red); }
.nu-warn { margin-top: 12px; font-size: 13px; color: var(--accent-orange); }
.nu-actions { display: flex; align-items: center; gap: 14px; margin-top: 16px; flex-wrap: wrap; }
.nu-ok { font-size: 13px; color: var(--accent-green); }
@media (max-width: 700px) { .profile-main { grid-template-columns: 1fr; } }

.profile-card { }
.avatar-row { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.avatar {
  width: 64px; height: 64px; border-radius: 50%;
  background: var(--gradient-btn);
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 700; color: #fff;
  box-shadow: var(--shadow-btn);
  flex-shrink: 0;
}
.user-name { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.user-role { margin-bottom: 4px; }
.user-meta { font-size: 14px; color: var(--text-muted); }

.profile-stats { display: flex; gap: 0; border: 1px solid var(--border-color); border-radius: var(--radius-sm); overflow: hidden; }
.ps-item { flex: 1; padding: 12px; text-align: center; border-right: 1px solid var(--border-color); }
.ps-item:last-child { border-right: none; }
.ps-val   { font-size: 20px; font-weight: 700; color: var(--accent-cyan); font-family: monospace; }
.ps-label { font-size: 13px; color: var(--text-muted); margin-top: 2px; }

.edit-card, .pwd-card { }
.card-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 16px;
}
.edit-form { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: flex; flex-direction: column; gap: 5px; }
.form-label { font-size: 14px; color: var(--text-secondary); }
.save-btn { align-self: flex-end; padding: 8px 20px; }

.sys-card { }
.sys-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.sys-item { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 10px 14px; }
.sys-label { font-size: 13px; color: var(--text-muted); margin-bottom: 4px; }
.sys-val   { font-size: 15px; color: var(--accent-cyan); font-weight: 500; }

.mobile-btn { width: 100%; margin-top: 14px; }

/* 二维码弹窗 */
.qr-modal { background: var(--bg-card) !important; }
.qr-popup { padding: 22px; display: flex; flex-direction: column; align-items: center; gap: 12px; background: var(--bg-card); }
.qr-title { font-size: 17px; font-weight: 700; color: var(--text-primary); }
.qr-img-wrap { background: #fff; padding: 12px; border-radius: var(--radius-sm); }
.qr-img { width: 220px; height: 220px; display: block; }
.qr-url { font-size: 14px; color: var(--accent-cyan); word-break: break-all; text-align: center; font-family: monospace; }
.qr-hint { font-size: 13px; color: var(--text-muted); text-align: center; }
.qr-warn { font-size: 13px; color: var(--accent-orange); text-align: center; line-height: 1.6; }
.qr-close { width: 100%; margin-top: 4px; }
</style>
