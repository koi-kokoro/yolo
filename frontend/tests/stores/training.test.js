import { createPinia, setActivePinia } from 'pinia'
import { createTrainingTask, getTrainingMetrics, getTrainingTask, listTrainingTasks, stopTrainingTask } from '@/api/training'
import { mergeMetrics, TRAINING_POLL_INTERVAL, useTrainingStore } from '@/stores/training'

vi.mock('@/api/training', () => ({
  createTrainingTask: vi.fn(), getTrainingMetrics: vi.fn(), getTrainingTask: vi.fn(), listTrainingTasks: vi.fn(), stopTrainingTask: vi.fn(),
}))

const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() }

describe('training store', () => {
  beforeEach(() => {
    setActivePinia(createPinia()); vi.useFakeTimers(); vi.clearAllMocks()
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    listTrainingTasks.mockResolvedValue({ total: 0, items: [] })
    getTrainingMetrics.mockResolvedValue({ metrics: [] })
  })
  afterEach(() => vi.useRealTimers())

  it('按 epoch 去重覆盖并排序，缺失 epoch 不混入', () => {
    expect(mergeMetrics([{ epoch: 2, miou: .2 }, { epoch: 1, miou: .1 }], [{ epoch: 2, miou: .25 }, { epoch: 3 }])).toEqual([
      { epoch: 1, miou: .1 }, { epoch: 2, miou: .25 }, { epoch: 3 },
    ])
  })

  it('创建后立即选中，轮询使用增量 after_epoch，终态最后刷新后停止', async () => {
    const store = useTrainingStore()
    createTrainingTask.mockResolvedValue({ id: 1, status: 'running', current_epoch: 1 })
    getTrainingTask.mockResolvedValueOnce({ id: 1, status: 'running', current_epoch: 2 }).mockResolvedValueOnce({ id: 1, status: 'completed', current_epoch: 3 })
    getTrainingMetrics.mockResolvedValueOnce({ metrics: [{ epoch: 2, miou: .4 }] }).mockResolvedValueOnce({ metrics: [{ epoch: 3, miou: .5 }] })
    await store.createTask({ dataset_key: 'smoke' })
    store.metrics = [{ epoch: 1, miou: .3 }]
    await vi.advanceTimersByTimeAsync(TRAINING_POLL_INTERVAL); await flush()
    expect(getTrainingMetrics).toHaveBeenNthCalledWith(1, 1, 1)
    await vi.advanceTimersByTimeAsync(TRAINING_POLL_INTERVAL); await flush()
    expect(getTrainingMetrics).toHaveBeenNthCalledWith(2, 1, 2)
    expect(store.metrics.map((item) => item.epoch)).toEqual([1, 2, 3])
    expect(store.polling).toBe(false)
  })

  it('防止并发，单次失败保留曲线并继续调度', async () => {
    const store = useTrainingStore(); store.selectedTask = { id: 2, status: 'running' }; store.metrics = [{ epoch: 1 }]
    let resolveTask
    getTrainingTask.mockReturnValue(new Promise((resolve) => { resolveTask = resolve }))
    store.startPolling(); await vi.advanceTimersByTimeAsync(TRAINING_POLL_INTERVAL)
    await vi.advanceTimersByTimeAsync(TRAINING_POLL_INTERVAL)
    expect(getTrainingTask).toHaveBeenCalledTimes(1)
    resolveTask({ id: 2, status: 'running' }); await flush()
    expect(store.metrics).toEqual([{ epoch: 1 }])
  })

  it('隐藏暂停、恢复立即刷新，dispose 清理监听与 timer', async () => {
    const store = useTrainingStore(); store.selectedTask = { id: 4, status: 'running' }
    getTrainingTask.mockResolvedValue({ id: 4, status: 'running' })
    store.initVisibilityHandling(); store.startPolling()
    Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(TRAINING_POLL_INTERVAL * 2)
    expect(getTrainingTask).not.toHaveBeenCalled()
    Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')); await flush()
    expect(getTrainingTask).toHaveBeenCalledTimes(1)
    store.dispose(); expect(store.pollTimer).toBeNull(); expect(store.visibilityHandler).toBeNull()
  })

  it('活动状态才允许停止', async () => {
    const store = useTrainingStore(); store.selectedTask = { id: 9, status: 'running' }
    stopTrainingTask.mockResolvedValue({ id: 9, status: 'stopping' })
    await store.stopSelected(); expect(stopTrainingTask).toHaveBeenCalledWith(9)
  })
})
