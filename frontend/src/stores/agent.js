import { defineStore } from "pinia";

export const useAgentStore = defineStore("agent", {
  state: () => ({
    currentSessionId: null,
    messages: [],
    sessions: [],
    isLoading: false,
    abortController: null,
  }),

  getters: {
    messageCount: (state) => state.messages.length,
    hasSession: (state) => state.sessions.length > 0,
  },

  actions: {
    addMessage(message) {
      this.messages.push(message);
    },

    updateLastAssistantMessage(content) {
      const lastMsg = this.messages[this.messages.length - 1];
      if (lastMsg && lastMsg.role === "assistant") {
        lastMsg.content = content;
      }
    },

    setLoading(loading) {
      this.isLoading = loading;
    },

    abort() {
      if (this.abortController) {
        this.abortController();
        this.abortController = null;
        this.isLoading = false;
      }
    },

    newChat() {
      this.currentSessionId = null;
      this.messages = [];
      this.abort();
    },

    clear() {
      this.currentSessionId = null;
      this.messages = [];
      this.sessions = [];
      this.abort();
    },
  },
});
