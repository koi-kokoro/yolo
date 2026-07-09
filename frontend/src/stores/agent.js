import { defineStore } from 'pinia'

export const useAgentStore = defineStore('agent', {
  state: () => ({
    currentSessionId: null,
    messages: [],
    sessions: [],
    isLoading: false,
    abortController: null,
    currentScene: null,
    conversations: [],
  }),
  actions: {
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
      const lastAssistantMessage = [...this.messages].reverse().find((message) => message.role === 'assistant')

      if (lastAssistantMessage) {
        lastAssistantMessage.content += content
        return
      }

      this.addMessage({ role: 'assistant', content })
    },
    setLoading(loading) {
      this.isLoading = loading
    },
    abort() {
      this.abortController?.abort()
      this.abortController = null
      this.isLoading = false
    },
    newChat() {
      this.abort()
      this.currentSessionId = null
      this.messages = []
    },
    clear() {
      this.abort()
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
