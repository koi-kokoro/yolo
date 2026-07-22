<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { detectSingle, getDetectionModelInfo } from '@/api/detection'

const router = useRouter()
const loading = ref(true)
const loadError = ref('')
const modelInfo = ref(null)
const showPredictDialog = ref(false)
const predictFile = ref(null)
const predicting = ref(false)
const predictResult = ref(null)
const conf = ref(0.25)
const iou = ref(0.45)

const metrics = computed(() => modelInfo.value?.metrics || {})
const classes = computed(() => modelInfo.value?.classes || [])
const inputSize = computed(() => modelInfo.value?.input_size || 640)
const currentImage = computed(() => predictResult.value?.images?.[0] || null)

const percent = (value, digits = 3) =>
  value == null ? '暂无数据' : `${(Number(value) * 100).toFixed(digits)}%`

const shortSha = computed(() => {
  const value = modelInfo.value?.model_sha256
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : '—'
})

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    modelInfo.value = await getDetectionModelInfo()
    if (!modelInfo.value?.ready) {
      loadError.value = modelInfo.value?.message || 'DIOR 模型未就绪'
    }
  } catch (error) {
    loadError.value = error?.response?.data?.detail || error?.message || 'DIOR 模型状态加载失败'
    modelInfo.value = { ready: false }
  } finally {
    loading.value = false
  }
}

function handlePredictFileChange(file) {
  predictFile.value = file.raw
  predictResult.value = null
}

async function runPredict() {
  if (!predictFile.value) return
  predicting.value = true
  const formData = new FormData()
  formData.append('file', predictFile.value)
  try {
    predictResult.value = await detectSingle(formData, {
      conf: conf.value,
      iou: iou.value,
      image_size: inputSize.value,
    })
    ElMessage.success(`检测完成，共发现 ${predictResult.value.total_objects} 个目标`)
  } finally {
    predicting.value = false
  }
}

defineExpose({ refresh })
onMounted(refresh)
</script>

