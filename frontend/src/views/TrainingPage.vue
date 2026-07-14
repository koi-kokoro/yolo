<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { getSemanticModelInfo } from '@/api/semantic'
import {
  evaluateSemanticModel,
  exportSemanticModel,
  listSemanticModelVersions,
  downloadSemanticModel,
  predictSemanticImage,
} from '@/api/modelOps'
import { downloadTrainingArtifact } from '@/api/training'
import TrainingMetricsChart from '@/components/training/TrainingMetricsChart.vue'
import { useTrainingStore } from '@/stores/training'
import { formatInputSize, resolveRuntimeModelIdentity } from '@/utils/semanticModelIdentity'

const loading = ref(true)
const loadError = ref('')
const report = ref(null)
const runtime = ref(null)
const evalWarning = ref('')
const validating = ref(false)
const showExportDialog = ref(false)
const exporting = ref(false)
const exportForm = ref({
  version: '',
  description: '',
  set_default: true,
  upload_minio: true,
})
const modelVersions = ref([])
const selectedVersionId = ref(null)
const trainingStore = useTrainingStore()
const { tasks, selectedTask, metrics, listLoading, detailLoading, creating, stopping, error, pollError } = storeToRefs(trainingStore)
const onlineAvailable = ref(true)
const createForm = reactive({
  dataset_key: 'full',
  model: 'yolo26n-sem.pt',
  experiment: 'S0',
  device: '0',
  epochs: 50,
  batch_size: 4,
  img_size: 512,
  patience: 15,
  mosaic: 1,
})

const showPredictDialog = ref(false)
const predicting = ref(false)
const predictFile = ref(null)
const predictResult = ref(null)

const parameters = computed(() => report.value || {})
const actualModel = computed(() => resolveRuntimeModelIdentity({ runtimeInfo: runtime.value }))
const runtimeInputTensor = computed(() => {
  const size = formatInputSize(actualModel.value.inputSize)
  return size === '—' ? '—' : `N × 3 × ${size}`
})
const trainingStatus = computed(() => {
  const status = report.value?.status
  if (status === 'early_stopped') return { label: '早停完成', type: 'success' }
  if (status === 'completed') return { label: '训练完成', type: 'success' }
  return { label: status || '未知', type: 'info' }
})

const dbDefaultModel = computed(() => modelVersions.value.find((item) => item.is_default) || null)
const modelIdentityConsistent = computed(() => {
  if (!dbDefaultModel.value || actualModel.value.modelVersion === '—') return null
  const runtimeVersion = String(actualModel.value.modelVersion).trim().toLowerCase()
  const dbVersion = String(dbDefaultModel.value.version || '').trim().toLowerCase()
  const runtimeSha = String(actualModel.value.modelSha256 || '').trim().toLowerCase()
  const dbSha = String(dbDefaultModel.value.artifact_sha256 || '').trim().toLowerCase()
  if (runtimeSha && dbSha) return runtimeVersion === dbVersion && runtimeSha === dbSha
  return runtimeVersion === dbVersion
})

const runtimeStatus = computed(() =>
  runtime.value?.ready
    ? { label: '已部署可用', type: 'success' }
    : { label: '推理服务未就绪', type: 'danger' },
)

const percent = (value, digits = 3) =>
  value == null ? '暂无数据' : `${(Number(value) * 100).toFixed(digits)}%`
