import { mount } from '@vue/test-utils'

import AppHeader from '../../src/components/layout/AppHeader.vue'

const push = vi.fn()
const logout = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push,
  }),
}))

vi.mock('../../src/stores/user', () => ({
  useUserStore: () => ({
    username: '测试用户',
    logout,
  }),
}))

describe('AppHeader', () => {
  it('can be imported and mounted with mocked router and store', () => {
    const wrapper = mount(AppHeader, {
      global: {
        stubs: {
          ElDropdown: {
            template: '<div><slot /><slot name="dropdown" /></div>',
          },
          ElDropdownMenu: {
            template: '<div><slot /></div>',
          },
          ElDropdownItem: {
            template: '<button type="button"><slot /></button>',
          },
          ElIcon: {
            template: '<i><slot /></i>',
          },
          ArrowDown: true,
        },
      },
    })

    expect(wrapper.find('.app-header').exists()).toBe(true)
    expect(wrapper.text()).toContain('测试用户')
  })

  it('emits a toggle event from the sidebar button', async () => {
    const wrapper = mount(AppHeader, {
      props: {
        sidebarCollapsed: false,
      },
      global: {
        stubs: {
          ElDropdown: { template: '<div><slot /><slot name="dropdown" /></div>' },
          ElDropdownMenu: { template: '<div><slot /></div>' },
          ElDropdownItem: { template: '<button type="button"><slot /></button>' },
          ElIcon: { template: '<i><slot /></i>' },
          Fold: true,
        },
      },
    })

    const toggle = wrapper.find('.app-header__sidebar-toggle')
    expect(toggle.attributes('aria-label')).toBe('隐藏任务栏')
    await toggle.trigger('click')
    expect(wrapper.emitted('toggle-sidebar')).toHaveLength(1)
  })
})
