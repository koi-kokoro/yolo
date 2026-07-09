import request from '@/utils/request'

export function register(data) {
  return request.post('/auth/register', data)
}

export function login(data) {
  return request.post('/auth/login', data)
}

export function getCurrentUser() {
  return request.get('/auth/me')
}

export const registerApi = register
export const loginApi = login
export const getUserInfoApi = getCurrentUser