const evaluation = computed(() => report.value?.independent_evaluation || {})
const evaluationMetrics = ref(null)
const curveMetrics = computed(() => report.value?.curve?.metrics || [])
const chartPoints = (key) => {
  const metrics = curveMetrics.value
  if (!metrics.length) return ''
  const width = 720
  const minY = 0.35
  const maxY = 0.72
  return metrics
    .map((item, index) => {
      const x = 40 + (index / Math.max(metrics.length - 1, 1)) * width
      const y = 240 - ((Number(item[key]) - minY) / (maxY - minY)) * 210
      return `${x.toFixed(1)},${Math.max(20, Math.min(240, y)).toFixed(1)}`
    })
    .join(' ')
}
const duration = computed(() => {
  const seconds = Number(report.value?.elapsed_seconds || 0)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${hours} 小时 ${minutes} 分钟`
})

const statusLabel = (status) => ({
  pending: '等待中', starting: '启动中', running: '训练中', stopping: '停止中', completed: '已完成',
  early_stopped: '早停完成', cancelled: '已取消', failed: '失败', interrupted: '已中断',
}[status] || status || '未知')
const artifactNames = computed(() => {
  const manifest = selectedTask.value?.artifact_manifest
  if (Array.isArray(manifest)) return manifest
  if (manifest && typeof manifest === 'object') return Object.keys(manifest)
  return []
})

async function loadOnlineTraining() {
  onlineAvailable.value = true
  try {
    await trainingStore.fetchTasks()
    if (!selectedTask.value && tasks.value.length) await trainingStore.selectTask(tasks.value[0])
  } catch (e) {
    onlineAvailable.value = ![404, 503].includes(e?.response?.status)
  }
}

async function submitTraining() {
  try {
    await trainingStore.createTask({ ...createForm })
    onlineAvailable.value = true
    ElMessage.success('在线训练任务已创建；训练产物不会自动部署')
  } catch (e) {
    if ([404, 503].includes(e?.response?.status)) onlineAvailable.value = false
  }
}

async function confirmStopTraining() {
  try {
    await ElMessageBox.confirm('停止后任务可能无法恢复，确认停止当前训练任务？', '停止在线训练', {
      type: 'warning', confirmButtonText: '确认停止', cancelButtonText: '取消',
    })
    await trainingStore.stopSelected()
    ElMessage.success('停止请求已提交')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close' && e?.response) return
  }
}

async function downloadArtifact(name) {
  try {
    const blob = await downloadTrainingArtifact(selectedTask.value.id, name)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = name
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    // Auth and API errors follow the shared request interceptor.
  }
}

async function loadDashboard() {
  loading.value = true
  loadError.value = ''
  try {
    const [reportResponse, evaluationResponse, runtimeResponse, versionsResponse] = await Promise.all([
      fetch('/model-dashboard/v2_training_summary.json'),
      fetch('/model-dashboard/v2_evaluation_metrics.json'),
      getSemanticModelInfo().catch(() => null),
      listSemanticModelVersions().catch(() => ({ items: [] })),
    ])
    if (!reportResponse.ok) throw new Error('V2 训练摘要读取失败')
    if (!evaluationResponse.ok) throw new Error('V2 独立评估结果读取失败')
    report.value = await reportResponse.json()
    evaluationMetrics.value = await evaluationResponse.json()
    runtime.value = runtimeResponse
    modelVersions.value = versionsResponse.items || []
    if (modelVersions.value.length > 0) {
      const defaultVersion = modelVersions.value.find((v) => v.is_default)
      selectedVersionId.value = defaultVersion?.id || modelVersions.value[0].id
    }
  } catch (error) {
    loadError.value = error?.message || '模型看板加载失败'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function evaluateModel() {
  validating.value = true
  try {
    const res = await evaluateSemanticModel({ device: 'cpu', force: false })
    evalWarning.value = res.warning || ''
    const miou = res.report?.overall?.miou ?? res.report?.miou
    ElMessage.success(`评估完成${res.source === 'cached' ? '（缓存）' : ''}: mIoU=${percent(miou)}`)
  } catch (e) {
    // Response interceptor already shows error message.
  } finally {
    validating.value = false
  }
}

async function exportModel() {
  exporting.value = true
  try {
    const res = await exportSemanticModel(exportForm.value)
    ElMessage.success(res.message || '模型导出成功')
    showExportDialog.value = false
    await loadDashboard()
  } catch (e) {
    // Error already displayed by interceptor.
  } finally {
    exporting.value = false
  }
}

async function downloadModel() {
  if (!selectedVersionId.value) {
    ElMessage.warning('没有可下载的模型版本')
    return
  }
  try {
    const token = localStorage.getItem('rsod_token') || ''
    const response = await fetch(downloadSemanticModel(selectedVersionId.value), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error('下载失败')
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const version = modelVersions.value.find((v) => v.id === selectedVersionId.value)
    a.download = `${version?.model_name || 'semantic_model'}.pt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    ElMessage.success('模型下载已开始')
  } catch (e) {
    ElMessage.error('模型下载失败')
  }
}

