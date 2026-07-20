<template>
  <div class="chat-page">
    <aside class="session-sidebar">
      <el-button type="primary" class="new-session" @click="agentStore.createSession()">
        <el-icon><Plus /></el-icon>
        新建会话
      </el-button>
      <div v-if="agentStore.sessionsLoading" class="session-empty">加载中...</div>
      <div
        v-for="session in agentStore.sessions"
        :key="session.id"
        :class="['session-item', { active: session.id === agentStore.currentSessionId }]"
        @click="agentStore.selectSession(session.id)"
      >
        <div class="session-title">{{ session.title || '新会话' }}</div>
        <div class="session-time">{{ formatSessionTime(session.last_message_at || session.created_at) }}</div>
        <div class="session-actions" @click.stop>
          <el-button link size="small" @click="renameSession(session)">重命名</el-button>
          <el-button link type="danger" size="small" @click="removeSession(session)">删除</el-button>
        </div>
      </div>
    </aside>
    <main class="chat-main">
    <div v-if="agentStore.messagesHasMore" class="load-more">
      <el-button link :loading="agentStore.messagesLoading" @click="agentStore.loadMoreMessages()">加载更早消息</el-button>
    </div>
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
          <div v-if="msg.workflow" class="workflow-progress">
            <div class="workflow-title">
              <span>{{ msg.workflow.reason }}</span>
              <el-tag size="small" :type="workflowStatusType(msg.workflow.status)">
                {{ workflowStatusLabel(msg.workflow.status) }}
              </el-tag>
            </div>
            <div class="workflow-steps">
              <el-tag
                v-for="step in msg.workflow.steps"
                :key="step.id"
                size="small"
                effect="plain"
                :type="workflowStatusType(step.status)"
              >
                {{ agentLabel(step.agent) }} · {{ workflowStatusLabel(step.status) }}
              </el-tag>
            </div>
          </div>
          <div v-if="msg.loading" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <div v-else class="message-content markdown-content" v-html="renderMarkdown(msg.content)"></div>

          <SegmentationResultCard
            v-if="msg.segmentationResult"
            :result="msg.segmentationResult"
          />

          <FacilityDetectionResultCard
            v-if="msg.facilityDetectionResult"
            :result="msg.facilityDetectionResult"
          />

          <el-button
            v-if="msg.exportResult"
            class="export-download"
            type="primary"
            plain
            @click="downloadExport(msg.exportResult)"
          >
            下载 {{ msg.exportResult.format?.toUpperCase() }} 文件
          </el-button>
        </div>

        <div v-if="msg.toolCall" class="tool-call-info">
          <el-tag size="small" type="info" effect="light">
            <el-icon><Tools /></el-icon>
            调用工具: {{ msg.toolCall.tool }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 快捷操作栏 -->
    <div class="quick-actions">
      <el-button @click="handleQuickSegment('single')" :disabled="agentStore.isLoading">
        <el-icon><Picture /></el-icon>
        单图分割
      </el-button>
      <el-button @click="handleQuickSegment('batch')" :disabled="agentStore.isLoading">
        <el-icon><FolderOpened /></el-icon>
        批量/ZIP 分割
      </el-button>
      <el-button @click="handleQuickSegment('video')" :disabled="agentStore.isLoading">
        <el-icon><VideoCamera /></el-icon>
        视频
      </el-button>
      <el-button @click="handleQuickSegment('camera')" :disabled="agentStore.isLoading">
        <el-icon><Camera /></el-icon>
        摄像头
      </el-button>
    </div>

    <el-dialog
      title="摄像头拍照"
      :model-value="cameraDialogVisible"
      custom-class="camera-dialog"
      width="640px"
      top="10vh"
      :append-to-body="true"
      @close="closeCameraDialog"
    >
      <div class="camera-dialog-body">
        <div v-if="cameraStream" class="camera-preview-wrapper">
          <video
            ref="cameraVideoRef"
            autoplay
            playsinline
            muted
            class="camera-preview"
          ></video>
        </div>
        <div v-else class="camera-error-wrapper">
          <p>摄像头未启动。请允许浏览器访问摄像头权限，或点击下方重试。</p>
          <div v-if="cameraError" class="camera-error-message">{{ cameraError }}</div>
          <el-button type="primary" @click="startCamera">重新尝试</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="closeCameraDialog">取消</el-button>
        <el-button
          type="primary"
          :disabled="!cameraStream || cameraCaptureInProgress || cameraRealtimeRunning"
          @click="captureCameraImage"
        >
          {{ cameraCaptureInProgress ? '拍照中...' : '拍照并分析' }}
        </el-button>
        <el-button
          type="success"
          :disabled="!cameraStream || cameraCaptureInProgress || cameraRealtimeRunning"
          @click="captureCameraVideo"
        >
          {{ cameraCaptureInProgress ? '视频采样中...' : '视频采样分析' }}
        </el-button>
        <el-button
          type="warning"
          :disabled="!cameraStream || cameraCaptureInProgress || cameraRealtimeRunning"
          @click="startRealtimeRecognition"
        >
          {{ cameraRealtimeRunning ? '实时识别中...' : '开始实时识别' }}
        </el-button>
        <el-button
          type="danger"
          :disabled="!cameraRealtimeRunning"
          @click="stopRealtimeRecognition"
        >
          停止实时识别
        </el-button>
      </template>
    </el-dialog>

    <!-- 输入区 -->
    <div v-if="selectedAttachments.length" class="pending-attachments">
      <div
        v-for="attachment in selectedAttachments"
        :key="attachment.id"
        class="pending-attachment-card"
      >
        <img
          v-if="attachment.preview"
          :src="attachment.preview"
          :alt="attachment.file.name"
          class="pending-attachment-preview"
        />
        <div v-else class="pending-attachment-file">ZIP</div>
        <button
          type="button"
          class="pending-attachment-remove"
          :aria-label="`移除 ${attachment.file.name}`"
          :title="`移除 ${attachment.file.name}`"
          @click="removeSelectedAttachment(attachment.id)"
        >
          ×
        </button>
        <span class="pending-attachment-name" :title="attachment.file.name">
          {{ attachment.file.name }}
        </span>
        <span class="pending-attachment-size">{{ formatFileSize(attachment.file.size) }}</span>
      </div>
    </div>

    <div class="input-area">
      <el-button class="attach-btn" @click="triggerFileInput" :disabled="agentStore.isLoading" circle>
        <el-icon><Paperclip /></el-icon>
      </el-button>
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*,.zip"
        multiple
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
        <el-icon><Promotion /></el-icon>
        发送
      </el-button>
      <el-button v-else type="danger" @click="handleStop"> 停止 </el-button>
    </div>
    </main>
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
import { segmentBatch, segmentSingle, segmentVideo, segmentZip } from '@/api/segmentation'
import FacilityDetectionResultCard from '@/components/FacilityDetectionResultCard.vue'
import SegmentationResultCard from '@/components/SegmentationResultCard.vue'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { renderMarkdown } from '@/utils/markdown'
import { createEventStream } from '@/utils/stream'
import request from '@/utils/request'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Camera, FolderOpened, Paperclip, Picture, Plus, Promotion, Tools, VideoCamera } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const agentStore = useAgentStore()

