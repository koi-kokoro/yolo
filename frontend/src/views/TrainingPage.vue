<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSemanticModelInfo } from '@/api/semantic'

const loading = ref(true)
const loadError = ref('')
const metrics = ref(null)
const report = ref(null)
const runtime = ref(null)
const matrixMode = ref('normalized')

const classNamesCn = {
  background: '背景',
  building: '建筑',
  road: '道路',
  water: '水体',
  barren: '裸地',
  forest: '森林',
  agricultural: '农田',
}

const classColors = ['#606266', '#f56c6c', '#e6a23c', '#409eff', '#a06b3b', '#34a853', '#9acd32']

const overall = computed(() => metrics.value?.overall || {})
const parameters = computed(() => report.value?.parameters || {})
const epochMetrics = computed(() => report.value?.epoch_metrics || [])
const perClass = computed(() => (overall.value.per_class || []).map((item, index) => ({
  ...item,
  displayName: classNamesCn[item.class_name] || item.class_name,
  color: classColors[index] || '#409eff',
})))

const trainingStatus = computed(() => {
  const status = report.value?.status
  if (status === 'early_stopped') return { label: '早停完成', type: 'success' }
  if (status === 'completed') return { label: '训练完成', type: 'success' }
  return { label: status || '未知', type: 'info' }
})

const runtimeStatus = computed(() => runtime.value?.ready
  ? { label: '已部署可用', type: 'success' }
  : { label: '推理服务未就绪', type: 'danger' })

const chart = computed(() => {
  const points = epochMetrics.value
  if (!points.length) return { miou: '', accuracy: '', bestX: 0, bestY: 0 }
  const width = 900
  const height = 260
  const padX = 48
  const padY = 24
  const min = 0.3
  const max = 0.75
  const x = (index) => padX + index * ((width - padX * 2) / Math.max(points.length - 1, 1))
  const y = (value) => height - padY - ((value - min) / (max - min)) * (height - padY * 2)
  const polyline = (key) => points.map((item, index) => `${x(index)},${y(Number(item[key]))}`).join(' ')
  const bestIndex = points.reduce((best, item, index) => Number(item['metrics/mIoU']) > Number(points[best]['metrics/mIoU']) ? index : best, 0)
  return {
    miou: polyline('metrics/mIoU'),
    accuracy: polyline('metrics/pixel_acc'),
    bestX: x(bestIndex),
    bestY: y(Number(points[bestIndex]['metrics/mIoU'])),
  }
})

const percent = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`
const duration = computed(() => {
  const seconds = Number(report.value?.elapsed_seconds || 0)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${hours} 小时 ${minutes} 分钟`
})

