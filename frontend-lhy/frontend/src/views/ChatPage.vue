<template>
  <div class="chat-page">
    <!-- ── 欢迎空状态页面 ── -->
    <div v-if="agentStore.messages.length === 0" class="welcome-container">
      <div class="welcome-card">
        <div class="welcome-header">
          <div class="avatar-container">
            <div class="avatar">
              <span class="avatar-icon">🌾</span>
            </div>
            <div class="avatar-glow"></div>
          </div>
          <h1 class="welcome-title">RSOD 目标检测智能体</h1>
          <p class="welcome-subtitle">基于 YOLOv8 的实时目标检测系统</p>
        </div>
        
        <div class="feature-cards">
          <div 
            class="feature-card" 
            @click="handleQuickDetect('single')"
            :class="{ disabled: agentStore.isLoading }"
          >
            <div class="feature-icon single-icon">📷</div>
            <h3 class="feature-title">单图检测</h3>
            <p class="feature-desc">上传单张图片进行目标检测</p>
          </div>
          
          <div 
            class="feature-card" 
            @click="handleQuickDetect('batch')"
            :class="{ disabled: agentStore.isLoading }"
          >
            <div class="feature-icon batch-icon">📁</div>
            <h3 class="feature-title">批量检测</h3>
            <p class="feature-desc">批量上传图片或 ZIP 文件</p>
          </div>
          
          <div 
            class="feature-card" 
            @click="handleVideoDetect"
            :class="{ disabled: agentStore.isLoading }"
          >
            <div class="feature-icon video-icon">🎬</div>
            <h3 class="feature-title">视频检测</h3>
            <p class="feature-desc">上传视频文件进行逐帧分析</p>
          </div>
          
          <div 
            class="feature-card" 
            @click="handleCameraDetect"
            :class="{ disabled: agentStore.isLoading }"
          >
            <div class="feature-icon camera-icon">📹</div>
            <h3 class="feature-title">实时监控</h3>
            <p class="feature-desc">使用摄像头进行实时检测</p>
          </div>
        </div>
        
        <div class="welcome-tips">
          <p>💡 提示：您可以直接输入消息与智能体对话，或选择上方功能进行检测</p>
        </div>
      </div>
    </div>

    <!-- ── 消息列表区域 ── -->
    <div v-else class="message-container">
      <div class="message-list" ref="messageListRef">
        <div
          v-for="(msg, index) in agentStore.messages"
          :key="index"
          :class="['message-item', `message-${msg.role}`]"
        >
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="message-bubble user-bubble">
            <div class="message-content">{{ msg.content }}</div>
            <!-- 单张图片附件 -->
            <div v-if="msg.image" class="message-attachment">
              <img :src="msg.imagePreview" alt="附件图片" />
            </div>
            <!-- 多图附件（批量检测） -->
            <div v-if="msg.images && msg.images.length" class="message-attachments-grid">
              <img v-for="(src, i) in msg.images" :key="i" :src="src" alt="附件图片" />
            </div>
            <!-- 视频附件 -->
            <div v-if="msg.videoUrl" class="message-attachment video-attachment">
              <video :src="msg.videoUrl" controls preload="metadata"></video>
            </div>
          </div>

          <!-- AI 消息 -->
          <div
            v-else-if="msg.role === 'assistant'"
            class="message-bubble assistant-bubble"
          >
            <div v-if="msg.loading" class="typing-indicator">
              <span></span><span></span><span></span>
            </div>
            <div
              v-else
              class="message-content markdown-body"
              v-html="renderMarkdown(msg.content)"
            ></div>

            <!-- 工具调用状态展示 -->
            <div
              v-if="msg.toolCalls && msg.toolCalls.length > 0"
              class="tool-calls"
            >
              <div
                v-for="(tc, idx) in msg.toolCalls"
                :key="idx"
                class="tool-call-item"
                :class="{ 'is-loading': tc.status === 'loading' }"
              >
                <el-icon v-if="tc.status === 'loading'" class="is-loading">
                  <Loading />
                </el-icon>
                <el-icon v-else color="#67c23a"><CircleCheckFilled /></el-icon>
                <span class="tool-name">{{ getToolName(tc.tool) }}</span>
                <span v-if="tc.summary" class="tool-summary">{{ tc.summary }}</span>
              </div>
            </div>

            <!-- 检测结果卡片 -->
            <div v-if="msg.detectionResult" class="result-wrapper">
              <DetectionResultCard :result="msg.detectionResult" />
            </div>
          </div>

          <!-- 工具调用提示 -->
          <div v-if="msg.toolCall" class="tool-call-info">
            <el-tag size="small" type="info" effect="light" round>
              <span class="tool-icon">🔧</span> 调用工具: {{ msg.toolCall.tool }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 底部输入区域 ── -->
    <div class="bottom-input-wrapper">
      <div class="input-card">
        <div class="input-area">
          <div class="tool-bar">
            <div class="tool-buttons">
              <button 
                class="tool-btn" 
                @click="handleQuickDetect('single')"
                :disabled="agentStore.isLoading"
                title="单图检测"
              >
                <span class="tool-icon">📷</span>
                <span class="tool-text">单图</span>
              </button>
              <button 
                class="tool-btn" 
                @click="handleQuickDetect('batch')"
                :disabled="agentStore.isLoading"
                title="批量检测"
              >
                <span class="tool-icon">📁</span>
                <span class="tool-text">批量</span>
              </button>
              <button 
                class="tool-btn" 
                @click="handleVideoDetect"
                :disabled="agentStore.isLoading"
                title="视频检测"
              >
                <span class="tool-icon">🎬</span>
                <span class="tool-text">视频</span>
              </button>
              <button 
                class="tool-btn camera-tool-btn" 
                @click="handleCameraDetect"
                :disabled="agentStore.isLoading"
                title="摄像头"
              >
                <span class="tool-icon">📹</span>
                <span class="tool-text">监控</span>
              </button>
            </div>
            
            <div class="divider"></div>
            
            <button
              class="attach-btn"
              @click="triggerFileInput"
              :disabled="agentStore.isLoading"
            >
              📎
            </button>
            
            <input
              ref="fileInputRef"
              type="file"
              accept="image/*,.zip"
              style="display: none"
              @change="handleFileSelect"
            />
          </div>
          
          <div class="input-row">
            <el-input
              v-model="inputText"
              placeholder="输入消息，或拖拽图片/ZIP 到这里..."
              @keyup.enter="sendMessage"
              :disabled="agentStore.isLoading"
              class="custom-input"
              size="large"
            />

            <button
              v-if="!agentStore.isLoading"
              class="send-btn"
              @click="sendMessage"
              :disabled="!inputText.trim() && !selectedFile"
            >
              <span class="send-icon">➤</span>
            </button>
            <button 
              v-else 
              class="stop-btn"
              @click="handleStop" 
            >
              <span class="stop-icon">⏹</span>
            </button>
          </div>
        </div>
      </div>
    </div>
    <!-- 实时监控弹窗 (基于 WebSocket 协议) -->
    <el-dialog 
      v-model="streamDialogVisible" 
      title="🔴 实时摄像头监控" 
      width="800px" 
      class="dark-stream-dialog"
      :before-close="stopStream"
      destroy-on-close
    >
      <div class="stream-container">
        <!-- 接收后端返回的带框图像 -->
        <img v-if="annotatedFrame" :src="annotatedFrame" class="live-feed" />
        <div v-else class="loading-feed">
          <span class="loading-spinner"></span>
          <p>正在连接摄像头并初始化 WebSocket...</p>
        </div>
        
        <!-- 隐藏的源视频和画布（用于抽帧截取发送给后端） -->
        <video ref="videoRef" style="display:none" autoplay muted playsinline></video>
        <canvas ref="canvasRef" style="display:none"></canvas>
      </div>
      
      <!-- 实时数据看板 -->
      <div class="stream-stats">
        <div class="stat-item">
          <div class="stat-label">FPS 帧率</div>
          <div class="stat-value text-green">{{ streamStats.fps || '0.0' }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">目标数量</div>
          <div class="stat-value text-blue">{{ streamStats.object_count || '0' }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">推理耗时</div>
          <div class="stat-value text-orange">{{ streamStats.inference_time || '0.0' }} ms</div>
        </div>
      </div>
    </el-dialog>

  </div>
</template>

<script setup>
import { detectBatch, detectSingle, detectVideo, detectZip } from "@/api/detection";
import DetectionResultCard from "@/components/DetectionResultCard.vue";
import { useAgentStore } from "@/stores/agent";
import { renderMarkdown } from "@/utils/markdown";
import request from "@/utils/request";
import { streamChat } from "@/utils/stream";
import { CircleCheckFilled, Loading } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

// ── Store ──
const agentStore = useAgentStore();

// ── 响应式状态 ──
const inputText = ref("");
const selectedFile = ref(null);
const messageListRef = ref(null);
const fileInputRef = ref(null);

// WebSocket 相关响应式状态
const streamDialogVisible = ref(false);
const videoRef = ref(null);
const canvasRef = ref(null);
const annotatedFrame = ref("");
const streamStats = ref({ fps: 0, object_count: 0, inference_time: 0 });
let ws = null;
let frameTimer = null;
let mediaStream = null;

// ── 计算属性 ──
const canSend = computed(() => {
  return inputText.value.trim() || selectedFile.value;
});

// ── 方法 ──

/** 发送消息 */
async function sendMessage() {
  if (!canSend.value) return;

  const message = inputText.value.trim();
  const fileToSend = selectedFile.value;
  const imagePreview = fileToSend ? URL.createObjectURL(fileToSend) : null;

  // 添加用户消息到列表
  agentStore.addMessage({
    role: "user",
    content: message,
    image: fileToSend ? fileToSend.name : null,
    imagePreview,
  });

  // 清空输入
  inputText.value = "";
  selectedFile.value = null;

  // 添加 AI 加载占位（增强版：带 toolCalls 数组）
  agentStore.addMessage({
    role: "assistant",
    content: "",
    loading: true,
    toolCalls: [],
  });

  // 滚动到底部
  scrollToBottom();

  // ── 如果有附件图片，先上传到服务端获取真实路径 ──
  let serverImagePath = null;
  if (fileToSend) {
    try {
      const formData = new FormData();
      formData.append("file", fileToSend);
      const uploadResult = await request.post("/chat/upload", formData);
      serverImagePath = uploadResult.image_path;
    } catch (err) {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1];
      lastMsg.content = `图片上传失败：${err.response?.data?.detail || err.message || "未知错误"}，请重试`;
      lastMsg.loading = false;
      lastMsg.error = true;
      return;
    }
  }

  // 发起 SSE 流式请求
  const requestBody = {
    message,
    ...(serverImagePath ? { image_path: serverImagePath } : {}),
  };

  let fullContent = "";

  const abortController = new AbortController();

  streamChat({
    message: requestBody.message,
    image_path: requestBody.image_path,
    signal: abortController.signal,
    onTextChunk: (data) => {
      fullContent += data.content;
      agentStore.updateLastAssistantMessage(fullContent);
      scrollToBottom();
    },
    onToolStart: (data) => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1];
      if (!lastMsg.toolCalls) lastMsg.toolCalls = [];
      lastMsg.toolCalls.push({
        tool: data.tool,
        status: "loading",
        summary: "",
      });
      scrollToBottom();
    },
    onToolEnd: (data) => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1];
      if (!lastMsg.toolCalls) lastMsg.toolCalls = [];
      const tc = lastMsg.toolCalls.find(
        (t) => t.tool === data.tool && t.status === "loading",
      );
      if (tc) {
        tc.status = "done";
        tc.summary = data.summary?.slice(0, 80) || "完成";
      }
      scrollToBottom();
    },
    onDone: () => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1];
      if (lastMsg.loading) {
        lastMsg.loading = false;
      }
      agentStore.setLoading(false);
    },
    onError: (err) => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1];
      lastMsg.content = `抱歉，处理出错了：${err.message}`;
      lastMsg.loading = false;
      lastMsg.error = true;
      agentStore.setLoading(false);
      ElMessage.error("对话请求失败，请重试");
    },
  }).catch(() => {});

  agentStore.abortController = abortController;
}

