import { defineStore } from 'pinia'
import { authApi } from '@/api'

export const useUserStore = defineStore('user', {
  state: () => ({
    token:    localStorage.getItem('token') || null,
    userInfo: null,
    role:     localStorage.getItem('role')  || null,
  }),

  getters: {
    isAdmin:       (s) => s.role === 'admin',
    isFieldWorker: (s) => s.role === 'field_worker',
    isLoggedIn:    (s) => !!s.token,
    displayName:   (s) => s.userInfo?.real_name || s.userInfo?.username || '用户',
  },

  actions: {
    setToken(token) {
      this.token = token
      localStorage.setItem('token', token)
    },

    setUserInfo(info) {
      this.userInfo = info
      this.role = info.role
      localStorage.setItem('role', info.role)
    },

    async fetchMe() {
      try {
        const data = await authApi.me()
        this.setUserInfo(data)
        return data
      } catch {
        this.logout()
      }
    },

    logout() {
      this.token    = null
      this.userInfo = null
      this.role     = null
      localStorage.removeItem('token')
      localStorage.removeItem('role')
    },
  },
})
