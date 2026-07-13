import { mount } from '@vue/test-utils'
import SemanticResultViewer from '@/components/semantic/SemanticResultViewer.vue'

const stubs = { 'el-empty': true, 'el-result': true, 'el-icon': true, 'el-segmented': true, 'el-image': { template: '<img :src="$attrs.src" />' } }

describe('SemanticResultViewer', () => {
  it('shows running state without result images', () => {
    const wrapper = mount(SemanticResultViewer, { props: { task: { status: 'running' } }, global: { stubs } })
    expect(wrapper.text()).toContain('模型推理中')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('shows failed state', () => {
    const wrapper = mount(SemanticResultViewer, { props: { task: { status: 'failed', error: { message: '模型异常' } } }, global: { stubs: { ...stubs, 'el-result': { props: ['title', 'subTitle'], template: '<div>{{ title }} {{ subTitle }}</div>' } } } })
    expect(wrapper.text()).toContain('模型异常')
  })

  it('renders all signed result links on success', () => {
    const task = { status: 'succeeded', source_url: 'source.png', result: { index_mask_url: 'index.png', color_mask_url: 'color.png', overlay_url: 'overlay.png' } }
    const wrapper = mount(SemanticResultViewer, { props: { task }, global: { stubs } })
    expect(wrapper.findAll('a')).toHaveLength(4)
    expect(wrapper.text()).toContain('打开索引 Mask')
    expect(wrapper.text()).toContain('打开叠加图')
  })
})
