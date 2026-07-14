import request from '@/utils/request'
import { createTrainingTask, downloadTrainingArtifact, getTrainingMetrics, getTrainingTask, listTrainingTasks, stopTrainingTask } from '@/api/training'

vi.mock('@/utils/request', () => ({ default: vi.fn() }))

describe('training api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('封装任务 CRUD 与增量指标参数', () => {
    const payload = { model: 'yolo26n-sem.pt', dataset_key: 'full' }
    createTrainingTask(payload); listTrainingTasks(); getTrainingTask(3); getTrainingMetrics(3, 7); stopTrainingTask(3)
    expect(request).toHaveBeenNthCalledWith(1, { url: '/training/tasks', method: 'post', data: payload })
    expect(request).toHaveBeenNthCalledWith(2, { url: '/training/tasks', method: 'get' })
    expect(request).toHaveBeenNthCalledWith(3, { url: '/training/tasks/3', method: 'get' })
    expect(request).toHaveBeenNthCalledWith(4, { url: '/training/tasks/3/metrics', method: 'get', params: { after_epoch: 7 } })
    expect(request).toHaveBeenNthCalledWith(5, { url: '/training/tasks/3/stop', method: 'post' })
  })

  it('下载沿用 request 认证错误约定并校验、编码产物名', () => {
    downloadTrainingArtifact(8, 'best.pt')
    expect(request).toHaveBeenCalledWith({ url: '/training/tasks/8/artifacts/best.pt', method: 'get', responseType: 'blob' })
    expect(() => downloadTrainingArtifact(8, '../best.pt')).toThrow('训练产物名称无效')
    expect(() => downloadTrainingArtifact('x', 'best.pt')).toThrow('训练任务 ID 无效')
  })
})
