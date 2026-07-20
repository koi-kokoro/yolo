import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import SettingsPage from '../../src/views/SettingsPage.vue'
import request from '../../src/utils/request'

vi.mock('../../src/utils/request', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))

const InputStub = defineComponent({
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
    disabled: Boolean,
  },
  template: '<input :value="modelValue" :disabled="disabled" />',
})

function mountPage() {
  setActivePinia(createPinia())
  return mount(SettingsPage, {
    global: {
      stubs: {
        'el-row': { template: '<div><slot /></div>' },
        'el-col': { template: '<div><slot /></div>' },
        'el-card': { template: '<section><slot name="header" /><slot /></section>' },
        'el-form': { template: '<form><slot /></form>' },
        'el-form-item': { template: '<label><slot /></label>' },
        'el-input': InputStub,
        'el-button': { template: '<button><slot /></button>' },
        'el-descriptions': { template: '<dl><slot /></dl>' },
        'el-descriptions-item': { template: '<div><slot /></div>' },
      },
    },
  })
}

async function flushUserInfo() {
  await Promise.resolve()
  await nextTick()
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    [false, '普通用户'],
    [true, '管理员'],
  ])('shows a read-only user type when is_superuser is %s', async (isSuperuser, expectedType) => {
    request.get.mockResolvedValue({
      username: 'test-user',
      email: 'test@example.com',
      phone: '',
      created_at: '2026-07-20T00:00:00',
      is_superuser: isSuperuser,
    })

    const wrapper = mountPage()
    await flushUserInfo()

    const userTypeInput = wrapper
      .findAll('input')
      .find((input) => input.element.value === expectedType)

    expect(request.get).toHaveBeenCalledWith('/auth/me')
    expect(userTypeInput).toBeDefined()
    expect(userTypeInput.attributes('disabled')).toBeDefined()
  })
})