/** 停止生成 */
function handleStop() {
  agentStore.abort();
  const lastMsg = agentStore.messages[agentStore.messages.length - 1];
  if (lastMsg.loading) {
    lastMsg.loading = false;
    lastMsg.content += "\n[已停止生成]";
  }
}

/** 触发文件选择框 */
function triggerFileInput() {
  fileInputRef.value?.click();
}

/** 文件选择回调 */
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (file) {
    selectedFile.value = file;
    file._tempPath = URL.createObjectURL(file);
    ElMessage.info(`${file.name} 已选择`);
  }
}

/** 滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
    }
  });
}

/** 快捷单图检测流程 */
async function handleQuickDetect(type) {
  if (type === "single") {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      agentStore.addMessage({
        role: "user",
        content: `[快捷检测] ${file.name}`,
        image: file.name,
        imagePreview: URL.createObjectURL(file),
      });

      agentStore.addMessage({
        role: "assistant",
        content: "正在检测中...",
        loading: true,
      });

      const formData = new FormData();
      formData.append("file", file);

      try {
        const result = await detectSingle(formData);
        const lastMsg = agentStore.messages[agentStore.messages.length - 1];
        lastMsg.content = `检测完成！发现 ${result.total_objects} 个目标。`;
        lastMsg.loading = false;
        lastMsg.detectionResult = result;
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1];
        lastMsg.content = "检测失败，请重试";
        lastMsg.loading = false;
      }
    };
    input.click();
  } else if (type === "batch") {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*,.zip";
    input.multiple = true;
    input.onchange = async (e) => {
      const files = Array.from(e.target.files);
      if (!files.length) return;

      const isZip = files.some((f) => f.name.endsWith(".zip"));
      const formData = new FormData();

      if (isZip && files.length === 1) {
        formData.append("file", files[0]);
        agentStore.addMessage({
          role: "user",
          content: `[快捷检测] ZIP: ${files[0].name}`,
        });
      } else {
        files.forEach((f) => formData.append("files", f));
        const imagePreviews = files.map((f) => URL.createObjectURL(f));
        agentStore.addMessage({
          role: "user",
          content: `[快捷检测] ${files.length} 张图片`,
          images: imagePreviews,
        });
      }

      agentStore.addMessage({
        role: "assistant",
        content: "正在批量检测中...",
        loading: true,
      });

      try {
        const apiCall = isZip ? detectZip(formData) : detectBatch(formData);
        const result = await apiCall;
        const lastMsg = agentStore.messages[agentStore.messages.length - 1];

        if (result.error) {
          lastMsg.content = `批量检测失败：${result.error}`;
          lastMsg.loading = false;
          lastMsg.error = true;
          return;
        }

        const totalObjects = result.total_objects ?? 0;
        lastMsg.content = `批量检测完成！共 ${totalObjects} 个目标。`;
        lastMsg.loading = false;
        lastMsg.detectionResult = result;
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1];
        lastMsg.content = `批量检测失败：${err.message || err}`;
        lastMsg.loading = false;
        lastMsg.error = true;
      }
    };
    input.click();
  }
}
/**
 * 视频检测流程：
 * 1. 用户点击 "🎬 视频" 按钮
 * 2. 弹出文件选择框（限制视频格式）
 * 3. 选择视频后，上传到后端
 * 4. 后端返回 task_id，前端开始轮询进度
 * 5. 处理完成后，展示关键帧结果卡片
 */