async function loadDashboard() {
  loading.value = true
  loadError.value = ''
  try {
    const [metricsResponse, reportResponse, runtimeResponse] = await Promise.all([
      fetch('/model-dashboard/metrics.json'),
      fetch('/model-dashboard/baseline_report.json'),
      getSemanticModelInfo().catch(() => null),
    ])
    if (!metricsResponse.ok || !reportResponse.ok) throw new Error('训练指标文件读取失败')
    metrics.value = await metricsResponse.json()
    report.value = await reportResponse.json()
    runtime.value = runtimeResponse
  } catch (error) {
    loadError.value = error?.message || '模型看板加载失败'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<template>
  <section v-loading="loading" class="training-dashboard">
    <header class="dashboard-header">
      <div>
        <div class="eyebrow">MODEL MANAGEMENT</div>
        <h1>模型管理看板</h1>
        <p>展示当前 YOLO26 Semantic 基线的训练配置、验证指标与部署状态。本页面仅用于模型管理和结果审阅，不提供在线训练。</p>
      </div>
      <el-button :loading="loading" @click="loadDashboard">刷新状态</el-button>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false" />

    <template v-if="metrics && report">
      <div class="status-strip">
        <div class="model-identity">
          <div class="model-icon">S</div>
          <div>
            <strong>YOLO26n Semantic</strong>
            <span>LoveDA 7 类土地覆盖语义分割 · Baseline V1</span>
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
        <article class="metric-card primary"><span>mIoU</span><strong>{{ percent(overall.miou) }}</strong><small>完整验证集 · 1669 张</small></article>
        <article class="metric-card"><span>像素准确率</span><strong>{{ percent(overall.pixel_accuracy) }}</strong><small>有效像素整体准确率</small></article>
        <article class="metric-card"><span>Mean Dice / F1</span><strong>{{ percent(overall.mean_dice_f1) }}</strong><small>7 类宏平均</small></article>
        <article class="metric-card"><span>最佳 Epoch</span><strong>20</strong><small>共运行 {{ report.epochs_recorded }} epoch</small></article>
        <article class="metric-card"><span>Urban mIoU</span><strong>{{ percent(metrics.Urban?.miou) }}</strong><small>城市域 · {{ metrics.Urban?.images }} 张</small></article>
        <article class="metric-card warning"><span>Rural mIoU</span><strong>{{ percent(metrics.Rural?.miou) }}</strong><small>农村域 · 后续重点优化</small></article>
      </div>

      <div class="content-grid">
        <article class="panel chart-panel">
          <div class="panel-title"><div><h2>训练趋势</h2><p>验证集 mIoU 与像素准确率</p></div><div class="legend"><span class="miou">mIoU</span><span class="accuracy">Pixel Accuracy</span></div></div>
          <div class="line-chart">
            <svg viewBox="0 0 900 260" role="img" aria-label="训练指标趋势图">
              <g class="grid-lines"><line v-for="value in [0.3,0.4,0.5,0.6,0.7]" :key="value" x1="48" x2="852" :y1="236 - ((value - 0.3) / 0.45) * 212" :y2="236 - ((value - 0.3) / 0.45) * 212" /><text v-for="value in [0.3,0.4,0.5,0.6,0.7]" :key="`t-${value}`" x="8" :y="240 - ((value - 0.3) / 0.45) * 212">{{ value.toFixed(1) }}</text></g>
              <polyline :points="chart.accuracy" fill="none" stroke="#67c23a" stroke-width="3" />
              <polyline :points="chart.miou" fill="none" stroke="#409eff" stroke-width="3" />
              <circle :cx="chart.bestX" :cy="chart.bestY" r="6" fill="#409eff" stroke="white" stroke-width="3" />
            </svg>
            <div class="x-axis"><span>Epoch 1</span><span>Epoch 10</span><span>Epoch 20（最佳）</span><span>Epoch 30</span></div>
          </div>
        </article>

        <article class="panel parameters-panel">
          <div class="panel-title"><div><h2>训练参数</h2><p>正式基线实验配置</p></div></div>
          <dl class="parameter-list">
            <div><dt>基础权重</dt><dd>{{ parameters.model }}</dd></div>
            <div><dt>数据集</dt><dd>LoveDA Semantic</dd></div>
            <div><dt>输入尺寸</dt><dd>{{ parameters.imgsz }} × {{ parameters.imgsz }}</dd></div>
            <div><dt>Batch Size</dt><dd>{{ parameters.batch }}</dd></div>
            <div><dt>最大 Epoch</dt><dd>{{ parameters.epochs }}</dd></div>
            <div><dt>Early Stopping</dt><dd>Patience {{ parameters.patience }}</dd></div>
            <div><dt>混合精度</dt><dd>{{ parameters.amp ? 'AMP 开启' : '关闭' }}</dd></div>
            <div><dt>随机种子</dt><dd>{{ parameters.seed }}</dd></div>
            <div><dt>训练设备</dt><dd>RTX 4060 Laptop GPU</dd></div>
            <div><dt>训练耗时</dt><dd>{{ duration }}</dd></div>
          </dl>
        </article>
      </div>

      <article class="panel class-panel">
        <div class="panel-title"><div><h2>各类别验证指标</h2><p>IoU、Dice、Precision 与 Recall；裸地和森林是当前主要弱项</p></div></div>
        <div class="class-table-wrap">
          <table class="class-table">
            <thead><tr><th>类别</th><th>IoU</th><th>Dice / F1</th><th>Precision</th><th>Recall</th><th>IoU 可视化</th></tr></thead>
            <tbody>
              <tr v-for="item in perClass" :key="item.class_id">
                <td><i :style="{ background: item.color }"></i><strong>{{ item.displayName }}</strong><small>{{ item.class_name }}</small></td>
                <td>{{ percent(item.iou) }}</td><td>{{ percent(item.dice_f1) }}</td><td>{{ percent(item.precision) }}</td><td>{{ percent(item.recall) }}</td>
                <td><div class="iou-bar"><span :style="{ width: percent(item.iou), background: item.color }"></span></div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <div class="content-grid bottom-grid">
        <article class="panel matrix-panel">
          <div class="panel-title"><div><h2>混淆矩阵</h2><p>真实类别与预测类别的像素级混淆关系</p></div><el-radio-group v-model="matrixMode" size="small"><el-radio-button value="normalized">归一化</el-radio-button><el-radio-button value="raw">原始计数</el-radio-button></el-radio-group></div>
          <img :src="matrixMode === 'normalized' ? '/model-dashboard/confusion_matrix_normalized.png' : '/model-dashboard/confusion_matrix.png'" alt="语义分割混淆矩阵" />
        </article>

        <article class="panel deployment-panel">
          <div class="panel-title"><div><h2>部署信息</h2><p>当前系统实际使用的模型产物</p></div></div>
          <div class="deployment-state" :class="{ ready: runtime?.ready }"><span></span><div><strong>{{ runtimeStatus.label }}</strong><small>{{ runtime?.message || '推理运行时已加载模型并可接受任务' }}</small></div></div>
          <dl class="parameter-list compact">
            <div><dt>模型版本</dt><dd>{{ runtime?.model_version || 'baseline-v1' }}</dd></div>
            <div><dt>模型名称</dt><dd>{{ runtime?.model_name || 'YOLO26n Semantic' }}</dd></div>
            <div><dt>模型格式</dt><dd>Dynamic ONNX</dd></div>
            <div><dt>输入张量</dt><dd>N × 3 × 512 × 512</dd></div>
            <div><dt>公开类别</dt><dd>7 类</dd></div>
            <div><dt>ONNX/PT 一致率</dt><dd>100%</dd></div>
          </dl>
          <el-alert title="此看板不启动训练" description="模型训练在隔离训练环境中离线执行。验证通过后导出并登记模型版本，生产页面只负责审阅和部署状态监控。" type="info" :closable="false" show-icon />
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped lang="scss">
.training-dashboard { min-height: 100%; color: #1f2937; }
.dashboard-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 22px; h1 { margin: 4px 0 8px; font-size: 28px; color: #172033; } p { margin: 0; color: #6b7280; line-height: 1.7; } }
.eyebrow { color: #409eff; font-size: 12px; font-weight: 700; letter-spacing: 1.8px; }
.status-strip, .panel, .metric-card { background: #fff; border: 1px solid #e5eaf1; border-radius: 12px; box-shadow: 0 4px 18px rgb(31 45 61 / 4%); }
.status-strip { padding: 18px 22px; display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 18px; }
.model-identity { display: flex; align-items: center; gap: 14px; min-width: 320px; .model-icon { width: 46px; height: 46px; border-radius: 12px; display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 22px; background: linear-gradient(135deg,#409eff,#675df4); } strong, span { display: block; } strong { font-size: 17px; } span { color: #8492a6; font-size: 13px; margin-top: 5px; } }
.status-items { flex: 1; display: grid; grid-template-columns: repeat(4,minmax(120px,1fr)); gap: 18px; div { border-left: 1px solid #ebeef5; padding-left: 18px; } span, strong { display: block; } span { color: #909399; font-size: 12px; margin-bottom: 8px; } strong { font-size: 13px; word-break: break-word; } }
.metric-grid { display: grid; grid-template-columns: repeat(6,1fr); gap: 14px; margin-bottom: 18px; }
.metric-card { padding: 18px; border-top: 3px solid #dcdfe6; span, strong, small { display: block; } span { color: #6b7280; font-size: 13px; } strong { font-size: 28px; margin: 10px 0 8px; color: #172033; } small { color: #a0a7b4; } &.primary { border-top-color: #409eff; } &.warning { border-top-color: #e6a23c; } }
.content-grid { display: grid; grid-template-columns: minmax(0,2fr) minmax(320px,1fr); gap: 18px; margin-bottom: 18px; }
.panel { padding: 22px; min-width: 0; }
.panel-title { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; h2 { font-size: 17px; margin: 0 0 5px; } p { color: #909399; font-size: 13px; margin: 0; } }
.legend { display: flex; gap: 18px; font-size: 12px; span::before { content: ''; display: inline-block; width: 18px; height: 3px; vertical-align: middle; margin-right: 6px; border-radius: 3px; } .miou::before { background: #409eff; } .accuracy::before { background: #67c23a; } }
.line-chart svg { width: 100%; min-height: 260px; .grid-lines line { stroke: #edf1f7; stroke-width: 1; } .grid-lines text { fill: #9ca3af; font-size: 11px; } } .x-axis { display: flex; justify-content: space-between; color: #909399; font-size: 11px; padding: 0 5%; }
.parameter-list { display: grid; grid-template-columns: 1fr 1fr; gap: 0 24px; margin: 0; div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px dashed #ebeef5; } dt { color: #909399; } dd { margin: 0; font-weight: 600; text-align: right; } &.compact { grid-template-columns: 1fr; margin-bottom: 18px; } }
.class-panel { margin-bottom: 18px; }
.class-table-wrap { overflow-x: auto; }.class-table { width: 100%; border-collapse: collapse; font-size: 13px; th { color: #8492a6; background: #f7f9fc; text-align: left; padding: 12px 14px; } td { padding: 13px 14px; border-bottom: 1px solid #eef1f6; } td:first-child { display: flex; align-items: center; min-width: 160px; i { width: 10px; height: 10px; border-radius: 50%; margin-right: 10px; } strong { margin-right: 7px; } small { color: #a0a7b4; } } }
.iou-bar { width: 180px; height: 8px; background: #edf1f7; border-radius: 6px; overflow: hidden; span { display: block; height: 100%; border-radius: 6px; } }
.bottom-grid { align-items: stretch; margin-bottom: 0; }.matrix-panel img { display: block; width: 100%; max-height: 560px; object-fit: contain; }.deployment-state { display: flex; align-items: center; gap: 12px; border-radius: 8px; background: #fef0f0; padding: 14px; margin-bottom: 14px; > span { width: 10px; height: 10px; border-radius: 50%; background: #f56c6c; box-shadow: 0 0 0 5px rgb(245 108 108 / 12%); } strong, small { display: block; } small { margin-top: 4px; color: #909399; } &.ready { background: #f0f9eb; > span { background: #67c23a; box-shadow: 0 0 0 5px rgb(103 194 58 / 12%); } } }
@media (max-width: 1280px) { .metric-grid { grid-template-columns: repeat(3,1fr); } .status-items { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 900px) { .status-strip { align-items: flex-start; flex-direction: column; } .status-items { width: 100%; } .content-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .dashboard-header { flex-direction: column; } .metric-grid { grid-template-columns: repeat(2,1fr); } .status-items { grid-template-columns: 1fr; } .parameter-list { grid-template-columns: 1fr; } }
</style>
