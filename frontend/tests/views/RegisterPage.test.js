import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

import RegisterPage from '../../src/views/RegisterPage.vue'
import { register } from '../../src/api/auth'

const push = vi.fn()

vi.mock('../../src/api/auth', () => ({
  register: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

const FormStub = defineComponent({
  template: '<form><slot /></form>',
  setup(_, { expose }) {
    expose({ validate: vi.fn().mockResolvedValue(true) })
    return {}
  },
})

const InputStub = defineComponent({
  template: '<input />',
})

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    register.mockResolvedValue({})
  })

  it('submits the optional admin code without the confirmation password', async () => {
    const wrapper = mount(RegisterPage, {
      global: {
        stubs: {
          'el-form': FormStub,
          'el-form-item': { template: '<div><slot /></div>' },
          'el-input': InputStub,
          'el-button': { template: '<button><slot /></button>' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    Object.assign(wrapper.vm.form, {
      username: 'admin-user',
      email: 'admin@example.com',
      password: 'password123',
      confirmPassword: 'password123',
      admin_code: 'test-admin-code',
    })

    await wrapper.vm.handleSubmit()

    expect(register).toHaveBeenCalledWith({
      username: 'admin-user',
      email: 'admin@example.com',
      password: 'password123',
      admin_code: 'test-admin-code',
    })
    expect(register.mock.calls[0][0]).not.toHaveProperty('confirmPassword')
    expect(push).toHaveBeenCalledWith('/login')
  })

  it('keeps backend registration errors rejected for the shared error handler', async () => {
    const error = { response: { status: 400, data: { message: '管理员代码错误' } } }
    register.mockRejectedValue(error)

    const wrapper = mount(RegisterPage, {
      global: {
        stubs: {
          'el-form': FormStub,
          'el-form-item': { template: '<div><slot /></div>' },
          'el-input': InputStub,
          'el-button': { template: '<button><slot /></button>' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
    Object.assign(wrapper.vm.form, {
      username: 'bad-admin',
      email: 'bad-admin@example.com',
      password: 'password123',
      confirmPassword: 'password123',
      admin_code: 'wrong-code',
    })

    await expect(wrapper.vm.handleSubmit()).rejects.toBe(error)
    expect(push).not.toHaveBeenCalled()
  })
})