<template>
  <section v-loading="loading" class="dior-dashboard">
    <el-alert
      v-if="loadError"
      :title="loadError"
      description="仍可查看页面结构；请检查 DIOR 部署目录、权重完整性和后端推理依赖。"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="action-bar">
      <el-space wrap>
        <el-button
          type="primary"
          :disabled="!modelInfo?.ready"
          @click="showPredictDialog = true"
        >
          测试验证
        </el-button>
        <el-button @click="router.push('/facility-detection')">进入设施检测</el-button>
        <el-tag type="info" effect="plain">离线训练 / 人工审核部署</el-tag>
      </el-space>
    </div>

    <section class="dashboard-section">
      <div class="section-heading">
        <div><span>DEPLOYED MODEL</span><h2>DIOR 设施目标检测部署模型</h2></div>
        <p>检测指标与 LoveDA 像素级指标独立展示，不混用 mAP、mIoU 或统计单位。</p>
      </div>

      <div class="status-strip">
        <div class="model-identity">
          <div class="model-icon">D</div>
          <div>
            <strong>{{ modelInfo?.display_name || 'DIOR 遥感设施目标检测' }}</strong>
            <span>{{ modelInfo?.model || 'dior-yolo11n' }} · {{ modelInfo?.version || '—' }}</span>
          </div>
        </div>
        <div class="status-items">
          <div>
            <span>部署状态</span>
            <el-tag :type="modelInfo?.ready ? 'success' : 'danger'" effect="dark">
              {{ modelInfo?.ready ? '已部署可用' : '推理服务未就绪' }}
            </el-tag>
          </div>
          <div><span>任务类型</span><strong>目标检测（HBB）</strong></div>
          <div><span>推理引擎</span><strong>{{ modelInfo?.engine || 'ultralytics-pt' }}</strong></div>
          <div><span>运行设备</span><strong>{{ modelInfo?.device || '—' }}</strong></div>
        </div>
      </div>

      <div class="metric-grid">
        <article class="metric-card primary">
          <span>验证集 mAP50-95</span><strong>{{ percent(metrics.map50_95) }}</strong>
          <small>综合定位与分类性能</small>
        </article>
        <article class="metric-card">
          <span>验证集 mAP50</span><strong>{{ percent(metrics.map50) }}</strong>
          <small>IoU 0.50</small>
        </article>
        <article class="metric-card">
          <span>Precision</span><strong>{{ percent(metrics.precision) }}</strong>
          <small>检测目标准确率</small>
        </article>
        <article class="metric-card warning">
          <span>Recall</span><strong>{{ percent(metrics.recall) }}</strong>
          <small>标注目标召回率</small>
        </article>
      </div>

      <div class="content-grid">
        <article class="panel">
          <div class="panel-title">
            <div><h2>DIOR 20 类目标</h2><p>类别顺序来自部署 metadata，并与 checkpoint 严格核验</p></div>
            <el-tag>{{ classes.length }} 类</el-tag>
          </div>
          <div v-if="classes.length" class="class-tags">
            <el-tag v-for="item in classes" :key="item.id" effect="plain" size="large">
              <b>{{ item.id }}</b> {{ item.display_name || item.name }}
              <small v-if="item.display_name && item.display_name !== item.name">{{ item.name }}</small>
            </el-tag>
          </div>
          <el-empty v-else description="模型未就绪，暂未读取类别元数据" />
        </article>

        <article class="panel">
          <div class="panel-title">
            <div><h2>实际推理模型</h2><p>来自 DIOR runtime / deployment metadata</p></div>
          </div>
          <dl class="parameter-list compact">
            <div><dt>模型名称</dt><dd>{{ modelInfo?.model || '—' }}</dd></div>
            <div><dt>模型版本</dt><dd>{{ modelInfo?.version || '—' }}</dd></div>
            <div><dt>模型格式</dt><dd>Ultralytics PT</dd></div>
            <div><dt>输入尺寸</dt><dd>{{ inputSize }} × {{ inputSize }}</dd></div>
            <div><dt>公开类别</dt><dd>{{ classes.length || 20 }} 类</dd></div>
            <div><dt>SHA256</dt><dd class="hash-value">{{ shortSha }}</dd></div>
          </dl>
          <el-alert
            title="当前未开放 DIOR 网页在线训练"
            description="DIOR 采用离线训练、独立评估、人工审核和部署包登记流程；此处只展示真实部署状态，不创建伪训练任务。"
            type="info"
            show-icon
            :closable="false"
          />
        </article>
      </div>
    </section>

    <el-dialog v-model="showPredictDialog" title="DIOR 单图测试验证" width="920px">
      <el-row :gutter="18">
        <el-col :span="9">
          <el-upload
            drag
            action=""
            :auto-upload="false"
            :on-change="handlePredictFileChange"
            accept=".jpg,.jpeg,.png,image/jpeg,image/png"
            :limit="1"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div>拖放遥感图片，或 <em>点击选择</em></div>
          </el-upload>
          <el-form label-position="top" class="predict-options">
            <el-form-item label="置信度阈值">
              <el-slider v-model="conf" :min="0.05" :max="0.95" :step="0.05" show-input />
            </el-form-item>
            <el-form-item label="NMS IoU 阈值">
              <el-slider v-model="iou" :min="0.1" :max="0.9" :step="0.05" show-input />
            </el-form-item>
          </el-form>
          <el-button
            type="primary"
            style="width: 100%"
            :loading="predicting"
            :disabled="!predictFile"
            @click="runPredict"
          >
            开始目标检测
          </el-button>
        </el-col>
        <el-col :span="15">
          <template v-if="currentImage">
            <img class="result-image" :src="currentImage.annotated_image_url" alt="DIOR 检测结果" />
            <div class="result-summary">
              {{ currentImage.filename }} · {{ currentImage.total_objects }} 个目标 ·
              {{ currentImage.inference_time_ms }} ms
            </div>
            <el-table :data="currentImage.detections" max-height="280" empty-text="当前阈值下未检测到目标">
              <el-table-column prop="class_name_cn" label="类别" min-width="90" />
              <el-table-column prop="class_name" label="英文名" min-width="130" />
              <el-table-column label="置信度" width="90">
                <template #default="{ row }">{{ (row.confidence * 100).toFixed(1) }}%</template>
              </el-table-column>
            </el-table>
          </template>
          <el-empty v-else description="上传图片并运行 DIOR 检测" />
        </el-col>
      </el-row>
    </el-dialog>
  </section>