async function handleVideoDetect() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "video/mp4,video/avi,video/quicktime,video/x-msvideo";
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // 校验文件大小（50MB）
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      ElMessage.warning("视频文件不能超过 50MB");
      return;
    }

    // 创建视频的 Blob URL 用于预览
    const videoUrl = URL.createObjectURL(file);

    // 添加用户消息
    agentStore.addMessage({
      role: "user",
      content: `[视频检测] ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)}MB)`,
      videoUrl,
    });

    // 添加加载占位
    agentStore.addMessage({
      role: "assistant",
      content: "正在上传视频...",
      loading: true,
    });

    // 上传视频
    const formData = new FormData();
    formData.append("file", file);

    try {
      const uploadResult = await detectVideo(formData);
      const taskId = uploadResult.task_id;

      // 更新加载消息
      const lastMsg = agentStore.messages[agentStore.messages.length - 1];
      lastMsg.content = "视频已上传，正在处理中...";

      // 开始轮询进度
      await pollVideoProgress(taskId);
    } catch (err) {
      console.error("[视频检测失败]", err);
      const lastMsg = agentStore.messages[agentStore.messages.length - 1];
      lastMsg.content = `视频检测失败：${err.message || err}`;
      lastMsg.loading = false;
      lastMsg.error = true;
    }
  };
  input.click();
}

