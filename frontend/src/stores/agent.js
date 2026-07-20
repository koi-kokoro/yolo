import { defineStore } from 'pinia'

import {
  createChatSession,
  deleteChatSession,
  getChatImage,
  listChatMessages,
  listChatSessions,
  renameChatSession,
} from '@/api/chat'

function storageKey(userId) {
  return `rsod_chat_current_session:${userId || 'anonymous'}`
}

function normalizeSessionId(value) {
  const id = Number(value)
  return Number.isSafeInteger(id) && id > 0 ? id : null
}

function parseToolResult(value) {
  if (!value) return null
  try {
    return typeof value === 'string' ? JSON.parse(value) : value
  } catch {
    return null
  }
}

function mapMessage(message) {
  const toolResult = parseToolResult(message.tool_result)
  const isSegmentationResult = toolResult && (
    toolResult.class_statistics
    || toolResult.annotated_images
    || toolResult.annotated_image
    || toolResult.annotated_image_ref
  )
  return {
    id: message.id,
    role: message.role,
    content: message.content || '',
    agentRoute: message.agent_used || null,
    toolCall: message.tool_calls?.[0] || null,
    exportResult: toolResult?.filename && toolResult?.download_url ? toolResult : null,
    attachmentRefs: message.role === 'user' ? toolResult?.attachments || [] : [],
    segmentationResult: message.role === 'assistant' && isSegmentationResult ? toolResult : null,
    createdAt: message.created_at || new Date().toISOString(),
  }
}

async function hydrateMessages(messages) {
  const refs = new Set()
  messages.forEach((message) => {
    message.attachmentRefs?.forEach((item) => refs.add(item.image_ref))
    const result = message.segmentationResult
    if (result?.annotated_image_ref) refs.add(result.annotated_image_ref)
    result?.annotated_images?.forEach((item) => {
      if (item.annotated_image_ref) refs.add(item.annotated_image_ref)
    })
  })

  const urls = []
  const urlByRef = new Map()
  await Promise.all([...refs].filter(Boolean).map(async (ref) => {
    try {
      const blob = await getChatImage(ref)
      const url = URL.createObjectURL(blob)
      urls.push(url)
      urlByRef.set(ref, url)
    } catch {
      // 单张历史图片过期时，其他文本和结果仍应正常展示。
    }
  }))

  messages.forEach((message) => {
    const attachmentUrls = (message.attachmentRefs || [])
      .map((item) => urlByRef.get(item.image_ref))
      .filter(Boolean)
    message.imagePreview = attachmentUrls.length === 1 ? attachmentUrls[0] : null
    message.images = attachmentUrls.length > 1 ? attachmentUrls : null

    const result = message.segmentationResult
    if (result?.annotated_image_ref) {
      result.annotated_image_url = urlByRef.get(result.annotated_image_ref) || null
    }
    result?.annotated_images?.forEach((item) => {
      if (item.annotated_image_ref) {
        item.annotated_image_url = urlByRef.get(item.annotated_image_ref) || null
      }
    })
  })

  return { messages, urls }
}