function handlePredictFileChange(file) {
  predictFile.value = file.raw
  predictResult.value = null
}

async function runPredict() {
  if (!predictFile.value) {
    ElMessage.warning('请先上传测试图片')
    return
  }
  predicting.value = true
  try {
    const formData = new FormData()
    formData.append('file', predictFile.value)
    formData.append('use_pt_fallback', 'true')
    const res = await predictSemanticImage(formData)
    predictResult.value = res
    ElMessage.success('语义分割推理完成')
  } catch (e) {
    // Error already displayed by interceptor.
  } finally {
    predicting.value = false
  }
}

onMounted(() => {
  loadDashboard()
  trainingStore.initVisibilityHandling()
  loadOnlineTraining()
})
onBeforeUnmount(() => trainingStore.dispose())
</script>

<template>
  <section v-loading="loading" class="training-dashboard">
    <header class="dashboard-header">
      <div>
        <div class="eyebrow">MODEL MANAGEMENT</div>
        <h1>模型管理看板</h1>
        <p>
          展示当前 V2 语义模型的部署身份、真实训练期摘要与运行状态。支持模型评估、导出、下载与单图测试验证。
        </p>
      </div>
      <el-button :loading="loading" @click="loadDashboard">刷新状态</el-button>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false" />
    <el-alert
      v-if="evalWarning"
      :title="evalWarning"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    />

    <!-- Model action bar -->
    <div class="action-bar">
      <el-space wrap>
        <el-button type="primary" :loading="validating" @click="evaluateModel">
          评估模型
        </el-button>
        <el-button type="success" @click="showExportDialog = true">导出模型</el-button>
        <el-select
          v-model="selectedVersionId"
          placeholder="选择版本"
          style="width: 220px"
          :empty-text="'暂无版本'"
        >
          <el-option
            v-for="v in modelVersions"
            :key="v.id"
            :label="`${v.version}${v.is_default ? '（默认）' : ''}`"
            :value="v.id"
          />
        </el-select>
        <el-button :disabled="!selectedVersionId" @click="downloadModel">
          下载权重
        </el-button>
        <el-button type="warning" @click="showPredictDialog = true">
          测试验证
        </el-button>
      </el-space>
    </div>

    <section class="dashboard-section">
      <div class="section-heading">
        <div><span>DEPLOYED MODEL</span><h2>当前部署模型 / 既有 V2 独立评估</h2></div>
        <p>实际推理身份始终来自 runtime / inference metadata；数据库默认版本仅用于一致性核验。</p>
      </div>
      <el-alert
        v-if="modelIdentityConsistent === false"
        title="模型登记信息未同步"
        :description="`实际推理模型为 ${actualModel.modelName} / ${actualModel.modelVersion}，数据库默认记录为 ${dbDefaultModel?.model_name} / ${dbDefaultModel?.version}。登记信息未同步，不影响当前 V2 推理；实际部署身份仍以 runtime / inference metadata 为准。`"
        type="warning" show-icon :closable="false" style="margin-bottom: 16px"
      />
      <el-alert
        v-else-if="modelIdentityConsistent === true"
        title="运行时部署 metadata 与数据库默认模型记录一致"
        type="success" show-icon :closable="false" style="margin-bottom: 16px"
      />
    <template v-if="report">
      <el-alert
        title="V2 数据口径说明"
        description="独立指标来自 V2 部署 ONNX 在 LoveDA Val Urban + Rural 完整 1669 张上的像素级评估（imgsz 1024、ignore 255）；训练期最佳 51.476% 单独保留，二者不混用。"
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom: 16px"
      />
      <div class="status-strip">
        <div class="model-identity">
          <div class="model-icon">S</div>
          <div>
            <strong>{{ actualModel.modelName }}</strong>
            <span>实际推理模型 · {{ actualModel.modelVersion }}</span>
          </div>
        </div>
        <div class="status-items">
          <div><span>训练状态</span><el-tag :type="trainingStatus.type" effect="dark">{{ trainingStatus.label }}</el-tag></div>
          <div><span>部署状态</span><el-tag :type="runtimeStatus.type" effect="dark">{{ runtimeStatus.label }}</el-tag></div>
          <div><span>推理引擎</span><strong>{{ runtime?.engine || 'ONNX Runtime' }}</strong></div>
          <div><span>Provider</span><strong>{{ runtime?.provider || 'CPUExecutionProvider' }}</strong></div>
        </div>
      </div>

      <div class="metric-grid">
        <article class="metric-card primary">
          <span>独立完整评估 mIoU</span><strong>{{ percent(evaluation.overall_miou) }}</strong>
          <small>完整验证集 · {{ evaluation.images }} 张 · imgsz {{ evaluation.imgsz }}</small>
        </article>
        <article class="metric-card">
          <span>独立 Pixel Accuracy</span><strong>{{ percent(evaluation.pixel_accuracy) }}</strong>
          <small>{{ evaluation.provider }}</small>
        </article>
        <article class="metric-card">
          <span>独立 Mean Dice / F1</span><strong>{{ percent(evaluation.mean_dice_f1) }}</strong>
          <small>{{ Number(evaluation.valid_pixels || 0).toLocaleString() }} 有效像素</small>
        </article>
        <article class="metric-card">
          <span>Urban mIoU</span><strong>{{ percent(evaluation.urban_miou) }}</strong>
          <small>LoveDA Val Urban · 677 张</small>
        </article>
        <article class="metric-card">
          <span>Rural mIoU</span><strong>{{ percent(evaluation.rural_miou) }}</strong>
          <small>LoveDA Val Rural · 992 张</small>
        </article>
        <article class="metric-card warning">
          <span>训练期最佳验证 mIoU</span><strong>{{ percent(report.best_miou) }}</strong>
          <small>训练指标 · best epoch {{ report.best_epoch }}</small>
        </article>
      </div>

      <div class="content-grid">
        <article class="panel chart-panel">
          <div class="panel-title">
            <div>
              <h2>训练趋势</h2>
              <p>完整 {{ report.curve?.epochs_recorded }} epoch · 严格来源于 V2 results.csv</p>
            </div>
            <div class="legend"><span class="miou">mIoU</span><span class="accuracy">Pixel Accuracy</span></div>
          </div>
          <div v-if="report.curve?.available" class="line-chart" aria-label="V2 完整训练曲线">
            <svg viewBox="0 0 800 270" role="img">
              <g class="grid-lines">
                <line v-for="tick in [40, 90, 140, 190, 240]" :key="tick" x1="40" :y1="tick" x2="760" :y2="tick" />
                <text x="4" y="244">35%</text><text x="4" y="194">44%</text>
                <text x="4" y="144">54%</text><text x="4" y="94">63%</text><text x="4" y="44">72%</text>
              </g>
              <polyline class="curve-line miou-line" :points="chartPoints('miou')" />
              <polyline class="curve-line accuracy-line" :points="chartPoints('pixel_accuracy')" />
            </svg>
            <div class="x-axis"><span>Epoch 1</span><span>Epoch {{ report.curve.epochs_recorded }}</span></div>
          </div>
          <el-empty v-else description="V2 曲线暂无可信完整数据" />
        </article>

        <article class="panel parameters-panel">
          <div class="panel-title">
            <div>
              <h2>V2 训练参数</h2>
              <p>来源：V2 experiment_report.json</p>
            </div>
          </div>
          <dl class="parameter-list">
            <div><dt>基础权重</dt><dd>{{ parameters.model_display_name }}</dd></div>
            <div><dt>数据集</dt><dd>{{ parameters.dataset }}</dd></div>
            <div><dt>输入尺寸</dt><dd>{{ parameters.imgsz }} × {{ parameters.imgsz }}</dd></div>
            <div><dt>Batch Size</dt><dd>{{ parameters.batch }}</dd></div>
            <div><dt>计划 Epoch</dt><dd>{{ parameters.epochs_configured }}</dd></div>
            <div><dt>Early Stopping</dt><dd>Patience {{ parameters.patience }}</dd></div>
            <div><dt>混合精度</dt><dd>{{ parameters.amp ? 'AMP 开启' : '关闭' }}</dd></div>
            <div><dt>随机种子</dt><dd>{{ parameters.seed }}</dd></div>
            <div><dt>训练设备</dt><dd>{{ parameters.gpu }}</dd></div>
            <div><dt>训练耗时</dt><dd>{{ duration }}</dd></div>
          </dl>
        </article>
      </div>

      <div class="content-grid bottom-grid">
        <article class="panel matrix-panel">
          <div class="panel-title">
            <div>
              <h2>V2 独立完整评估</h2>
              <p>LoveDA Val · Urban + Rural · 1669 张 · imgsz 1024 · ignore 255</p>
            </div>
          </div>
          <img src="/model-dashboard/v2_confusion_matrix_normalized.png" alt="V2 完整验证集归一化混淆矩阵" />
          <div class="class-table-wrap">
            <table class="class-table">
              <thead><tr><th>类别</th><th>IoU</th><th>Dice / F1</th><th>Precision</th><th>Recall</th></tr></thead>
              <tbody>
                <tr v-for="item in evaluationMetrics?.overall?.per_class || []" :key="item.class_id">
                  <td><strong>{{ item.class_name }}</strong></td>
                  <td>{{ percent(item.iou) }}</td><td>{{ percent(item.dice_f1) }}</td>
                  <td>{{ percent(item.precision) }}</td><td>{{ percent(item.recall) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel deployment-panel">
          <div class="panel-title">
            <div>
              <h2>实际推理模型</h2>
              <p>优先采用当前推理运行时返回的部署 metadata</p>
            </div>
          </div>
          <div class="deployment-state" :class="{ ready: runtime?.ready }">
            <span></span>
            <div>
              <strong>{{ runtimeStatus.label }}</strong
              ><small>{{ runtime?.message || '推理运行时已加载模型并可接受任务' }}</small>
            </div>
          </div>
          <dl class="parameter-list compact">
            <div><dt>模型版本</dt><dd>{{ actualModel.modelVersion }}</dd></div>
            <div><dt>模型名称</dt><dd>{{ actualModel.modelName }}</dd></div>
            <div><dt>模型格式</dt><dd>Dynamic ONNX</dd></div>
            <div><dt>输入张量</dt><dd>{{ runtimeInputTensor }}</dd></div>
            <div><dt>公开类别</dt><dd>7 类</dd></div>
            <div><dt>ONNX/PT 一致率</dt><dd>100%</dd></div>
          </dl>
          <el-alert
            title="此看板不启动训练"
            description="模型训练在隔离训练环境中离线执行。验证通过后导出并登记模型版本，生产页面只负责审阅和部署状态监控。"
            type="info"
            :closable="false"
            show-icon
          />
        </article>
      </div>
    </template>
    </section>

    <section class="dashboard-section online-section">
      <div class="section-heading">
        <div><span>ONLINE TRAINING</span><h2>LoveDA 在线训练任务</h2></div>
        <el-button :loading="listLoading" @click="loadOnlineTraining">刷新任务</el-button>
      </div>
      <el-alert title="训练与部署相互独立" description="在线训练生成候选产物，不会自动替换或部署当前实际推理模型。" type="info" show-icon :closable="false" />
      <el-alert v-if="!onlineAvailable" title="在线训练当前不可用" description="后端未提供该功能、功能未启用或训练 worker/场景尚未就绪。既有 V2 看板仍可正常使用。" type="warning" show-icon :closable="false" />
      <el-alert v-else-if="error || pollError" :title="error || pollError" type="error" show-icon :closable="false" />

      <div class="online-grid">
        <article class="panel create-panel">
          <div class="panel-title"><div><h2>创建任务</h2><p>字段及约束与后端 TrainingTaskCreate schema 一致</p></div></div>
          <el-form :model="createForm" label-position="top" :disabled="!onlineAvailable || creating">
            <el-row :gutter="12">
              <el-col :span="12"><el-form-item label="数据集"><el-select v-model="createForm.dataset_key"><el-option label="完整集 full" value="full"/><el-option label="冒烟集 smoke" value="smoke"/></el-select></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="基础模型"><el-input v-model="createForm.model" maxlength="100" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="实验预设"><el-select v-model="createForm.experiment"><el-option v-for="v in ['S0','S1','S2','M0','custom']" :key="v" :label="v" :value="v"/></el-select></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="设备"><el-input v-model="createForm.device" maxlength="20" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="Epoch"><el-input-number v-model="createForm.epochs" :min="1" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="Batch Size"><el-input-number v-model="createForm.batch_size" :min="1" :max="4" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="Image Size"><el-input-number v-model="createForm.img_size" :min="128" :max="2048" :step="32" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="Patience"><el-input-number v-model="createForm.patience" :min="1" :max="100" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="Mosaic"><el-input-number v-model="createForm.mosaic" :min="0" :max="1" :step="0.1" /></el-form-item></el-col>
            </el-row>
            <el-button type="primary" :loading="creating" :disabled="!onlineAvailable" @click="submitTraining">创建并监控</el-button>
          </el-form>
        </article>

        <article class="panel task-list-panel">
          <div class="panel-title"><div><h2>我的任务</h2><p>最多显示后端返回的最近任务</p></div></div>
          <el-table v-loading="listLoading" :data="tasks" height="360" highlight-current-row @current-change="(row) => row && trainingStore.selectTask(row)">
            <el-table-column prop="id" label="ID" width="60"/><el-table-column prop="run_name" label="任务" min-width="155" show-overflow-tooltip/>
            <el-table-column label="状态" width="90"><template #default="{ row }">{{ statusLabel(row.status) }}</template></el-table-column>
            <el-table-column label="进度" width="75"><template #default="{ row }">{{ row.progress }}%</template></el-table-column>
          </el-table>
        </article>
      </div>

      <article v-if="selectedTask" v-loading="detailLoading" class="panel task-detail">
        <div class="panel-title"><div><h2>任务 #{{ selectedTask.id }} · {{ statusLabel(selectedTask.status) }}</h2><p>{{ selectedTask.run_name }} · 候选训练产物（非当前部署模型）</p></div>
          <el-button type="danger" :disabled="!trainingStore.selectedTaskActive" :loading="stopping" @click="confirmStopTraining">停止训练</el-button>
        </div>
        <el-progress :percentage="selectedTask.progress || 0" :status="selectedTask.status === 'failed' ? 'exception' : undefined" />
        <div class="online-metrics">
          <div><span>Epoch</span><strong>{{ selectedTask.current_epoch }} / {{ selectedTask.epochs }}</strong></div>
          <div><span>最佳 mIoU</span><strong>{{ percent(selectedTask.best_miou) }}</strong><small>Epoch {{ selectedTask.best_epoch ?? '—' }}</small></div>
          <div><span>最新 mIoU</span><strong>{{ percent(selectedTask.latest_miou) }}</strong></div>
          <div><span>最新 Pixel Accuracy</span><strong>{{ percent(selectedTask.latest_pixel_accuracy) }}</strong></div>
        </div>
        <el-alert v-if="selectedTask.error_message" :title="selectedTask.error_message" type="error" show-icon :closable="false" />
        <TrainingMetricsChart :metrics="metrics" />
        <div v-if="artifactNames.length" class="artifacts"><strong>安全产物下载：</strong><el-button v-for="name in artifactNames" :key="name" size="small" @click="downloadArtifact(name)">{{ name }}</el-button></div>
      </article>
      <el-empty v-else description="暂无选中的在线训练任务" />
    </section>

    <!-- Export dialog -->
    <el-dialog v-model="showExportDialog" title="导出模型" width="500px">
      <el-form :model="exportForm" label-width="100px">
        <el-form-item label="版本号">
          <el-input v-model="exportForm.version" placeholder="自动生成（如 v1.0.0）" />
        </el-form-item>
        <el-form-item label="版本描述">
          <el-input
            v-model="exportForm.description"
            type="textarea"
            :rows="3"
            placeholder="描述本次导出的主要变更..."
          />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="exportForm.set_default" />
          <span style="margin-left: 8px; color: #909399; font-size: 12px">设为该场景的默认检测模型</span>
        </el-form-item>
        <el-form-item label="上传 MinIO">
          <el-switch v-model="exportForm.upload_minio" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showExportDialog = false">取消</el-button>
        <el-button type="primary" :loading="exporting" @click="exportModel">确认导出</el-button>
      </template>
    </el-dialog>

    <!-- Test prediction dialog -->
    <el-dialog v-model="showPredictDialog" title="测试图验证" width="900px">
      <el-row :gutter="16">
        <el-col :span="10">
          <el-upload
            class="predict-upload"
            drag
            action=""
            :auto-upload="false"
            :on-change="handlePredictFileChange"
            accept="image/*"
            :limit="1"
          >
            <el-icon style="font-size: 40px; color: #909399"><UploadFilled /></el-icon>
            <div>拖拽图片到此处，或 <em>点击上传</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 JPG/PNG 格式</div>
            </template>
          </el-upload>
          <el-button
            type="primary"
            style="width: 100%; margin-top: 16px"
            :loading="predicting"
            :disabled="!predictFile"
            @click="runPredict"
          >
            开始分割
          </el-button>
        </el-col>
        <el-col :span="14">
          <div v-if="predictResult">
            <img
              :src="`data:image/png;base64,${predictResult.annotated_image}`"
              style="width: 100%; border-radius: 8px; margin-bottom: 12px"
            />
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="推理耗时">{{ predictResult.inference_time_ms }}ms</el-descriptions-item>
              <el-descriptions-item label="模型">{{ predictResult.model }}</el-descriptions-item>
            </el-descriptions>
            <el-table :data="predictResult.class_statistics" stripe size="small" style="margin-top: 8px">
              <el-table-column prop="display_name" label="类别" width="120" />
              <el-table-column label="占比" width="100">
                <template #default="{ row }">{{ (row.ratio * 100).toFixed(1) }}%</template>
              </el-table-column>
              <el-table-column prop="pixel_count" label="像素数" />
            </el-table>
          </div>
          <el-empty v-else description="上传图片并点击分割" />
        </el-col>
      </el-row>
    </el-dialog>
  </section>
</template>

<style scoped lang="scss">
.training-dashboard {
  min-height: 100%;
  color: #1f2937;
}
.dashboard-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 22px;
  h1 {
    margin: 4px 0 8px;
    font-size: 28px;
    color: #172033;
  }
  p {
    margin: 0;
    color: #6b7280;
    line-height: 1.7;
  }
}
.dashboard-section { margin-bottom: 28px; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin: 18px 0 14px; }
.section-heading span { color: #409eff; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }
.section-heading h2 { margin: 4px 0 0; font-size: 21px; }
.section-heading p { color: #8492a6; margin: 0; font-size: 13px; }
.online-section > .el-alert { margin-bottom: 14px; }
.online-grid { display: grid; grid-template-columns: minmax(480px, 1.2fr) minmax(380px, 1fr); gap: 18px; margin-bottom: 18px; }
.create-panel :deep(.el-select), .create-panel :deep(.el-input-number) { width: 100%; }
.online-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }
.online-metrics div { padding: 14px; background: #f7f9fc; border-radius: 8px; }
.online-metrics span, .online-metrics strong, .online-metrics small { display: block; }
.online-metrics span, .online-metrics small { color: #909399; font-size: 12px; }
.online-metrics strong { margin: 7px 0; font-size: 18px; }
.artifacts { padding-top: 14px; border-top: 1px solid #ebeef5; }
.artifacts .el-button { margin: 4px; }
.action-bar {
  background: #fff;
  border: 1px solid #e5eaf1;
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 18px;
  box-shadow: 0 4px 18px rgb(31 45 61 / 4%);
}
.eyebrow {
  color: #409eff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1.8px;
}
.status-strip,
.panel,
.metric-card {
  background: #fff;
  border: 1px solid #e5eaf1;
  border-radius: 12px;
  box-shadow: 0 4px 18px rgb(31 45 61 / 4%);
}
.status-strip {
  padding: 18px 22px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  margin-bottom: 18px;
}
.model-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 320px;
  .model-icon {
    width: 46px;
    height: 46px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    color: #fff;
    font-weight: 800;
    font-size: 22px;
    background: linear-gradient(135deg, #409eff, #675df4);
  }
  strong,
  span {
    display: block;
  }
  strong {
    font-size: 17px;
  }
  span {
    color: #8492a6;
    font-size: 13px;
    margin-top: 5px;
  }
}
.status-items {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 18px;
  div {
    border-left: 1px solid #ebeef5;
    padding-left: 18px;
  }
  span,
  strong {
    display: block;
  }
  span {
    color: #909399;
    font-size: 12px;
    margin-bottom: 8px;
  }
  strong {
    font-size: 13px;
    word-break: break-word;
  }
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  margin-bottom: 18px;
}
.metric-card {
  padding: 18px;
  border-top: 3px solid #dcdfe6;
  span,
  strong,
  small {
    display: block;
  }
  span {
    color: #6b7280;
    font-size: 13px;
  }
  strong {
    font-size: 28px;
    margin: 10px 0 8px;
    color: #172033;
  }
  small {
    color: #a0a7b4;
  }
  &.primary {
    border-top-color: #409eff;
  }
  &.warning {
    border-top-color: #e6a23c;
  }
}
.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
  gap: 18px;
  margin-bottom: 18px;
}
.panel {
  padding: 22px;
  min-width: 0;
}
.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
  h2 {
    font-size: 17px;
    margin: 0 0 5px;
  }
  p {
    color: #909399;
    font-size: 13px;
    margin: 0;
  }
}
.legend {
  display: flex;
  gap: 18px;
  font-size: 12px;
  span::before {
    content: '';
    display: inline-block;
    width: 18px;
    height: 3px;
    vertical-align: middle;
    margin-right: 6px;
    border-radius: 3px;
  }
  .miou::before {
    background: #409eff;
  }
  .accuracy::before {
    background: #67c23a;
  }
}
.line-chart {
  .curve-line {
    fill: none;
    stroke-width: 3;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .miou-line {
    stroke: #409eff;
  }
  .accuracy-line {
    stroke: #67c23a;
  }
  svg {
    width: 100%;
    min-height: 260px;
    .grid-lines line {
      stroke: #edf1f7;
      stroke-width: 1;
    }
    .grid-lines text {
      fill: #9ca3af;
      font-size: 11px;
    }
  }
  .x-axis {
    display: flex;
    justify-content: space-between;
    color: #909399;
    font-size: 11px;
    padding: 0 5%;
  }
}
.parameter-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 24px;
  margin: 0;
  div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px dashed #ebeef5;
  }
  dt {
    color: #909399;
  }
  dd {
    margin: 0;
    font-weight: 600;
    text-align: right;
  }
  &.compact {
    grid-template-columns: 1fr;
    margin-bottom: 18px;
  }
}
.class-panel {
  margin-bottom: 18px;
}
.class-table-wrap {
  overflow-x: auto;
}
.class-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th {
    color: #8492a6;
    background: #f7f9fc;
    text-align: left;
    padding: 12px 14px;
  }
  td {
    padding: 13px 14px;
    border-bottom: 1px solid #eef1f6;
  }
  td:first-child {
    display: flex;
    align-items: center;
    min-width: 160px;
    i {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 10px;
    }
    strong {
      margin-right: 7px;
    }
    small {
      color: #a0a7b4;
    }
  }
}
.iou-bar {
  width: 180px;
  height: 8px;
  background: #edf1f7;
  border-radius: 6px;
  overflow: hidden;
  span {
    display: block;
    height: 100%;
    border-radius: 6px;
  }
}
.bottom-grid {
  align-items: stretch;
  margin-bottom: 0;
}
.matrix-panel img {
  display: block;
  width: 100%;
  max-height: 560px;
  object-fit: contain;
}
.deployment-state {
  display: flex;
  align-items: center;
  gap: 12px;
  border-radius: 8px;
  background: #fef0f0;
  padding: 14px;
  margin-bottom: 14px;
  > span {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #f56c6c;
    box-shadow: 0 0 0 5px rgb(245 108 108 / 12%);
  }
  strong,
  small {
    display: block;
  }
  small {
    margin-top: 4px;
    color: #909399;
  }
  &.ready {
    background: #f0f9eb;
    > span {
      background: #67c23a;
      box-shadow: 0 0 0 5px rgb(103 194 58 / 12%);
    }
  }
}
.predict-upload {
  width: 100%;
}
.predict-upload :deep(.el-upload-dragger) {
  width: 100%;
  padding: 20px;
}
@media (max-width: 1280px) {
  .metric-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .status-items {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 900px) {
  .status-strip {
    align-items: flex-start;
    flex-direction: column;
  }
  .status-items {
    width: 100%;
  }
  .content-grid, .online-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .dashboard-header {
    flex-direction: column;
  }
  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .status-items {
    grid-template-columns: 1fr;
  }
  .parameter-list {
    grid-template-columns: 1fr;
  }
}
</style>
