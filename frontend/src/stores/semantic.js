import { defineStore } from 'pinia'

import {
  createSemanticTask,
  getSemanticModelInfo,
  getSemanticTask,
  listSemanticTasks,
} from '@/api/semantic'

const TERMINAL_STATUSES = new Set(['succeeded', 'failed'])
const BASE_POLL_DELAY = 1500
const MAX_POLL_DELAY = 10000

function apiMessage(error, fallback = '请求失败') {
  return error?.response?.data?.message || error?.response?.data?.detail || error?.message || fallback
}

export const useSemanticStore = defineStore('semantic', {
  state: () => ({
    modelInfo: null,
    currentTask: null,
    history: [],
    pagination: { total: 0, page: 1, page_size: 20, total_pages: 0 },
    uploading: false,
    polling: false,
    loadingHistory: false,
    error: '',
    pollTimer: null,
    pollGeneration: 0,
    consecutivePollErrors: 0,
  }),
  getters: {
    modelReady: (state) => Boolean(state.modelInfo?.ready),
    isActive: (state) => ['pending', 'running'].includes(state.currentTask?.status),
    canSubmit() {
      return this.modelReady && !this.uploading && !this.isActive
    },
  },
  actions: {
    async fetchModelInfo() {
      try {
        this.modelInfo = await getSemanticModelInfo()
        return this.modelInfo
      } catch (error) {
        this.error = apiMessage(error, '模型状态获取失败')
        throw error
      }
    },
    async fetchHistory(params = {}) {
      this.loadingHistory = true
      try {
        const data = await listSemanticTasks({ page: 1, page_size: 20, ...params })
        this.history = data.items || []
        this.pagination = {
          total: data.total,
          page: data.page,
          page_size: data.page_size,
          total_pages: data.total_pages,
        }
        return data
      } finally {
        this.loadingHistory = false
      }
    },
    async createTask(file) {
      if (!this.canSubmit) return null
      this.stopPolling()
      this.uploading = true
      this.error = ''
      const formData = new FormData()
      formData.append('file', file)
      try {
        const task = await createSemanticTask(formData)
        this.currentTask = task
        this.startPolling(task.task_uuid)
        await this.fetchHistory().catch(() => {})
        return task
      } catch (error) {
        this.error = apiMessage(error, '任务创建失败')
        throw error
      } finally {
        this.uploading = false
      }
    },
    async openTask(taskUuid) {
      this.stopPolling()
      this.error = ''
      try {
        const task = await getSemanticTask(taskUuid)
        this.currentTask = task
        if (!TERMINAL_STATUSES.has(task.status)) this.startPolling(taskUuid)
        return task
      } catch (error) {
        this.error = apiMessage(error, '任务详情获取失败')
        throw error
      }
    },
    async refreshCurrentTask() {
      if (!this.currentTask?.task_uuid) return null
      return this.openTask(this.currentTask.task_uuid)
    },
    startPolling(taskUuid) {
      this.stopPolling()
      const generation = ++this.pollGeneration
      this.polling = true
      this.consecutivePollErrors = 0

      const poll = async () => {
        if (!this.polling || generation !== this.pollGeneration) return
        let delay = BASE_POLL_DELAY
        try {
          const task = await getSemanticTask(taskUuid)
          if (!this.polling || generation !== this.pollGeneration) return
          this.currentTask = task
          this.consecutivePollErrors = 0
          this.error = task.status === 'failed' ? task.error?.message || '任务执行失败' : ''
          if (TERMINAL_STATUSES.has(task.status)) {
            this.stopPolling()
            await this.fetchHistory().catch(() => {})
            return
          }
        } catch (error) {
          if (!this.polling || generation !== this.pollGeneration) return
          this.consecutivePollErrors += 1
          delay = Math.min(BASE_POLL_DELAY * 2 ** this.consecutivePollErrors, MAX_POLL_DELAY)
          this.error = apiMessage(error, '轮询任务状态失败，正在重试')
        }
        if (this.polling && generation === this.pollGeneration) {
          this.pollTimer = setTimeout(poll, delay)
        }
      }

      poll()
    },
    stopPolling() {
      this.polling = false
      this.pollGeneration += 1
      if (this.pollTimer) clearTimeout(this.pollTimer)
      this.pollTimer = null
      this.consecutivePollErrors = 0
    },
    clearCurrentTask() {
      this.stopPolling()
      this.currentTask = null
      this.error = ''
    },
    dispose() {
      this.stopPolling()
    },
  },
})
