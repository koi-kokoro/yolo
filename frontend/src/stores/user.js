import { defineStore } from 'pinia'

import { getCurrentUser, login as loginApi } from '@/api/auth'

export const TOKEN_KEY = 'rsod_token'
export const USER_KEY = 'rsod_user'
const LEGACY_TOKEN_KEY = 'token'
const LEGACY_USER_KEY = 'user'

function cleanupLegacyAuth() {
  localStorage.removeItem(LEGACY_TOKEN_KEY)
  localStorage.removeItem(LEGACY_USER_KEY)
}

function readStoredUser() {
  const rawUser = localStorage.getItem(USER_KEY)

  if (!rawUser) return null

  try {
    return JSON.parse(rawUser)
  } catch {
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export function clearStoredAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  cleanupLegacyAuth()
}

export const useUserStore = defineStore('user', {
  state: () => {
    cleanupLegacyAuth()

    return {
      token: localStorage.getItem(TOKEN_KEY) || '',
      user: readStoredUser(),
    }
  },
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    username: (state) => state.user?.username || '',
  },
  actions: {
    setAuth({ access_token, user }) {
      this.token = access_token
      this.user = user
      localStorage.setItem(TOKEN_KEY, access_token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
      cleanupLegacyAuth()
    },
    async login(payload) {
      const data = await loginApi(payload)
      this.setAuth(data)
      return data
    },
    async fetchUserInfo() {
      if (!this.token) return null

      const user = await getCurrentUser()
      this.user = user
      localStorage.setItem(USER_KEY, JSON.stringify(user))
      return user
    },
    logout() {
      this.token = ''
      this.user = null
      clearStoredAuth()
    },
  },
})