/**
 * 轮询视频检测进度
 * @param {number} taskId - 视频检测任务 ID
 */
async function pollVideoProgress(taskId) {
  const maxRetries = 300;
  let retries = 0;

  return new Promise((resolve, reject) => {
    const timer = setInterval(async () => {
      retries++;

      try {
        const status = await getVideoStatus(taskId);

        const lastMsg = agentStore.messages[agentStore.messages.length - 1];

        if (status.status === "completed") {
          clearInterval(timer);
          lastMsg.content = `视频检测完成！共处理 ${status.result?.processed_frames || 0} 帧，发现 ${status.result?.total_objects || 0} 个目标。`;
          lastMsg.loading = false;
          lastMsg.detectionResult = {
            ...status.result,
            type: "video",
          };
          resolve(status);
        } else if (status.status === "failed") {
          clearInterval(timer);
          lastMsg.content = `视频检测失败：${status.message || "未知错误"}`;
          lastMsg.loading = false;
          lastMsg.error = true;
          reject(new Error(status.message));
        } else {
          lastMsg.content = `视频处理中... ${status.message || ""}`;
        }

        if (retries >= maxRetries) {
          clearInterval(timer);
          const lastMsg = agentStore.messages[agentStore.messages.length - 1];
          lastMsg.content = "视频处理超时，请稍后在历史记录中查看结果";
          lastMsg.loading = false;
          reject(new Error("timeout"));
        }
      } catch (err) {
        console.error("[轮询视频进度失败]", err);
      }
    }, 1000);
  });
}