export const useAgentStore = defineStore('agent', {
  state: () => ({
    currentSessionId: null,
    messages: [],
    sessions: [],
    sessionsLoading: false,
    messagesLoading: false,
    messagesCursor: null,
    messagesHasMore: false,
    isLoading: false,
    abortController: null,
    currentScene: null,
    conversations: [],
    selectionSequence: 0,
    userId: null,
    historyObjectUrls: [],
  }),
  actions: {
    setUser(userId) {
      this.userId = userId
    },
    persistCurrent() {
      const key = storageKey(this.userId)
      if (this.currentSessionId) localStorage.setItem(key, String(this.currentSessionId))
      else localStorage.removeItem(key)
    },
    setCurrentScene(scene) {
      this.currentScene = scene
    },
    setAbortController(controller) {
      this.abortController = controller
    },
    addMessage(message) {
      this.messages.push({
        id: message.id || `${Date.now()}-${this.messages.length}`,
        role: message.role,
        content: message.content || '',
        createdAt: message.createdAt || new Date().toISOString(),
        ...message,
      })
    },
    updateLastAssistantMessage(content) {
      const last = [...this.messages].reverse().find((message) => message.role === 'assistant')
      if (last) last.content += content
      else this.addMessage({ role: 'assistant', content })
    },
    setLoading(loading) {
      this.isLoading = loading
    },
    abort() {
      if (typeof this.abortController === 'function') this.abortController()
      else this.abortController?.abort?.()
      this.abortController = null
      this.isLoading = false
    },
    async listSessions() {
      this.sessionsLoading = true
      try {
        const data = await listChatSessions({ page: 1, page_size: 100 })
        this.sessions = data.items || []
        return this.sessions
      } finally {
        this.sessionsLoading = false
      }
    },
    async createSession(title = '新会话') {
      this.abort()
      const session = await createChatSession(title)
      this.sessions.unshift(session)
      await this.selectSession(session.id, { force: true })
      return session
    },
    async selectSession(id, { force = false } = {}) {
      id = normalizeSessionId(id)
      if (!id) return false
      if (!force && id === this.currentSessionId && this.messages.length) return
      this.abort()
      const sequence = ++this.selectionSequence
      this.messagesLoading = true
      try {
        const data = await listChatMessages(id, { limit: 30 })
        if (sequence !== this.selectionSequence) return false
        const hydrated = await hydrateMessages((data.items || []).map(mapMessage))
        if (sequence !== this.selectionSequence) {
          hydrated.urls.forEach((url) => URL.revokeObjectURL(url))
          return false
        }
        this.historyObjectUrls.forEach((url) => URL.revokeObjectURL(url))
        this.historyObjectUrls = hydrated.urls
        this.currentSessionId = id
        this.messages = hydrated.messages
        this.messagesCursor = data.next_cursor
        this.messagesHasMore = data.has_more
        this.persistCurrent()
        return true
      } finally {
        if (sequence === this.selectionSequence) this.messagesLoading = false
      }
    },
    async loadMoreMessages() {
      if (!this.currentSessionId || !this.messagesHasMore || this.messagesLoading) return
      const sessionId = this.currentSessionId
      const sequence = this.selectionSequence
      this.messagesLoading = true
      try {
        const data = await listChatMessages(sessionId, {
          limit: 30,
          before_id: this.messagesCursor,
        })
        if (sequence !== this.selectionSequence || sessionId !== this.currentSessionId) return
        const hydrated = await hydrateMessages((data.items || []).map(mapMessage))
        if (sequence !== this.selectionSequence || sessionId !== this.currentSessionId) {
          hydrated.urls.forEach((url) => URL.revokeObjectURL(url))
          return
        }
        this.historyObjectUrls.push(...hydrated.urls)
        this.messages = [...hydrated.messages, ...this.messages]
        this.messagesCursor = data.next_cursor
        this.messagesHasMore = data.has_more
      } finally {
        if (sequence === this.selectionSequence) this.messagesLoading = false
      }
    },
    async renameSession(id, title) {
      const updated = await renameChatSession(id, title)
      const index = this.sessions.findIndex((item) => item.id === id)
      if (index >= 0) this.sessions[index] = updated
    },
    async deleteSession(id) {
      this.abort()
      await deleteChatSession(id)
      this.sessions = this.sessions.filter((item) => item.id !== id)
      if (this.currentSessionId === id) {
        this.currentSessionId = null
        this.messages = []
        this.persistCurrent()
        if (this.sessions[0]) await this.selectSession(this.sessions[0].id, { force: true })
        else await this.createSession()
      }
    },
    handleSessionEvent(data, expectedSessionId = null) {
      const incoming = normalizeSessionId(data?.session_id)
      const expected = normalizeSessionId(expectedSessionId)
      if (!incoming) return false
      if (expected && normalizeSessionId(this.currentSessionId) !== expected) return false
      // 已绑定会话的请求不允许服务端事件静默切换到另一会话。
      if (expected && incoming !== expected) return false
      this.currentSessionId = incoming
      this.persistCurrent()
      return true
    },
    async initialize(userId) {
      this.setUser(userId)
      await this.listSessions()
      const stored = Number(localStorage.getItem(storageKey(userId)))
      const target = this.sessions.find((item) => item.id === stored)?.id || this.sessions[0]?.id
      if (target) await this.selectSession(target, { force: true })
      else await this.createSession()
    },
    async newChat() {
      return this.createSession()
    },
    clear() {
      this.abort()
      this.historyObjectUrls.forEach((url) => URL.revokeObjectURL(url))
      this.historyObjectUrls = []
      this.selectionSequence += 1
      this.currentSessionId = null
      this.messages = []
      this.sessions = []
      this.currentScene = null
      this.conversations = []
    },
    reset() {
      this.clear()
    },
  },
})
