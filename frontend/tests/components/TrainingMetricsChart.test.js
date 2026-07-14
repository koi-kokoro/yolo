import { mount } from '@vue/test-utils'
import { buildTrainingChartOption, metricValue } from '@/components/training/trainingChartOptions'

const dispose = vi.fn(); const resize = vi.fn(); const setOption = vi.fn(); const clear = vi.fn()
vi.mock('echarts/core', () => ({ use: vi.fn(), init: vi.fn(() => ({ dispose, resize, setOption, clear })) }))
vi.mock('echarts/charts', () => ({ LineChart: {} }))
vi.mock('echarts/components', () => ({ GridComponent: {}, LegendComponent: {}, TooltipComponent: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

describe('TrainingMetricsChart', () => {
  it('缺失值严格映射为 null，不伪造 0', () => {
    expect(metricValue(undefined)).toBeNull(); expect(metricValue(null)).toBeNull(); expect(metricValue(0)).toBe(0)
    const option = buildTrainingChartOption([{ epoch: 1, miou: null }, { epoch: 2, miou: .5 }])
    expect(option.series.find((s) => s.name === 'mIoU').data).toEqual([null, .5])
    expect(option.yAxis[1].name).toContain('%')
  })

  it('有数据时 setOption，卸载 dispose', async () => {
    const component = (await import('@/components/training/TrainingMetricsChart.vue')).default
    const wrapper = mount(component, { props: { metrics: [{ epoch: 1, train_ce_loss: 1 }] }, global: { stubs: { ElEmpty: true } } })
    await wrapper.vm.$nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(setOption).toHaveBeenCalled(); wrapper.unmount(); expect(dispose).toHaveBeenCalled()
  })
})