/**
 * 工具名称映射
 */
function getToolName(toolKey) {
  return TOOL_NAME_MAP[toolKey] || toolKey;
}

/* ==============================================================
   严格按文档协议编写的 WebSocket 摄像头检测逻辑
   ============================================================== */

/** 打开摄像头并连接 WebSocket */
async function handleCameraDetect() {
  streamDialogVisible.value = true;
  await nextTick();
  
  try {
    // 请求调用电脑摄像头
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    videoRef.value.srcObject = mediaStream;
    videoRef.value.play();
    
    // 初始化 WebSocket 握手
    initWebSocket();
  } catch (err) {
    ElMessage.error("无法访问摄像头，请检查权限设置");
    streamDialogVisible.value = false;
  }
}

/** 协议实现核心：WebSocket 连接 */
function initWebSocket() {
  // ⚠️ 请确认后端的 WebSocket 地址是否需要带 /api (根据你刚才 Swagger 里看到的实际情况填写)
  const wsUrl = "ws://127.0.0.1:8000/api/detection/camera"; 
  ws = new WebSocket(wsUrl);

  // 【协议 1】：连接成功，发送初始化配置
  ws.onopen = () => {
    ws.send(JSON.stringify({
      type: "config",
      mode: "cpu", // 可选: "gpu"
      conf: 0.25,
      scene_id: 1
    }));
    
    // 配置发完后，启动抽帧发送循环
    startFrameLoop();
  };

  // 【协议 2&3】：接收后端返回的检测结果 / 错误信息
  ws.onmessage = (event) => {
    try {
      const res = JSON.parse(event.data);
      if (res.type === "result") {
        // 渲染带标注的 JPEG (需要加上 data:image/jpeg;base64, 前缀才能在 img 显示)
        annotatedFrame.value = "data:image/jpeg;base64," + res.annotated_frame;
        // 渲染统计指标
        streamStats.value = {
          fps: res.fps,
          object_count: res.object_count,
          inference_time: res.inference_time
        };
      } else if (res.type === "error") {
        console.error("检测错误:", res.message);
        ElMessage.error(res.message);
      }
    } catch (e) {
      console.error("解析 WebSocket 消息失败", e);
    }
  };

  ws.onerror = () => {
    ElMessage.error("WebSocket 连接失败，请检查后端服务");
    stopStream();
  };
}

/** 协议实现核心：抽帧发送 (Frame) */
function startFrameLoop() {
  const canvas = canvasRef.value;
  const ctx = canvas.getContext('2d');
  
  // 以大概 10 FPS (100毫秒) 的频率抽取画面并发送
  frameTimer = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!videoRef.value || videoRef.value.paused || videoRef.value.ended) return;

    // 对齐 Canvas 与视频尺寸
    if (canvas.width !== videoRef.value.videoWidth) {
       canvas.width = videoRef.value.videoWidth;
       canvas.height = videoRef.value.videoHeight;
    }

    // 绘制当前画面
    ctx.drawImage(videoRef.value, 0, 0, canvas.width, canvas.height);
    
    // 导出 JPEG base64 (协议要求纯数据，切除前缀 "data:image/jpeg;base64,")
    const fullBase64 = canvas.toDataURL("image/jpeg", 0.8);
    const base64Data = fullBase64.split(",")[1];

    if (base64Data) {
      ws.send(JSON.stringify({
        type: "frame",
        data: base64Data
      }));
    }
  }, 100); 
}

/** 协议实现核心：关闭连接 (Close) */
function stopStream(done) {
  // 1. 发送关闭连接的报文
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "close" }));
    ws.close();
  }
  // 2. 清理定时器
  if (frameTimer) clearInterval(frameTimer);
  
  // 3. 彻底释放摄像头物理资源
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }
  
  // 4. 数据复位
  annotatedFrame.value = "";
  streamStats.value = { fps: 0, object_count: 0, inference_time: 0 };
  ws = null;
  
  streamDialogVisible.value = false;
  if (typeof done === "function") done();
}
onMounted(() => {
 
});

// 组件卸载时安全释放资源
onBeforeUnmount(() => {
  stopStream();
});
</script>

<style lang="scss" scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-image: url("@/assets/AI生成1784517440315.png");
  background-size: cover;
  background-position: center;
  position: relative;
}

.chat-page::before {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  pointer-events: none;
}

.welcome-container {
  flex: 1;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 80px 40px 40px;
  position: relative;
  z-index: 1;
}

