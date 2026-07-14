<template>
  <div class="chat-page">
    <!-- 消息列表 -->
    <div class="message-list" ref="messageListRef">
      <div
        v-for="(msg, index) in agentStore.messages"
        :key="index"
        :class="['message-item', `message-${msg.role}`]"
      >
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="message-bubble user-bubble">
          <div class="message-content">{{ msg.content }}</div>
          <div v-if="msg.imagePreview" class="message-attachment">
            <img :src="msg.imagePreview" alt="附件图片" />
          </div>
          <div v-if="msg.images?.length" class="message-attachments-grid">
            <img v-for="(src, i) in msg.images" :key="i" :src="src" alt="附件图片" />
          </div>
        </div>

        <!-- AI 消息 -->
        <div v-else-if="msg.role === 'assistant'" class="message-bubble assistant-bubble">
          <div v-if="msg.loading" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <div v-else class="message-content" style="white-space: pre-wrap">{{ msg.content }}</div>

          <SegmentationResultCard
            v-if="msg.segmentationResult"
            :result="msg.segmentationResult"
          />
        </div>

        <div v-if="msg.toolCall" class="tool-call-info">
          <el-tag size="small" type="info"> 🔧 调用工具: {{ msg.toolCall.tool }} </el-tag>
        </div>
      </div>
    </div>

    <!-- 快捷操作栏 -->
    <div class="quick-actions">
      <el-button @click="handleQuickSegment('single')" :disabled="agentStore.isLoading">
        📷 单图分割
      </el-button>
      <el-button @click="handleQuickSegment('batch')" :disabled="agentStore.isLoading">
        📁 批量/ZIP 分割
      </el-button>
      <el-button disabled>🎬 视频</el-button>
      <el-button disabled>📹 摄像头</el-button>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <el-button class="attach-btn" @click="triggerFileInput" :disabled="agentStore.isLoading" circle>
        📎
      </el-button>
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*,.zip"
        style="display: none"
        @change="handleFileSelect"
      />

      <el-input
        v-model="inputText"
        placeholder="输入消息，或拖拽图片/ZIP 到这里..."
        @keyup.enter="sendMessage"
        :disabled="agentStore.isLoading"
      />

      <el-button
        v-if="!agentStore.isLoading"
        type="primary"
        @click="sendMessage"
        :disabled="!canSend"
      >
        发送
      </el-button>
      <el-button v-else type="danger" @click="handleStop"> 停止 </el-button>
    </div>
  </div>
</template>

<script setup>
/**
 * ChatPage.vue — 智能对话界面（Day 8）
 *
 * Features:
 *   - Message bubbles for user / assistant
 *   - Image / ZIP attachment upload
 *   - SSE streaming AI replies
 *   - Segmentation result cards
 *   - Quick-action toolbar for single / batch / ZIP segmentation
 *   - Stop generation
 */
import { segmentBatch, segmentSingle, segmentZip } from '@/api/segmentation'
import SegmentationResultCard from '@/components/SegmentationResultCard.vue'
import { useAgentStore } from '@/stores/agent'
import { createEventStream } from '@/utils/stream'
import request from '@/utils/request'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'

const agentStore = useAgentStore()

const inputText = ref('')
const selectedFile = ref(null)
const messageListRef = ref(null)
const fileInputRef = ref(null)

const canSend = computed(() => {
  return inputText.value.trim() || selectedFile.value
})

function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

async function sendMessage() {
  if (!canSend.value) return

  const message = inputText.value.trim()
  const fileToSend = selectedFile.value
  const imagePreview = fileToSend ? URL.createObjectURL(fileToSend) : null

  agentStore.addMessage({
    role: 'user',
    content: message,
    image: fileToSend ? fileToSend.name : null,
    imagePreview,
  })

  inputText.value = ''
  selectedFile.value = null

  agentStore.addMessage({
    role: 'assistant',
    content: '',
    loading: true,
  })

  scrollToBottom()

  let serverImagePath = null
  if (fileToSend) {
    try {
      const formData = new FormData()
      formData.append('file', fileToSend)
      const uploadResult = await request.post('/chat/upload', formData)
      serverImagePath = uploadResult.image_path
    } catch (err) {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `图片上传失败：${err.response?.data?.detail || err.message || '未知错误'}，请重试`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
      return
    }
  }

  const requestBody = {
    message,
    ...(serverImagePath ? { image_path: serverImagePath } : {}),
  }

  let fullContent = ''
  agentStore.setLoading(true)

  const { stop } = createEventStream('/api/chat/stream', {
    body: requestBody,
    onMessage: (dataText) => {
      let data
      try {
        data = JSON.parse(dataText)
      } catch {
        data = { type: 'text_chunk', content: dataText }
      }

      const lastMsg = agentStore.messages[agentStore.messages.length - 1]

      if (data.type === 'text_chunk') {
        fullContent += data.content
        lastMsg.content = fullContent
        scrollToBottom()
      } else if (data.type === 'tool_call') {
        lastMsg.toolCall = { tool: data.tool, input: data.input }
      } else if (data.type === 'tool_result') {
        try {
          const result = JSON.parse(data.result)
          if (result.class_statistics || result.annotated_images || result.annotated_image) {
            lastMsg.segmentationResult = result
          }
        } catch {
          lastMsg.content += `\n[工具结果: ${data.result?.substring(0, 100)}...]`
        }
        scrollToBottom()
      } else if (data.type === 'error') {
        lastMsg.content = data.content
        lastMsg.loading = false
        lastMsg.error = true
        agentStore.setLoading(false)
      }
    },
    onDone: () => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      if (lastMsg?.loading) {
        lastMsg.loading = false
      }
      agentStore.setLoading(false)
    },
    onError: (err) => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `抱歉，处理出错了：${err.message}`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
      ElMessage.error('对话请求失败，请重试')
    },
  })

  agentStore.setAbortController(stop)
}

