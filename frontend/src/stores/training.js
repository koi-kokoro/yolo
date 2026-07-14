import { defineStore } from 'pinia'

import {
  createTrainingTask,
  getTrainingMetrics,
  getTrainingTask,
  listTrainingTasks,
  stopTrainingTask,
} from '@/api/training'

export const ACTIVE_TRAINING_STATUSES = new Set(['pending', 'starting', 'running', 'stopping'])
export const TERMINAL_TRAINING_STATUSES = new Set([
  'completed',
  'early_stopped',
  'cancelled',
  'failed',
  'interrupted',
])
export const TRAINING_POLL_INTERVAL = 5000

export function trainingApiMessage(error, fallback = '在线训练请求失败') {
  const status = error?.response?.status
  const detail = error?.response?.data?.message || error?.response?.data?.detail
  const messages = {
    401: '登录状态已失效，请重新登录',
    403: '当前账号无权访问该训练任务',
    404: '训练任务或产物不存在',
    409: '训练任务状态冲突或已达到并发上限',
    503: '在线训练功能未启用或训练服务暂不可用',
  }
  return detail || messages[status] || error?.message || fallback
}

export function mergeMetrics(current, incoming) {
  const byEpoch = new Map()
  for (const item of [...(current || []), ...(incoming || [])]) {
    const epoch = Number(item?.epoch)
    if (Number.isInteger(epoch) && epoch > 0) byEpoch.set(epoch, { ...item, epoch })
  }
  return [...byEpoch.values()].sort((a, b) => a.epoch - b.epoch)
}

export const useTrainingStore = defineStore('training', {
  state: () => ({
    tasks: [],
    selectedTask: null,
    metrics: [],
    listLoading: false,
    detailLoading: false,
    creating: false,
    stopping: false,
    error: '',
    pollError: '',
    polling: false,
    pollTimer: null,
    pollGeneration: 0,
    requestInFlight: false,
    visibilityHandler: null,
  }),
  getters: {
    selectedTaskActive: (state) => ACTIVE_TRAINING_STATUSES.has(state.selectedTask?.status),
    latestEpoch: (state) => state.metrics.reduce((max, item) => Math.max(max, Number(item.epoch) || 0), 0),
  },
  actions: {
    replaceTask(task) {
      const index = this.tasks.findIndex((item) => item.id === task.id)
      if (index >= 0) this.tasks[index] = task
      else this.tasks.unshift(task)
      if (this.selectedTask?.id === task.id) this.selectedTask = task
    },
    async fetchTasks() {
      this.listLoading = true
      try {
        const response = await listTrainingTasks()
        this.tasks = response.items || []
        return response
      } catch (error) {
        this.error = trainingApiMessage(error, '训练任务列表加载失败')
        throw error
      } finally {
        this.listLoading = false
      }
    },
    async createTask(payload) {
      this.creating = true
      this.error = ''
      try {
        const task = await createTrainingTask(payload)
        this.replaceTask(task)
        await this.selectTask(task, { refresh: false })
        if (ACTIVE_TRAINING_STATUSES.has(task.status)) this.startPolling()
        return task
      } catch (error) {
        this.error = trainingApiMessage(error, '训练任务创建失败')
        throw error
      } finally {
        this.creating = false
      }
    },
    async selectTask(taskOrId, { refresh = true } = {}) {
      const id = typeof taskOrId === 'object' ? taskOrId.id : Number(taskOrId)
      this.stopPolling()
      this.metrics = []
      this.pollError = ''
      this.selectedTask = typeof taskOrId === 'object' ? taskOrId : this.tasks.find((item) => item.id === id) || null
      if (refresh) await this.refreshSelected({ force: true })
      if (ACTIVE_TRAINING_STATUSES.has(this.selectedTask?.status)) this.startPolling()
      return this.selectedTask
    },
    async refreshSelected({ force = false } = {}) {
      const id = this.selectedTask?.id
      if (!id || this.requestInFlight || (!force && document.hidden)) return this.selectedTask
      this.requestInFlight = true
      this.detailLoading = force
      try {
        const afterEpoch = this.latestEpoch
        const [task, metricResponse] = await Promise.all([
          getTrainingTask(id),
          getTrainingMetrics(id, afterEpoch),
        ])
        if (this.selectedTask?.id !== id) return this.selectedTask
        this.selectedTask = task
        this.replaceTask(task)
        this.metrics = mergeMetrics(this.metrics, metricResponse.metrics || [])
        this.pollError = ''
        return task
      } catch (error) {
        if (this.selectedTask?.id === id) {
          this.pollError = trainingApiMessage(error, '训练状态刷新失败，已有曲线已保留')
        }
        throw error
      } finally {
        this.requestInFlight = false
        this.detailLoading = false
      }
    },
    async stopSelected() {
      if (!this.selectedTaskActive || this.stopping) return null
      this.stopping = true
      this.error = ''
      try {
        const task = await stopTrainingTask(this.selectedTask.id)
        this.replaceTask(task)
        if (ACTIVE_TRAINING_STATUSES.has(task.status)) this.startPolling()
        return task
      } catch (error) {
        this.error = trainingApiMessage(error, '停止训练任务失败')
        throw error
      } finally {
        this.stopping = false
      }
    },
    startPolling() {
      if (!this.selectedTaskActive) return
      this.stopPolling()
      this.polling = true
      const generation = ++this.pollGeneration
      const schedule = () => {
        if (!this.polling || generation !== this.pollGeneration || !this.selectedTaskActive || document.hidden) return
        this.pollTimer = setTimeout(poll, TRAINING_POLL_INTERVAL)
      }
      const poll = async () => {
        if (!this.polling || generation !== this.pollGeneration || document.hidden || this.requestInFlight) return
        try {
          await this.refreshSelected()
        } catch {
          // A transient polling error is exposed but does not erase metrics or stop retries.
        }
        if (!this.polling || generation !== this.pollGeneration) return
        if (TERMINAL_TRAINING_STATUSES.has(this.selectedTask?.status)) {
          this.stopPolling()
          await this.fetchTasks().catch(() => {})
          return
        }
        schedule()
      }
      schedule()
    },
    stopPolling() {
      this.polling = false
      this.pollGeneration += 1
      if (this.pollTimer) clearTimeout(this.pollTimer)
      this.pollTimer = null
    },
    handleVisibilityChange() {
      if (document.hidden) {
        if (this.pollTimer) clearTimeout(this.pollTimer)
        this.pollTimer = null
        return
      }
      if (!this.selectedTaskActive) return
      this.stopPolling()
      this.refreshSelected({ force: true })
        .catch(() => {})
        .finally(() => {
          if (this.selectedTaskActive) this.startPolling()
        })
    },
    initVisibilityHandling() {
      if (this.visibilityHandler) return
      this.visibilityHandler = () => this.handleVisibilityChange()
      document.addEventListener('visibilitychange', this.visibilityHandler)
    },
    dispose() {
      this.stopPolling()
      if (this.visibilityHandler) document.removeEventListener('visibilitychange', this.visibilityHandler)
      this.visibilityHandler = null
    },
  },
})