.welcome-card {
  max-width: 600px;
  width: 100%;
  background: rgba(26, 22, 18, 0.95);
  backdrop-filter: blur(30px);
  -webkit-backdrop-filter: blur(30px);
  border-radius: 32px;
  border: 1px solid rgba(139, 115, 85, 0.15);
  box-shadow: 
    0 25px 50px rgba(0, 0, 0, 0.5),
    0 0 100px rgba(139, 115, 85, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
  padding: 56px 48px;
  text-align: center;
  animation: fadeInUp 0.6s ease;
}

.welcome-header {
  margin-bottom: 48px;
}

.avatar-container {
  position: relative;
  width: 96px;
  height: 96px;
  margin: 0 auto 24px;
}

.avatar {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #8B7355 0%, #A68B67 50%, #8B7355 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
  box-shadow: 0 8px 32px rgba(139, 115, 85, 0.4);
}

.avatar-icon {
  font-size: 40px;
}

.avatar-glow {
  position: absolute;
  inset: -8px;
  background: linear-gradient(135deg, #8B7355 0%, transparent 70%);
  border-radius: 50%;
  opacity: 0.4;
  animation: pulseGlow 2s ease-in-out infinite;
}

@keyframes pulseGlow {
  0%, 100% { transform: scale(1); opacity: 0.4; }
  50% { transform: scale(1.1); opacity: 0.6; }
}

.welcome-title {
  font-size: 32px;
  font-weight: 700;
  color: #ffffff;
  margin: 0 0 12px;
  letter-spacing: -0.5px;
}

.welcome-subtitle {
  font-size: 15px;
  color: rgba(255, 255, 255, 0.6);
  margin: 0;
}

.feature-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.feature-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  padding: 24px;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: transparent;
    transition: background 0.3s ease;
  }

  &:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(139, 115, 85, 0.3);
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);

    &::before {
      background: linear-gradient(90deg, transparent, rgba(139, 115, 85, 0.8), transparent);
    }
  }

  &.disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none !important;
  }
}

.feature-icon {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  margin-bottom: 16px;
}

.single-icon {
  background: linear-gradient(135deg, rgba(139, 115, 85, 0.2) 0%, rgba(139, 115, 85, 0.1) 100%);
}

.batch-icon {
  background: linear-gradient(135deg, rgba(107, 142, 35, 0.2) 0%, rgba(107, 142, 35, 0.1) 100%);
}

.video-icon {
  background: linear-gradient(135deg, rgba(218, 165, 32, 0.2) 0%, rgba(218, 165, 32, 0.1) 100%);
}

.camera-icon {
  background: linear-gradient(135deg, rgba(205, 92, 92, 0.2) 0%, rgba(205, 92, 92, 0.1) 100%);
}

.feature-title {
  font-size: 16px;
  font-weight: 600;
  color: #ffffff;
  margin: 0 0 8px;
}

.feature-desc {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
}

.welcome-tips {
  padding: 16px 24px;
  background: rgba(139, 115, 85, 0.08);
  border-radius: 12px;
  border: 1px solid rgba(139, 115, 85, 0.15);

  p {
    margin: 0;
    font-size: 14px;
    color: rgba(255, 255, 255, 0.7);
  }
}

.message-container {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
  position: relative;
  z-index: 1;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.2);
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 3px;
    &:hover {
      background: rgba(255, 255, 255, 0.3);
    }
  }
}

.message-list {
  max-width: 900px;
  margin: 0 auto;
  padding: 0 20px 200px;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.message-item {
  display: flex;
  margin-bottom: 24px;
  animation: slideIn 0.3s ease;

  &.message-user {
    justify-content: flex-end;
  }
  &.message-assistant {
    justify-content: flex-start;
  }
}

.message-item:first-child {
  margin-top: auto;
}

.message-bubble {
  max-width: 80%;
  padding: 16px 24px;
  line-height: 1.6;
  font-size: 16px;
  word-break: break-word;
  position: relative;
}

.user-bubble {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(37, 99, 235, 0.9) 100%);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: white;
  border-radius: 20px 20px 6px 20px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 
    0 4px 15px rgba(59, 130, 246, 0.3),
    0 1px 3px rgba(0, 0, 0, 0.2);
}

.assistant-bubble {
  background: linear-gradient(135deg, rgba(30, 30, 30, 0.98) 0%, rgba(20, 20, 20, 0.98) 100%);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  color: #ffffff;
  border-radius: 20px 20px 20px 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 
    0 8px 30px rgba(0, 0, 0, 0.5),
    0 2px 8px rgba(0, 0, 0, 0.3);
}

