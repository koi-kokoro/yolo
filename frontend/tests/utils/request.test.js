import { ElMessage } from 'element-plus'

import request from '../../src/utils/request'

describe('utils/request', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates axios instance with frontend API defaults', () => {
    expect(request.defaults.baseURL).toBe('/api')
    expect(request.defaults.timeout).toBe(30000)
  })

  it('adds bearer token from localStorage in request interceptor', async () => {
    localStorage.setItem('rsod_token', 'test-token')

    const config = await request.interceptors.request.handlers[0].fulfilled({ headers: {} })

    expect(config.headers.Authorization).toBe('Bearer test-token')
  })

  it('unwraps response data in response interceptor', () => {
    const response = { data: { ok: true } }

    expect(request.interceptors.response.handlers[0].fulfilled(response)).toEqual({ ok: true })
  })

  it('clears auth and redirects to login on 401 response', async () => {
    localStorage.setItem('rsod_token', 'test-token')
    localStorage.setItem('rsod_user', JSON.stringify({ username: 'demo' }))
    localStorage.setItem('token', 'legacy-token')
    localStorage.setItem('user', JSON.stringify({ username: 'legacy' }))

    const replace = vi.fn()
    vi.stubGlobal('location', {
      pathname: '/chat',
      replace,
    })

    const error = {
      message: 'Unauthorized',
      response: {
        status: 401,
        data: { detail: '登录已过期' },
      },
    }

    await expect(request.interceptors.response.handlers[0].rejected(error)).rejects.toBe(error)

    expect(localStorage.getItem('rsod_token')).toBeNull()
    expect(localStorage.getItem('rsod_user')).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(replace).toHaveBeenCalledWith('/login')
    expect(ElMessage.error).toHaveBeenCalledWith('登录已过期')
  })
})
