import axios from 'axios'
import { showToast } from 'vant'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 90000, // 大模型响应可能较慢
})

// 请求拦截：注入 JWT
http.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：统一错误处理
http.interceptors.response.use(
  res => res.data,
  err => {
    const status = err.response?.status
    const detail = err.response?.data?.detail || '请求失败'

    if (status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/#/login'
      showToast('登录已过期，请重新登录')
    } else if (status === 403) {
      showToast('无访问权限')
    } else if (status >= 500) {
      showToast('服务器异常，请稍后重试')
    } else {
      showToast(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
    return Promise.reject(err)
  }
)

// ==================== Auth ====================
export const authApi = {
  login:    (data) => http.post('/auth/login', data),
  register: (data) => http.post('/auth/register', data),
  me:       ()     => http.get('/auth/me'),
  refresh:  ()     => http.post('/auth/refresh'),
}

// ==================== Diagnosis ====================
export const diagnosisApi = {
  analyze: (formData) => http.post('/diagnosis/analyze', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  }),
  history: (params) => http.get('/diagnosis/history', { params }),
  guideStep: (data) => http.post('/diagnosis/guide/step', data, { timeout: 120000 }),
  // 分步排查定论后，据根本原因即时生成现场维修作业方案（本地兜底模型可能较慢，放宽超时）
  repairPlan: (data) => http.post('/diagnosis/repair-plan', data, { timeout: 300000 }),
}

// ==================== Knowledge ====================
export const knowledgeApi = {
  search: (formData) => http.post('/knowledge/search', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  detail: (id)      => http.get(`/knowledge/${id}`),
  kgGraph: (id)     => http.get(`/knowledge/${id}/kg`),
  history: (params) => http.get('/knowledge/history', { params }),
}

// ==================== Documents（知识文档）====================
export const documentsApi = {
  upload:  (formData) => http.post('/documents', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000, // 大 PDF 解析较慢
  }),
  my:      (params)   => http.get('/documents/my', { params }),
  detail:  (id)       => http.get(`/documents/${id}`),
  delete:  (id)       => http.delete(`/documents/${id}`),
  pending: (params)   => http.get('/documents/pending', { params }),        // 管理员
  approve: (id, comment) => http.post(`/documents/${id}/approve`, { comment }, { timeout: 180000 }),
  reject:  (id, comment) => http.post(`/documents/${id}/reject`, { comment }),
}

// ==================== Cases ====================
export const casesApi = {
  create:   (formData) => http.post('/cases', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  myCases:  (params)   => http.get('/cases/my', { params }),
  detail:   (id)       => http.get(`/cases/${id}`),
  delete:   (id)       => http.delete(`/cases/${id}`),
}

// ==================== Audit ====================
export const auditApi = {
  pending:  (params) => http.get('/audit/pending', { params }),
  approve:  (id, comment) => http.post(`/audit/${id}/approve`, { comment }),
  reject:   (id, comment) => http.post(`/audit/${id}/reject`, { comment }),
  detail:   (id)          => http.get(`/audit/${id}`),
}

// ==================== Workflow ====================
export const workflowApi = {
  recommend: (params)    => http.get('/workflow/recommend', { params }),
  list:      (params)    => http.get('/workflow/templates', { params }),
  detail:    (id)        => http.get(`/workflow/templates/${id}`),
  create:    (data)      => http.post('/workflow/templates', data),
  update:    (id, data)  => http.put(`/workflow/templates/${id}`, data),
  delete:    (id)        => http.delete(`/workflow/templates/${id}`),
  startRecord:  (data)   => http.post('/workflow/records', data),
  updateRecord: (id, data) => http.put(`/workflow/records/${id}`, data),
  getRecord:    (id)     => http.get(`/workflow/records/${id}`),
  records:      (params) => http.get('/workflow/records', { params }),   // 作业留痕列表（scope=mine|all）
  completeRecord: (id)   => http.post(`/workflow/records/${id}/complete`),
  // 作业指引申请 → 审批 → AI 生成 → 发布
  createRequest:  (data)   => http.post('/workflow/requests', data),
  myRequests:     (params) => http.get('/workflow/requests/my', { params }),
  listRequests:   (params) => http.get('/workflow/requests', { params }),         // 管理员
  generateDraft:  (data)   => http.post('/workflow/generate', data, { timeout: 120000 }), // 管理员：AI 生成
  approveRequest: (id, data) => http.post(`/workflow/requests/${id}/approve`, data),
  rejectRequest:  (id, comment) => http.post(`/workflow/requests/${id}/reject`, { comment }),
}

// ==================== Feedback ====================
export const feedbackApi = {
  submit:  (data)   => http.post('/feedback', data),
  list:    (params) => http.get('/feedback', { params }),
  pending: (params) => http.get('/feedback/pending', { params }),   // 管理员：待采纳反馈
  adopt:   (id)     => http.post(`/feedback/${id}/adopt`),          // 管理员：采纳 → 注入诊断
}

// ==================== Upload ====================
export const uploadApi = {
  file: (formData) => http.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
}

// ==================== Devices ====================
export const devicesApi = {
  list:   (params)  => http.get('/devices', { params }),
  search: (keyword) => http.get('/devices/search', { params: { keyword } }),
  create: (data)    => http.post('/devices', data),
}

// ==================== Dashboard ====================
export const dashboardApi = {
  stats:    () => http.get('/admin/stats'),
  timeline: () => http.get('/admin/timeline'),
}

export default http
