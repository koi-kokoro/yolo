import request from '@/utils/request'

export const listChatSessions = (params = {}) => request.get('/chat/sessions', { params })
export const createChatSession = (title) => request.post('/chat/sessions', { title })
export const getChatSession = (id) => request.get(`/chat/sessions/${id}`)
export const renameChatSession = (id, title) => request.patch(`/chat/sessions/${id}`, { title })
export const deleteChatSession = (id) => request.delete(`/chat/sessions/${id}`)
export const listChatMessages = (id, params = {}) =>
  request.get(`/chat/sessions/${id}/messages`, { params })