.message-content {
  white-space: pre-wrap;
}

.result-wrapper {
  margin-top: 12px;
}

.bottom-input-wrapper {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(to top, rgba(26, 22, 18, 0.98) 0%, rgba(26, 22, 18, 0.9) 70%, transparent 100%);
  padding: 0 20px 36px;
  z-index: 30;
}

.input-card {
  max-width: 900px;
  margin: 0 auto;
  background: rgba(30, 26, 22, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 24px;
  box-shadow: 
    0 -4px 30px rgba(0, 0, 0, 0.5),
    0 4px 20px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
  border: none;
  overflow: hidden;
}

.tool-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px 8px;
  flex-wrap: wrap;
}

.tool-buttons {
  display: flex;
  gap: 8px;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 20px 16px;
}

.tool-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s ease;

  .tool-icon {
    font-size: 14px;
  }

  .tool-text {
    font-size: 12px;
  }

  &:hover:not(:disabled) {
    background: rgba(139, 115, 85, 0.15);
    border-color: rgba(139, 115, 85, 0.3);
    color: #ffffff;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &.camera-tool-btn {
    background: rgba(205, 92, 92, 0.1);
    border-color: rgba(205, 92, 92, 0.2);
    color: #CD5C5C;

    &:hover:not(:disabled) {
      background: rgba(205, 92, 92, 0.15);
      border-color: rgba(205, 92, 92, 0.4);
    }
  }
}

.divider {
  width: 1px;
  height: 28px;
  background: rgba(255, 255, 255, 0.1);
  margin: 0 4px;
}

.input-row :deep(.el-input__wrapper) {
  box-shadow: none !important;
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 24px;
  padding: 6px 20px;
  transition: all 0.3s ease;
  
  &:hover {
    border-color: rgba(139, 115, 85, 0.4);
    background: rgba(255, 255, 255, 0.08) !important;
  }
  
  &.is-focus {
    border-color: #8B7355;
    box-shadow: 0 0 0 3px rgba(139, 115, 85, 0.15);
  }
}

.input-row :deep(.el-input__inner) {
  color: #ffffff;
  font-size: 15px;
  height: 40px;
  background: transparent !important;
}

.input-row :deep(.el-input__inner::placeholder) {
  color: rgba(255, 255, 255, 0.5);
}

