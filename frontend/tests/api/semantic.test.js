import request from '@/utils/request'
import { createSemanticTask, getSemanticModelInfo, getSemanticTask, listSemanticTasks } from '@/api/semantic'

vi.mock('@/utils/request', () => ({ default: vi.fn() }))

describe('semantic api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends multipart create payload', () => {
    const formData = new FormData()
    createSemanticTask(formData)
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: '/semantic-tasks', method: 'post', data: formData,
      headers: { 'Content-Type': 'multipart/form-data' },
    }))
  })

  it('sends list params and detail/model-info paths', () => {
    listSemanticTasks({ page: 2, page_size: 10, status: 'succeeded' })
    getSemanticTask('task-uuid')
    getSemanticModelInfo()
    expect(request).toHaveBeenNthCalledWith(1, expect.objectContaining({ params: { page: 2, page_size: 10, status: 'succeeded' } }))
    expect(request).toHaveBeenNthCalledWith(2, { url: '/semantic-tasks/task-uuid', method: 'get' })
    expect(request).toHaveBeenNthCalledWith(3, { url: '/semantic-tasks/model-info', method: 'get' })
  })
})
