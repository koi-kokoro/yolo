import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'rsod_token'
const USER_KEY = 'rsod_user'
const LEGACY_TOKEN_KEY = 'token'
const LEGACY_USER_KEY = 'user'

function clearStoredAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(LEGACY_TOKEN_KEY)
  localStorage.removeItem(LEGACY_USER_KEY)
}

const service = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

service.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

service.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.message || error.response?.data?.detail || error.message || '请求失败'

    if (error.response?.status === 401) {
      clearStoredAuth()

      if (window.location.pathname !== '/login') {
        window.location.replace('/login')
      }
    }

    ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default service