.attach-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #a3a8b0;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.25s ease;

  &:hover:not(:disabled) {
    color: #8B7355;
    background: rgba(139, 115, 85, 0.15);
    border-color: rgba(139, 115, 85, 0.3);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.send-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, #8B7355 0%, #A68B67 100%);
  border: none;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 15px rgba(139, 115, 85, 0.4);
  transition: all 0.25s ease;

  &:hover:not(:disabled) {
    background: linear-gradient(135deg, #A68B67 0%, #C4A87A 100%);
    box-shadow: 0 6px 20px rgba(139, 115, 85, 0.5);
    transform: translateY(-2px);
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
  }

  .send-icon {
    font-size: 18px;
    font-weight: 600;
    margin-left: 2px;
  }
}

.stop-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, #CD5C5C 0%, #B04040 100%);
  border: none;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 15px rgba(205, 92, 92, 0.4);
  transition: all 0.25s ease;

  &:hover {
    background: linear-gradient(135deg, #B04040 0%, #CD5C5C 100%);
    box-shadow: 0 6px 20px rgba(205, 92, 92, 0.5);
    transform: translateY(-2px);
  }

  .stop-icon {
    font-size: 16px;
  }
}

.message-attachment img {
  max-width: 240px;
  border-radius: 10px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  margin-top: 10px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.message-attachments-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
  margin-top: 12px;
  img {
    width: 100%;
    height: 80px;
    object-fit: cover;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }
}

@keyframes slideIn {
  from { 
    opacity: 0; 
    transform: translateY(20px) scale(0.98); 
  }
  to { 
    opacity: 1; 
    transform: translateY(0) scale(1); 
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.typing-indicator {
  display: flex;
  gap: 5px;
  padding: 8px 0;
  span {
    width: 7px;
    height: 7px;
    background: rgba(255, 255, 255, 0.6);
    border-radius: 50%;
    animation: typing 1.4s infinite ease-in-out;
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.3);
  }
  span:nth-child(2) { animation-delay: 0.2s; }
  span:nth-child(3) { animation-delay: 0.4s; }
}

@keyframes typing {
  0%, 60%, 100% { 
    transform: translateY(0); 
    opacity: 0.6;
  }
  30% { 
    transform: translateY(-6px); 
    opacity: 1;
  }
}

:deep(.markdown-body) {
  background: transparent !important;
  color: #d1d5db !important; 
  
  h1, h2, h3, strong { color: #ffffff !important; margin: 12px 0; }
  
  code { 
    background: rgba(139, 115, 85, 0.15) !important; 
    color: #C4A87A !important; 
    padding: 2px 6px; 
    border-radius: 4px; 
    font-size: 0.9em;
  }
  
  pre { 
    background: rgba(0, 0, 0, 0.6) !important; 
    border: 1px solid rgba(139, 115, 85, 0.15);
    color: #abb2bf; 
    padding: 16px; 
    border-radius: 10px; 
    overflow-x: auto; 
    margin: 12px 0;
  }
  
  table th, table td { 
    border: 1px solid rgba(255, 255, 255, 0.1) !important; 
    background: transparent !important;
    padding: 8px 12px;
  }
  table th { 
    background: rgba(255, 255, 255, 0.08) !important; 
    color: #ffffff;
  }
  
  ul, ol {
    padding-left: 20px;
    margin: 8px 0;
  }
  
  li {
    margin: 4px 0;
  }
}

:deep(.dark-stream-dialog) {
  background: rgba(26, 22, 18, 0.98) !important;
  border: 1px solid rgba(139, 115, 85, 0.2);
  border-radius: 20px;
  overflow: hidden;
  backdrop-filter: blur(20px);
  
  .el-dialog__title { 
    color: #fff; 
    font-weight: 600; 
    font-size: 18px;
  }
  .el-dialog__header { 
    border-bottom: 1px solid rgba(139, 115, 85, 0.15); 
    margin: 0; 
    padding: 20px 24px;
    background: rgba(139, 115, 85, 0.03);
  }
  .el-dialog__body { 
    padding: 0; 
  }
  .el-dialog__footer {
    border-top: 1px solid rgba(139, 115, 85, 0.15);
    padding: 16px 24px;
    background: rgba(0, 0, 0, 0.3);
  }
}

.stream-container {
  width: 100%;
  height: 480px;
  background: #000;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  overflow: hidden;
  border-radius: 0 0 16px 16px;
}

.live-feed {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.loading-feed {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #666;
  font-size: 14px;
}

.loading-spinner {
  width: 48px; 
  height: 48px;
  border: 3px solid rgba(255, 255, 255, 0.1);
  border-top-color: #8B7355;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
  box-shadow: 0 0 20px rgba(139, 115, 85, 0.3);
}

@keyframes spin { 
  to { transform: rotate(360deg); } 
}

.stream-stats {
  display: flex;
  justify-content: space-around;
  padding: 20px 24px;
  background: rgba(0, 0, 0, 0.4);
  border-top: 1px solid rgba(139, 115, 85, 0.1);
}

.stat-item {
  text-align: center;
}

.stat-label {
  font-size: 11px;
  color: #888;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  font-family: 'SF Mono', 'Consolas', monospace;
}

.text-green { color: #6B8E23; }
.text-blue { color: #8B7355; }
.text-orange { color: #DAA520; }

:deep(.el-button--plain) {
  border-color: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  transition: all 0.2s ease;
  
  &:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.3);
    color: #fff;
  }
}

:deep(.el-button--danger) {
  background: linear-gradient(135deg, #CD5C5C 0%, #B04040 100%);
  border: none;
  border-radius: 22px;
  box-shadow: 0 4px 15px rgba(205, 92, 92, 0.4);
  
  &:hover {
    background: linear-gradient(135deg, #B04040 0%, #CD5C5C 100%);
    box-shadow: 0 6px 20px rgba(205, 92, 92, 0.5);
  }
}

:deep(.el-button--danger.is-plain) {
  background: rgba(205, 92, 92, 0.15);
  border-color: rgba(245, 108, 108, 0.4);
  color: #f56c6c;
  
  &:hover {
    background: rgba(245, 108, 108, 0.25);
    border-color: #f56c6c;
    color: #fff;
  }
}

:deep(.el-tag) {
  border-radius: 6px;
}

.video-attachment {
  margin-top: 10px;
  
  video {
    max-width: 280px;
    max-height: 200px;
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: #000;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }
}

.tool-calls {
  margin: 12px 0;
  padding: 12px 16px;
  background: rgba(139, 115, 85, 0.08);
  border-radius: 12px;
  border: 1px solid rgba(139, 115, 85, 0.15);
}

.tool-call-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);

  &.is-loading {
    color: #8B7355;
  }

  .tool-name {
    font-weight: 500;
  }

  .tool-summary {
    color: rgba(255, 255, 255, 0.4);
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 300px;
  }
}
</style>