</template>

<style scoped lang="scss">
.dior-dashboard { min-height: 420px; }
.dior-dashboard > .el-alert { margin-bottom: 16px; }
.action-bar,
.status-strip,
.panel,
.metric-card {
  background: linear-gradient(150deg, rgba(255, 255, 255, .96), rgba(248, 250, 253, .9));
  border: 1px solid rgba(122, 146, 181, .16);
  border-radius: 14px;
  box-shadow: 0 4px 18px rgb(31 45 61 / 4%);
}
.action-bar { padding: 18px 22px; margin-bottom: 18px; }
.dashboard-section { margin-bottom: 28px; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin: 18px 0 14px; }
.section-heading span { color: $primary-color; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }
.section-heading h2 { margin: 4px 0 0; font-size: 21px; }
.section-heading p { color: $text-secondary; margin: 0; font-size: 13px; }
.status-strip { padding: 18px 22px; display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 18px; }
.model-identity { display: flex; align-items: center; gap: 14px; min-width: 320px; }
.model-identity strong, .model-identity span { display: block; }
.model-identity strong { font-size: 17px; }
.model-identity span { color: $text-secondary; font-size: 13px; margin-top: 5px; }
.model-icon { width: 46px; height: 46px; border-radius: 12px; display: grid; place-items: center; color: #fff; font-size: 22px; font-weight: 800; background: linear-gradient(135deg, #d97706, #f59e0b); }
.status-items { flex: 1; display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 18px; }
.status-items div { border-left: 1px solid rgba(122, 146, 181, .12); padding-left: 18px; }
.status-items span, .status-items strong { display: block; }
.status-items span { color: $text-secondary; font-size: 12px; margin-bottom: 8px; }
.status-items strong { font-size: 13px; word-break: break-word; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.metric-card { padding: 18px; border-top: 3px solid rgba(122, 146, 181, .22); }
.metric-card.primary { border-top-color: $primary-color; }
.metric-card.warning { border-top-color: $warning-color; }
.metric-card span, .metric-card strong, .metric-card small { display: block; }
.metric-card span { color: $text-secondary; font-size: 13px; }
.metric-card strong { color: $text-primary; font-size: 28px; margin: 10px 0 8px; }
.metric-card small { color: $text-muted; }
.content-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); gap: 18px; }
.panel { padding: 22px; min-width: 0; }
.panel-title { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.panel-title h2 { font-size: 17px; margin: 0 0 5px; }
.panel-title p { color: $text-secondary; font-size: 13px; margin: 0; }
.class-tags { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.class-tags .el-tag { justify-content: flex-start; height: auto; min-height: 40px; padding: 7px 10px; overflow: hidden; }
.class-tags b { display: inline-grid; place-items: center; min-width: 22px; height: 22px; margin-right: 7px; border-radius: 6px; background: rgba(64, 158, 255, .12); }
.class-tags small { display: block; margin-left: 7px; overflow: hidden; color: $text-muted; text-overflow: ellipsis; }
.parameter-list { display: grid; grid-template-columns: 1fr; gap: 0; margin: 0 0 18px; }
.parameter-list div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px dashed rgba(122, 146, 181, .16); }
.parameter-list dt { color: $text-secondary; }
.parameter-list dd { margin: 0; font-weight: 600; text-align: right; }
.hash-value { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
.predict-options { margin-top: 18px; }
.result-image { display: block; width: 100%; max-height: 390px; object-fit: contain; border-radius: 8px; background: #f5f7fa; }
.result-summary { margin: 10px 0; color: $text-secondary; font-size: 13px; text-align: center; }
.upload-icon { font-size: 48px; color: $primary-color; }
@media (max-width: 1200px) {
  .status-strip { align-items: flex-start; flex-direction: column; }
  .status-items { width: 100%; }
  .class-tags { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .content-grid { grid-template-columns: 1fr; }
  .metric-grid, .status-items { grid-template-columns: repeat(2, 1fr); }
  .class-tags { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .section-heading { align-items: flex-start; flex-direction: column; }
  .metric-grid, .status-items, .class-tags { grid-template-columns: 1fr; }
  .model-identity { min-width: 0; }
}
</style>