const userStore = useUserStore()

const inputText = ref('')
const selectedAttachments = ref([])
const messageListRef = ref(null)
const fileInputRef = ref(null)
const cameraVideoRef = ref(null)
const cameraDialogVisible = ref(false)
const cameraStream = ref(null)
const cameraError = ref('')
const cameraCaptureInProgress = ref(false)
const cameraRealtimeRunning = ref(false)
const cameraRealtimeStopRequested = ref(false)
let cameraMediaStream = null
let attachmentSequence = 0

const canSend = computed(() => {
  return inputText.value.trim() || selectedAttachments.value.length > 0
})

function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

function refreshSessionTitles() {
  void agentStore.listSessions().catch(() => {
    // 标题刷新失败不影响当前对话。
  })
}

async function sendMessage() {
  if (!canSend.value) return

  const message = inputText.value.trim()
  const attachmentsToSend = [...selectedAttachments.value]
  const filesToSend = attachmentsToSend.map((attachment) => attachment.file)
  const imageFiles = filesToSend.filter((file) => file.type.startsWith('image/'))

  if (filesToSend.length > 1 && imageFiles.length !== filesToSend.length) {
    ElMessage.warning('多附件发送仅支持图片，请移除 ZIP 后重试')
    return
  }

  const isBatch = imageFiles.length > 1
  const fileToSend = filesToSend[0] || null
  const messageImages = imageFiles.map((file) => URL.createObjectURL(file))
  const effectiveMessage = message || (isBatch
    ? `[批量分割] ${imageFiles.length} 张图片`
    : fileToSend
      ? `请分析图片：${fileToSend.name}`
      : '')

  agentStore.addMessage({
    role: 'user',
    content: effectiveMessage,
    image: fileToSend ? fileToSend.name : null,
    imagePreview: messageImages.length === 1 ? messageImages[0] : null,
    images: messageImages.length > 1 ? messageImages : null,
  })

  inputText.value = ''
  clearSelectedAttachments()

  agentStore.addMessage({
    role: 'assistant',
    content: '',
    loading: true,
  })

  scrollToBottom()

  if (isBatch) {
    await sendSelectedImageBatch(imageFiles, effectiveMessage)
    return
  }

  let serverImageRef = null
  if (fileToSend) {
    try {
      const formData = new FormData()
      formData.append('file', fileToSend)
      const uploadResult = await request.post('/chat/upload', formData)
      serverImageRef = uploadResult.image_ref
    } catch (err) {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `图片上传失败：${err.response?.data?.detail || err.message || '未知错误'}，请重试`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
      return
    }
  }

  const requestSessionId = agentStore.currentSessionId
  const requestBody = {
    message: effectiveMessage,
    session_id: requestSessionId,
    ...(serverImageRef ? { image_ref: serverImageRef } : {}),
  }

  let fullContent = ''
  agentStore.setLoading(true)

  const { stop } = await createEventStream('/api/chat/stream', {
    body: requestBody,
    onMessage: (dataText) => {
      let data
      try {
        data = JSON.parse(dataText)
      } catch {
        data = { type: 'text_chunk', content: dataText }
      }

      if (requestSessionId !== agentStore.currentSessionId) return
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]

      if (data.type === 'session') {
        agentStore.handleSessionEvent(data, requestSessionId)
      } else if (data.type === 'workflow_plan') {
        lastMsg.workflow = {
          id: data.workflow_id,
          reason: data.plan?.reason || '多 Agent 协作',
          status: 'running',
          steps: (data.plan?.steps || []).map((step) => ({ ...step, status: 'pending' })),
        }
      } else if (data.type === 'workflow_node') {
        const step = lastMsg.workflow?.steps?.find((item) => item.id === data.node)
        if (step) step.status = data.status
      } else if (data.type === 'workflow_retry') {
        const step = lastMsg.workflow?.steps?.find((item) => item.id === data.node)
        if (step) {
          step.status = 'running'
          step.attempt = data.attempt
        }
      } else if (data.type === 'workflow_complete') {
        if (lastMsg.workflow) {
          lastMsg.workflow.status = data.status
          lastMsg.workflow.review = data.review
        }
      } else if (data.type === 'agent_route') {
        lastMsg.agentRoute = data.agent
      } else if (data.type === 'text_chunk') {
        fullContent += data.content
        lastMsg.content = fullContent
        scrollToBottom()
      } else if (data.type === 'tool_call') {
        lastMsg.toolCall = { tool: data.tool, input: data.input }
      } else if (data.type === 'tool_result') {
        try {
          const result = JSON.parse(data.result)
          if (result.class_statistics || result.annotated_images || result.annotated_image) {
            if (result.kind === 'facility_detection') {
              lastMsg.facilityDetectionResult = result
            } else {
              lastMsg.segmentationResult = result
            }
          }
          if (result.download_url && result.filename) {
            lastMsg.exportResult = result
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
      if (requestSessionId !== agentStore.currentSessionId) return
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      if (lastMsg?.loading) {
        lastMsg.loading = false
      }
      agentStore.setLoading(false)
      refreshSessionTitles()
    },
    onError: (err) => {
      if (requestSessionId !== agentStore.currentSessionId) return
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

const AGENT_LABELS = {
  detection: '图像分割',
  facility_detection: '设施检测',
  analysis: '证据分析',
  review: '结果审核',
  report: '报告生成',
  evaluation: '模型评估',
  export: '数据导出',
  qa: '知识问答',
  chat: '通用对话',
}

function agentLabel(agent) {
  return AGENT_LABELS[agent] || agent
}

function workflowStatusLabel(status) {
  return {
    pending: '等待',
    running: '执行中',
    completed: '完成',
    partial: '部分完成',
    failed: '失败',
    skipped: '跳过',
  }[status] || status
}

function workflowStatusType(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed' || status === 'partial') return 'danger'
  if (status === 'running') return 'primary'
  if (status === 'skipped') return 'warning'
  return 'info'
}

async function downloadExport(exportResult) {
  try {
    const blob = await request.get(`/chat/exports/${encodeURIComponent(exportResult.filename)}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = exportResult.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error.message || '导出文件下载失败')
  }
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

function clearSelectedAttachments() {
  selectedAttachments.value.forEach((attachment) => {
    if (attachment.preview) URL.revokeObjectURL(attachment.preview)
  })
  selectedAttachments.value = []
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function removeSelectedAttachment(id) {
  const attachment = selectedAttachments.value.find((item) => item.id === id)
  if (attachment?.preview) URL.revokeObjectURL(attachment.preview)
  selectedAttachments.value = selectedAttachments.value.filter((item) => item.id !== id)
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function handleFileSelect(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) return

  const additions = files.map((file) => ({
    id: `attachment-${Date.now()}-${attachmentSequence++}`,
    file,
    preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
  }))
  selectedAttachments.value = [...selectedAttachments.value, ...additions]
  event.target.value = ''
  ElMessage.info(files.length === 1 ? `${files[0].name} 已添加` : `已添加 ${files.length} 个附件`)
}

async function sendSelectedImageBatch(files, message) {
  agentStore.setLoading(true)
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  formData.append('session_id', String(agentStore.currentSessionId))
  formData.append('message', message)

  try {
    const result = await segmentBatch(formData)
    agentStore.handleSessionEvent({ session_id: result.session_id }, agentStore.currentSessionId)
    const lastMsg = agentStore.messages[agentStore.messages.length - 1]
    if (result.error) {
      lastMsg.content = `批量分割失败：${result.error}`
      lastMsg.error = true
    } else {
      lastMsg.content = `批量分割完成！共 ${result.successful_images} 张图片。`
      lastMsg.segmentationResult = result
    }
    lastMsg.loading = false
    refreshSessionTitles()
  } catch (err) {
    const lastMsg = agentStore.messages[agentStore.messages.length - 1]
    lastMsg.content = `批量分割失败：${err.message || err}`
    lastMsg.loading = false
    lastMsg.error = true
  } finally {
    agentStore.setLoading(false)
    scrollToBottom()
  }
}

async function startCamera() {
  cameraError.value = ''
  cameraCaptureInProgress.value = false

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 1280, height: 720 },
      audio: false,
    })
    cameraMediaStream = stream
    cameraStream.value = stream
    await nextTick()
    if (cameraVideoRef.value) {
      cameraVideoRef.value.srcObject = stream
    }
  } catch (err) {
    cameraStream.value = null
    cameraError.value = err instanceof Error ? err.message : '摄像头启动失败，请检查权限和设备'
  }
}

function closeCameraDialog() {
  stopRealtimeRecognition()
  if (cameraMediaStream) {
    cameraMediaStream.getTracks().forEach((track) => track.stop())
    cameraMediaStream = null
  }
  cameraStream.value = null
  cameraError.value = ''
  cameraCaptureInProgress.value = false
  cameraDialogVisible.value = false
}

function canvasToBlob(canvas, type = 'image/jpeg', quality = 0.95) {
  return new Promise((resolve, reject) => {
    if (typeof canvas.toBlob !== 'function') {
      return reject(new Error('当前浏览器不支持 canvas.toBlob'))
    }
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('canvas 生成 Blob 失败'))
      } else {
        resolve(blob)
      }
    }, type, quality)
  })
}

async function captureCameraImage() {
  if (!cameraStream.value || !cameraVideoRef.value) return
  cameraCaptureInProgress.value = true

  try {
    const video = cameraVideoRef.value
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      throw new Error('无法获取画布上下文')
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

    const blob = await canvasToBlob(canvas, 'image/jpeg', 0.95)
    const file = new File([blob], `camera-${Date.now()}.jpg`, {
      type: 'image/jpeg',
    })

    closeCameraDialog()

    agentStore.addMessage({
      role: 'user',
      content: '[快捷分割] 摄像头拍照',
      image: file.name,
    })
    agentStore.addMessage({
      role: 'assistant',
      content: '正在处理摄像头图像...',
      loading: true,
    })

    const formData = new FormData()
    formData.append('file', file)
    formData.append('session_id', String(agentStore.currentSessionId))
    const requestSessionId = agentStore.currentSessionId
    const result = await segmentSingle(formData)
    if (requestSessionId !== agentStore.currentSessionId) return
    agentStore.handleSessionEvent({ session_id: result.session_id }, requestSessionId)

    const lastMsg = agentStore.messages[agentStore.messages.length - 1]
    if (result.error) {
      lastMsg.content = `摄像头图像处理失败：${result.error}`
      lastMsg.loading = false
      lastMsg.error = true
    } else {
      lastMsg.content = `摄像头图像处理完成！尺寸 ${result.image_width}×${result.image_height}。`
      lastMsg.loading = false
      lastMsg.segmentationResult = result
    }
    refreshSessionTitles()
    scrollToBottom()
  } catch (err) {
    closeCameraDialog()
    const lastMsg = agentStore.messages[agentStore.messages.length - 1]
    if (lastMsg) {
      lastMsg.content = `摄像头拍照失败：${err instanceof Error ? err.message : err}`
      lastMsg.loading = false
      lastMsg.error = true
    }
  } finally {
    cameraCaptureInProgress.value = false
  }
}

async function captureCameraVideo() {
  if (!cameraStream.value || !cameraVideoRef.value) return
  cameraCaptureInProgress.value = true

  try {
    const captureCount = 6
    const frameIntervalMs = 500
    const files = []
    for (let idx = 0; idx < captureCount; idx += 1) {
      await new Promise((resolve) => setTimeout(resolve, frameIntervalMs))
      const video = cameraVideoRef.value
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth || 1280
      canvas.height = video.videoHeight || 720
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        throw new Error('无法获取画布上下文')
      }
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const blob = await canvasToBlob(canvas, 'image/jpeg', 0.95)
      files.push(new File([blob], `camera-frame-${idx + 1}.jpg`, { type: 'image/jpeg' }))
    }

    closeCameraDialog()

    agentStore.addMessage({
      role: 'user',
      content: '[快捷分割] 摄像头视频采样',
    })
    agentStore.addMessage({
      role: 'assistant',
      content: '正在处理摄像头视频帧...',
      loading: true,
    })

    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    formData.append('session_id', String(agentStore.currentSessionId))
    const requestSessionId = agentStore.currentSessionId
    const result = await segmentBatch(formData)
    if (requestSessionId !== agentStore.currentSessionId) return
    agentStore.handleSessionEvent({ session_id: result.session_id }, requestSessionId)

    const lastMsg = agentStore.messages[agentStore.messages.length - 1]
    if (result.error) {
      lastMsg.content = `摄像头视频分析失败：${result.error}`
      lastMsg.loading = false
      lastMsg.error = true
    } else {
      lastMsg.content = `摄像头视频分析完成！共 ${result.successful_images} 帧。`
      lastMsg.loading = false
      lastMsg.segmentationResult = result
    }
    refreshSessionTitles()
    scrollToBottom()
  } catch (err) {
    closeCameraDialog()
    const lastMsg = agentStore.messages[agentStore.messages.length - 1]
    if (lastMsg) {
      lastMsg.content = `摄像头视频分析失败：${err instanceof Error ? err.message : err}`
      lastMsg.loading = false
      lastMsg.error = true
    }
  } finally {
    cameraCaptureInProgress.value = false
  }
}

async function startRealtimeRecognition() {
  if (!cameraStream.value || !cameraVideoRef.value || cameraRealtimeRunning.value) return
  cameraRealtimeStopRequested.value = false
  cameraRealtimeRunning.value = true
  cameraCaptureInProgress.value = false

  agentStore.addMessage({
    role: 'user',
    content: '[快捷分割] 摄像头实时识别',
  })
  agentStore.addMessage({
    role: 'assistant',
    content: '实时识别已启动，将显示每帧结果。',
    loading: false,
  })
  scrollToBottom()

  let frameIndex = 0
  const frameIntervalMs = 800

  while (!cameraRealtimeStopRequested.value && cameraStream.value && cameraVideoRef.value) {
    frameIndex += 1
    try {
      const video = cameraVideoRef.value
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth || 1280
      canvas.height = video.videoHeight || 720
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        throw new Error('无法获取画布上下文')
      }
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const blob = await canvasToBlob(canvas, 'image/jpeg', 0.8)
      const file = new File([blob], `camera-realtime-${Date.now()}-${frameIndex}.jpg`, {
        type: 'image/jpeg',
      })
      const formData = new FormData()
      formData.append('file', file)
      // 实时识别不携带 session_id，避免逐帧写入会话；停止时仅保留前端聚合提示。
      const result = await segmentSingle(formData)

      if (result.error) {
        agentStore.addMessage({
          role: 'assistant',
          content: `第 ${frameIndex} 帧识别失败：${result.error}`,
          loading: false,
          error: true,
        })
        scrollToBottom()
        break
      }

      agentStore.addMessage({
        role: 'assistant',
        content: `实时识别第 ${frameIndex} 帧：检测到 ${result.class_statistics?.length || 0} 类。`,
        loading: false,
        segmentationResult: result,
      })
      scrollToBottom()
    } catch (err) {
      agentStore.addMessage({
        role: 'assistant',
        content: `实时识别第 ${frameIndex} 帧出错：${err instanceof Error ? err.message : err}`,
        loading: false,
        error: true,
      })
      scrollToBottom()
      break
    }

    await new Promise((resolve) => setTimeout(resolve, frameIntervalMs))
  }

  cameraRealtimeRunning.value = false
}

function stopRealtimeRecognition() {
  cameraRealtimeStopRequested.value = true
  cameraRealtimeRunning.value = false
  agentStore.addMessage({
    role: 'assistant',
    content: '实时识别已停止。',
    loading: false,
  })
}

async function openCameraDialog() {
  cameraDialogVisible.value = true
  await nextTick()
  await startCamera()
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
      formData.append('session_id', String(agentStore.currentSessionId))

      try {
        const result = await segmentSingle(formData)
        agentStore.handleSessionEvent({ session_id: result.session_id }, agentStore.currentSessionId)
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `分割完成！图片尺寸 ${result.image_width}×${result.image_height}。`
        lastMsg.loading = false
        lastMsg.segmentationResult = result
        refreshSessionTitles()
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = '分割失败，请重试'
        lastMsg.loading = false
        lastMsg.error = true
      }
      scrollToBottom()
    }
    input.click()
  } else if (type === 'video') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'video/*'
    input.onchange = async (e) => {
      const file = e.target.files[0]
      if (!file) return

      agentStore.addMessage({
        role: 'user',
        content: `[快捷分割] 视频: ${file.name}`,
        image: file.name,
      })

      agentStore.addMessage({
        role: 'assistant',
        content: '正在处理视频中...',
        loading: true,
      })

      const formData = new FormData()
      formData.append('file', file)
      formData.append('frame_sample_rate', '5')
      formData.append('max_frames', '30')

      try {
        const result = await segmentVideo(formData)
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        if (result.error) {
          lastMsg.content = `视频分割失败：${result.error}`
          lastMsg.loading = false
          lastMsg.error = true
          return
        }
        lastMsg.content = `视频分割完成！处理 ${result.processed_frames} 帧。`
        lastMsg.loading = false
        lastMsg.segmentationResult = result
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `视频分割失败：${err.message || err}`
        lastMsg.loading = false
        lastMsg.error = true
      }
      scrollToBottom()
    }
    input.click()
  } else if (type === 'camera') {
    openCameraDialog()
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
      formData.append('session_id', String(agentStore.currentSessionId))

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
        agentStore.handleSessionEvent({ session_id: result.session_id }, agentStore.currentSessionId)
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
        refreshSessionTitles()
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

function formatSessionTime(value) {
  return value ? new Date(value).toLocaleString() : ''
}

async function renameSession(session) {
  try {
    const { value } = await ElMessageBox.prompt('输入新会话名称', '重命名', {
      inputValue: session.title || '',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    await agentStore.renameSession(session.id, value.trim())
  } catch {
    // 用户取消。
  }
}

async function removeSession(session) {
  try {
    await ElMessageBox.confirm(`确定删除“${session.title || '新会话'}”及其历史消息？`, '删除会话', {
      type: 'warning',
    })
    await agentStore.deleteSession(session.id)
  } catch {
    // 用户取消。
  }
}

onMounted(async () => {
  try {
    await agentStore.initialize(userStore.user?.id)
  } catch (error) {
    ElMessage.error(`会话初始化失败：${error.message || error}`)
  }
})

onBeforeUnmount(() => {
  selectedAttachments.value.forEach((attachment) => {
    if (attachment.preview) URL.revokeObjectURL(attachment.preview)
  })
})
</script>

<style lang="scss" scoped>
.chat-page {
  display: flex;
  flex-direction: row;
  height: 100%;
  min-height: 0;
  background: transparent;
}

.chat-main {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
}

.session-sidebar {
  width: 240px;
  padding: 14px 12px;
  overflow-y: auto;
  border-right: 1px solid rgba(78, 103, 138, 0.14);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(246, 249, 253, 0.9));
}

.new-session {
  width: 100%;
  margin-bottom: 14px;
  border-radius: 10px;
  box-shadow: 0 10px 22px rgba($primary-color, 0.18);
}

.session-item {
  padding: 11px 10px;
  margin-bottom: 8px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.86);
  border-color: rgba($primary-color, 0.18);
  box-shadow: 0 8px 20px rgba(20, 33, 56, 0.06);
  transform: translateY(-1px);
}

.session-item.active {
  background: linear-gradient(135deg, rgba($primary-color, 0.12), rgba($info-color, 0.06));
  border-color: rgba($primary-color, 0.24);
  box-shadow: 0 10px 24px rgba($primary-color, 0.1);
}
.session-title { overflow: hidden; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.session-time { margin-top: 4px; color: $text-secondary; font-size: 11px; }
.session-actions { display: flex; justify-content: flex-end; }
.session-empty, .load-more { color: $text-secondary; text-align: center; }

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
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
  padding: 13px 16px;
  border-radius: 14px;
  line-height: 1.5;
  word-break: break-word;
}

.user-bubble {
  background: linear-gradient(135deg, $primary-color, $info-color);
  color: #fff;
  border-bottom-right-radius: 5px;
  box-shadow: 0 12px 26px rgba($primary-color, 0.18);
}

.assistant-bubble {
  background: linear-gradient(150deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 253, 0.94));
  border: 1px solid rgba(122, 146, 181, 0.16);
  border-bottom-left-radius: 5px;
  box-shadow: 0 8px 24px rgba(20, 33, 56, 0.06);
}

.workflow-progress {
  min-width: 320px;
  margin-bottom: 10px;
  padding: 10px;
  border: 1px solid rgba($primary-color, 0.2);
  border-radius: 8px;
  background: rgba($primary-color, 0.08);
}

.workflow-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: $text-primary;
  font-size: 13px;
  font-weight: 600;
}

.workflow-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.markdown-content {
  overflow-x: auto;
  white-space: normal;

  :deep(> :first-child) {
    margin-top: 0;
  }

  :deep(> :last-child) {
    margin-bottom: 0;
  }

  :deep(h1),
  :deep(h2),
  :deep(h3),
  :deep(h4),
  :deep(h5),
  :deep(h6) {
    margin: 1em 0 0.5em;
    color: $text-primary;
    line-height: 1.3;
  }

  :deep(h1) { font-size: 1.5em; }
  :deep(h2) { font-size: 1.3em; }
  :deep(h3) { font-size: 1.15em; }

  :deep(p),
  :deep(ul),
  :deep(ol),
  :deep(blockquote),
  :deep(pre),
  :deep(table) {
    margin: 0.65em 0;
  }

  :deep(ul),
  :deep(ol) {
    padding-left: 1.6em;
  }

  :deep(table) {
    width: max-content;
    min-width: 100%;
    border-spacing: 0;
    border-collapse: collapse;
  }

  :deep(th),
  :deep(td) {
    padding: 6px 10px;
    border: 1px solid rgba(122, 146, 181, 0.16);
    text-align: left;
    white-space: nowrap;
  }

  :deep(th) {
    background: rgba($primary-color, 0.07);
    font-weight: 600;
  }

  :deep(blockquote) {
    padding-left: 12px;
    border-left: 4px solid rgba(122, 146, 181, 0.32);
    color: $text-secondary;
  }

  :deep(pre) {
    overflow-x: auto;
    padding: 12px;
    border: 1px solid rgba(122, 146, 181, 0.16);
    border-radius: 6px;
    background: rgba(78, 103, 138, 0.07);
    color: $text-primary;
  }

  :deep(code) {
    padding: 0.15em 0.35em;
    border-radius: 4px;
    background: rgba(78, 103, 138, 0.1);
    font-family: Consolas, Monaco, monospace;
  }

  :deep(pre code) {
    padding: 0;
    background: transparent;
    color: inherit;
  }

  :deep(a) {
    color: $primary-color;
    text-decoration: none;
  }

  :deep(a:hover) {
    text-decoration: underline;
  }
}

.typing-indicator {
  display: flex;
  gap: 4px;

  span {
    width: 6px;
    height: 6px;
    background: rgba($primary-color, 0.45);
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
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 20px 10px;
  border-top: 1px solid rgba(122, 146, 181, 0.16);
  background: rgba(248, 250, 253, 0.88);

  :deep(.el-button) {
    margin-left: 0;
    border-color: rgba(78, 103, 138, 0.14);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.86);
    color: $text-regular;
  }

  :deep(.el-button:hover) {
    color: $primary-dark;
    border-color: rgba($primary-color, 0.32);
    background: rgba($primary-color, 0.07);
  }
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 20px 16px;
  border-top: 1px solid rgba(122, 146, 181, 0.16);
  background: rgba(248, 250, 253, 0.94);

  .el-input {
    flex: 1;
  }

  :deep(.el-input__wrapper) {
    min-height: 40px;
    border-radius: 12px;
    box-shadow: 0 0 0 1px rgba(78, 103, 138, 0.14) inset;
  }

  :deep(.el-input__wrapper.is-focus) {
    box-shadow: 0 0 0 1px rgba($primary-color, 0.42) inset, 0 8px 22px rgba($primary-color, 0.08);
  }

  :deep(.el-button) {
    border-radius: 10px;
  }
}

.pending-attachments {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding: 10px 20px;
  border-top: 1px solid rgba(122, 146, 181, 0.16);
  background: rgba(248, 250, 253, 0.94);
}

.pending-attachment-card {
  position: relative;
  display: flex;
  width: 82px;
  min-width: 82px;
  flex-direction: column;
  gap: 3px;
}

.pending-attachment-preview,
.pending-attachment-file {
  width: 80px;
  height: 80px;
  border: 1px solid rgba(122, 146, 181, 0.16);
  border-radius: 8px;
  box-shadow: 0 8px 18px rgba(20, 33, 56, 0.08);
}

.pending-attachment-preview {
  object-fit: cover;
}

.pending-attachment-file {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(78, 103, 138, 0.06);
  color: $text-secondary;
  font-size: 12px;
  font-weight: 600;
}

.pending-attachment-name {
  width: 80px;
  overflow: hidden;
  color: $text-primary;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-attachment-size {
  color: $text-secondary;
  font-size: 12px;
}

.pending-attachment-remove {
  position: absolute;
  top: -7px;
  right: -5px;
  display: flex;
  width: 22px;
  height: 22px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 2px solid rgba(255, 255, 255, 0.98);
  border-radius: 50%;
  background: $danger-color;
  color: #fff;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  z-index: 1;
}

.pending-attachment-remove:hover {
  background: $danger-color;
}

.message-attachment {
  margin-top: 8px;

  img {
    max-width: 200px;
    border-radius: 8px;
    border: 1px solid rgba(122, 146, 181, 0.16);
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
    border: 1px solid rgba(122, 146, 181, 0.16);
  }
}

.tool-call-info {
  margin-top: 8px;
  padding: 4px 8px;
  background: transparent;
  border-radius: 6px;
  font-size: 12px;
  color: $text-secondary;

  :deep(.el-tag) {
    gap: 5px;
    border-color: rgba($info-color, 0.18);
    background: rgba($info-color, 0.08);
    color: $text-secondary;
  }
}

.camera-dialog {
  max-height: 80vh;
}

.camera-dialog .el-dialog__body {
  padding: 16px;
  overflow: hidden;
}

.camera-dialog .el-dialog__footer {
  position: sticky;
  bottom: 0;
  background: rgba(255, 255, 255, 0.98);
  border-top: 1px solid rgba(122, 146, 181, 0.14);
  z-index: 10;
}

.camera-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 65vh;
  overflow: hidden;
  padding-bottom: 0;
}

.camera-preview-wrapper,
.camera-error-wrapper {
  width: 100%;
  max-height: 55vh;
  overflow: hidden;
}

.camera-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 8px;
  background: rgba(22, 34, 53, 0.92);
  box-shadow: 0 10px 28px rgba(20, 33, 56, 0.12);
}

.camera-error-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  gap: 12px;
  text-align: center;
}

.camera-error-message {
  color: $danger-color;
  font-size: 14px;
}

.el-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
}

@media (max-width: 768px) {
  .chat-page {
    flex-direction: column;
  }

  .session-sidebar {
    width: 100%;
    max-height: 220px;
    border-right: 0;
    border-bottom: 1px solid rgba(78, 103, 138, 0.14);
  }

  .message-list {
    padding: 16px;
  }

  .message-bubble {
    max-width: 90%;
  }

  .quick-actions,
  .input-area,
  .pending-attachments {
    padding-right: 14px;
    padding-left: 14px;
  }
}

@media (max-width: 560px) {
  .input-area {
    flex-wrap: wrap;

    .el-input {
      flex-basis: calc(100% - 48px);
    }
  }

  .quick-actions :deep(.el-button) {
    flex: 1 1 calc(50% - 8px);
  }
}

@media (max-width: 420px) {
  .quick-actions :deep(.el-button) {
    flex-basis: 100%;
  }
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
