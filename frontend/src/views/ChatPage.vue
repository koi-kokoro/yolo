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
      <el-button @click="handleQuickSegment('video')" :disabled="agentStore.isLoading">
        🎬 视频
      </el-button>
      <el-button @click="handleQuickSegment('camera')" :disabled="agentStore.isLoading">
        📹 摄像头
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
import { segmentBatch, segmentSingle, segmentVideo, segmentZip } from '@/api/segmentation'
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
const cameraVideoRef = ref(null)
const cameraDialogVisible = ref(false)
const cameraStream = ref(null)
const cameraError = ref('')
const cameraCaptureInProgress = ref(false)
const cameraRealtimeRunning = ref(false)
const cameraRealtimeStopRequested = ref(false)
let cameraMediaStream = null

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
    const result = await segmentSingle(formData)

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
    const result = await segmentBatch(formData)

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
  background: #fff;
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
  background: #000;
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
  color: #f56c6c;
  font-size: 14px;
}

.el-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
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
