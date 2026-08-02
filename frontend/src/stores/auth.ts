import { defineStore } from 'pinia'
import { login as loginApi } from '@/api/auth'
import { TOKEN_KEY, USERNAME_KEY } from '@/api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) ?? '',
    username: localStorage.getItem(USERNAME_KEY) ?? '',
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
  },
  actions: {
    async login(username: string, password: string) {
      const res = await loginApi(username, password)
      this.token = res.access_token
      this.username = username
      localStorage.setItem(TOKEN_KEY, res.access_token)
      localStorage.setItem(USERNAME_KEY, username)
    },
    logout() {
      this.token = ''
      this.username = ''
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USERNAME_KEY)
    },
  },
})
