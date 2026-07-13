import { createPinia, setActivePinia } from 'pinia'

import { useSemanticStore } from '@/stores/semantic'
import { createSemanticTask, getSemanticTask, listSemanticTasks } from '@/api/semantic'

vi.mock('@/api/semantic', () => ({
  createSemanticTask: vi.fn(), getSemanticTask: vi.fn(), listSemanticTasks: vi.fn(), getSemanticModelInfo: vi.fn(),
}))

const flush = async () => {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

describe('semantic store polling', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.clearAllMocks()
    listSemanticTasks.mockResolvedValue({ total: 0, page: 1, page_size: 20, total_pages: 0, items: [] })
  })
  afterEach(() => vi.useRealTimers())

  it('creates FormData and stops polling on success', async () => {
    const store = useSemanticStore()
    store.modelInfo = { ready: true }
    const file = new File(['image'], 'tile.png', { type: 'image/png' })
    createSemanticTask.mockResolvedValue({ task_uuid: 'u1', status: 'pending' })
    getSemanticTask.mockResolvedValue({ task_uuid: 'u1', status: 'succeeded', result: {} })

    await store.createTask(file)
    await flush()

    expect(createSemanticTask.mock.calls[0][0]).toBeInstanceOf(FormData)
    expect(createSemanticTask.mock.calls[0][0].get('file')).toBe(file)
    expect(store.currentTask.status).toBe('succeeded')
    expect(store.polling).toBe(false)
    expect(store.pollTimer).toBeNull()
  })

  it('stops on failed terminal state and exposes error', async () => {
    const store = useSemanticStore()
    getSemanticTask.mockResolvedValue({ task_uuid: 'u2', status: 'failed', error: { message: '推理失败' } })
    store.startPolling('u2')
    await flush()
    expect(store.polling).toBe(false)
    expect(store.error).toBe('推理失败')
  })

  it('cleans timer and ignores stale polling when disposed', async () => {
    const store = useSemanticStore()
    getSemanticTask.mockResolvedValue({ task_uuid: 'u3', status: 'running' })
    store.startPolling('u3')
    await flush()
    expect(store.pollTimer).not.toBeNull()
    store.dispose()
    expect(store.polling).toBe(false)
    expect(store.pollTimer).toBeNull()
    await vi.advanceTimersByTimeAsync(12000)
    expect(getSemanticTask).toHaveBeenCalledTimes(1)
  })
})