function handleStop() {
  agentStore.abort()
  const lastMsg = agentStore.messages[agentStore.messages.length - 1]
  if (lastMsg?.loading) {
    lastMsg.loading = false
    lastMsg.content += '\n[已停止生成]'
  }
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleFileSelect(event) {
  const file = event.target.files[0]
  if (file) {
    selectedFile.value = file
    ElMessage.info(`${file.name} 已选择`)
  }
}

async function handleQuickSegment(type) {
  if (type === 'single') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async (e) => {
      const file = e.target.files[0]
      if (!file) return

      agentStore.addMessage({
        role: 'user',
        content: `[快捷分割] ${file.name}`,
        image: file.name,
        imagePreview: URL.createObjectURL(file),
      })

      agentStore.addMessage({
        role: 'assistant',
        content: '正在分割中...',
        loading: true,
      })

      const formData = new FormData()
      formData.append('file', file)

      try {
        const result = await segmentSingle(formData)
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `分割完成！图片尺寸 ${result.image_width}×${result.image_height}。`
        lastMsg.loading = false
        lastMsg.segmentationResult = result
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = '分割失败，请重试'
        lastMsg.loading = false
        lastMsg.error = true
      }
      scrollToBottom()
    }
    input.click()
  } else if (type === 'batch') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.zip'
    input.multiple = true
    input.onchange = async (e) => {
      const files = Array.from(e.target.files)
      if (!files.length) return

      const isZip = files.some((f) => f.name.endsWith('.zip'))
      const formData = new FormData()

      if (isZip && files.length === 1) {
        formData.append('file', files[0])
        agentStore.addMessage({
          role: 'user',
          content: `[快捷分割] ZIP: ${files[0].name}`,
        })
      } else {
        files.forEach((f) => formData.append('files', f))
        const imagePreviews = files.map((f) => URL.createObjectURL(f))
        agentStore.addMessage({
          role: 'user',
          content: `[快捷分割] ${files.length} 张图片`,
          images: imagePreviews,
        })
      }

      agentStore.addMessage({
        role: 'assistant',
        content: '正在批量分割中...',
        loading: true,
      })

      try {
        const apiCall = isZip ? segmentZip(formData) : segmentBatch(formData)
        const result = await apiCall
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]

        if (result.error) {
          lastMsg.content = `批量分割失败：${result.error}`
          lastMsg.loading = false
          lastMsg.error = true
          return
        }

        lastMsg.content = `批量分割完成！共 ${result.successful_images} 张图。`
        lastMsg.loading = false
        lastMsg.segmentationResult = result
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `批量分割失败：${err.message || err}`
        lastMsg.loading = false
        lastMsg.error = true
      }
      scrollToBottom()
    }
    input.click()
  }
}

onMounted(() => {
  if (agentStore.messages.length === 0) {
    agentStore.addMessage({
      role: 'assistant',
      content:
        '你好！我是遥感检测智能体助手。\n\n你可以：\n- 上传一张图片，让我帮你进行 LoveDA 7 类分析\n- 使用下方的快捷按钮直接触发分析\n- 用自然语言描述你的需求\n\n试试发一张图片给我吧！',
    })
  }
})
</script>

<style lang="scss" scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f5f5;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.message-item {
  display: flex;
  margin-bottom: 16px;

  &.message-user {
    justify-content: flex-end;
  }

  &.message-assistant {
    justify-content: flex-start;
  }
}

.message-bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.user-bubble {
  background: #409eff;
  color: white;
  border-bottom-right-radius: 4px;
}

.assistant-bubble {
  background: white;
  border: 1px solid #e0e0e0;
  border-bottom-left-radius: 4px;
}

.typing-indicator {
  display: flex;
  gap: 4px;

  span {
    width: 6px;
    height: 6px;
    background: #999;
    border-radius: 50%;
    animation: typing 1.2s infinite;
  }

  span:nth-child(2) {
    animation-delay: 0.2s;
  }
  span:nth-child(3) {
    animation-delay: 0.4s;
  }
}

.quick-actions {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #e0e0e0;
  background: white;
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #e0e0e0;
  background: white;

  .el-input {
    flex: 1;
  }
}

.message-attachment {
  margin-top: 8px;

  img {
    max-width: 200px;
    border-radius: 8px;
    border: 1px solid #e0e0e0;
  }
}

.message-attachments-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
  margin-top: 8px;

  img {
    width: 100%;
    height: 80px;
    object-fit: cover;
    border-radius: 6px;
    border: 1px solid #e0e0e0;
  }
}

.tool-call-info {
  margin-top: 8px;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
}

@keyframes typing {
  0%,
  60%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-4px);
  }
}
</style>
