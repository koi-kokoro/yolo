import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/chat', () => ({
  listChatSessions: vi.fn(),
  createChatSession: vi.fn(),
  listChatMessages: vi.fn(),
  renameChatSession: vi.fn(),
  deleteChatSession: vi.fn(),
}))

import { createChatSession, deleteChatSession, listChatMessages, listChatSessions } from '@/api/chat'
import { useAgentStore } from '@/stores/agent'

describe('agent session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('加载列表并恢复按用户隔离的会话', async () => {
    localStorage.setItem('rsod_chat_current_session:7', '2')
    listChatSessions.mockResolvedValue({ items: [{ id: 1 }, { id: 2 }] })
    listChatMessages.mockResolvedValue({ items: [{ id: 9, role: 'user', content: '历史' }] })
    const store = useAgentStore()
    await store.initialize(7)
    expect(store.currentSessionId).toBe(2)
    expect(store.messages[0].content).toBe('历史')
  })

  it('无会话时新建并处理 session 事件', async () => {
    listChatSessions.mockResolvedValue({ items: [] })
    createChatSession.mockResolvedValue({ id: 3, title: '新会话' })
    listChatMessages.mockResolvedValue({ items: [], has_more: false })
    const store = useAgentStore()
    await store.initialize(8)
    expect(store.currentSessionId).toBe(3)
    expect(store.handleSessionEvent({ session_id: 3 }, 3)).toBe(true)
    expect(localStorage.getItem('rsod_chat_current_session:8')).toBe('3')
    expect(store.handleSessionEvent({ session_id: '3' }, 3)).toBe(true)
    expect(store.currentSessionId).toBe(3)
    expect(store.handleSessionEvent({ session_id: 4 }, 3)).toBe(false)
    expect(store.handleSessionEvent({ session_id: 'invalid' }, 3)).toBe(false)
    expect(store.currentSessionId).toBe(3)
  })

  it('切换时丢弃过期异步消息结果', async () => {
    let resolveFirst
    listChatMessages
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ items: [{ id: 2, role: 'user', content: '新会话' }] })
    const store = useAgentStore()
    const first = store.selectSession(1)
    await store.selectSession(2)
    resolveFirst({ items: [{ id: 1, role: 'user', content: '旧会话' }] })
    await first
    expect(store.currentSessionId).toBe(2)
    expect(store.messages[0].content).toBe('新会话')
  })

  it('删除当前会话后切换剩余会话', async () => {
    deleteChatSession.mockResolvedValue()
    listChatMessages.mockResolvedValue({ items: [] })
    const store = useAgentStore()
    store.sessions = [{ id: 1 }, { id: 2 }]
    store.currentSessionId = 1
    await store.deleteSession(1)
    expect(store.currentSessionId).toBe(2)
  })

  it('恢复历史消息中的导出下载信息', async () => {
    listChatMessages.mockResolvedValue({
      items: [{
        id: 10,
        role: 'assistant',
        content: '已导出',
        tool_result: JSON.stringify({
          filename: 'evaluation_test.json',
          download_url: '/api/chat/exports/evaluation_test.json',
          format: 'json',
        }),
      }],
    })
    const store = useAgentStore()
    await store.selectSession(1)
    expect(store.messages[0].exportResult.filename).toBe('evaluation_test.json')
  })
})
