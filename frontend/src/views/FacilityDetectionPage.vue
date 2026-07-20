<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

import { detectBatch, detectSingle, getDetectionModelInfo } from '@/api/detection'

const modelInfo = ref(null)
const selectedFiles = ref([])
const uploadRef = ref()
const loading = ref(false)
const result = ref(null)
const activeImage = ref(0)
const conf = ref(0.25)
const iou = ref(0.45)
const imageSize = ref(640)

const currentImage = computed(() => result.value?.images?.[activeImage.value] || null)
const canSubmit = computed(() => modelInfo.value?.ready && selectedFiles.value.length && !loading.value)

function onFilesChanged(_file, uploadFiles) {
  selectedFiles.value = uploadFiles.map((item) => item.raw).filter(Boolean)
  result.value = null
  activeImage.value = 0
}

function onFilesRemoved(_file, uploadFiles) {
  selectedFiles.value = uploadFiles.map((item) => item.raw).filter(Boolean)
}

function clear() {
  uploadRef.value?.clearFiles()
  selectedFiles.value = []
  result.value = null
  activeImage.value = 0
}

async function submit() {
  if (!canSubmit.value) return
  loading.value = true
  const form = new FormData()
  const params = { conf: conf.value, iou: iou.value, image_size: imageSize.value }
  try {
    if (selectedFiles.value.length === 1) {
      form.append('file', selectedFiles.value[0])
      result.value = await detectSingle(form, params)
    } else {
      selectedFiles.value.forEach((file) => form.append('files', file))
      result.value = await detectBatch(form, params)
    }
    activeImage.value = 0
    ElMessage.success(`检测完成，共发现 ${result.value.total_objects} 个目标`)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    modelInfo.value = await getDetectionModelInfo()
  } catch {
    modelInfo.value = { ready: false, message: '无法获取 DIOR 模型状态' }
  }
})
</script>

<template>
  <section class="facility-page">
    <div class="page-heading">
      <div>
        <h1>遥感设施目标检测</h1>
        <p>使用 DIOR YOLO11 检测机场、桥梁、港口、船舶、储油罐等 20 类遥感目标。</p>
      </div>
      <el-tag :type="modelInfo?.ready ? 'success' : 'danger'" size="large">
        DIOR 模型{{ modelInfo?.ready ? '已就绪' : '不可用' }}
      </el-tag>
    </div>

    <el-alert
      v-if="modelInfo && !modelInfo.ready"
      type="error"
      :closable="false"
      show-icon
      :title="modelInfo.message || 'DIOR 模型未就绪，请检查后端部署目录与依赖。'"
    />

    <div class="top-grid">
      <el-card shadow="never">
        <template #header><span>上传遥感图像</span></template>
        <el-upload
          ref="uploadRef"
          drag
          multiple
          :auto-upload="false"
          :limit="20"
          accept=".jpg,.jpeg,.png,image/jpeg,image/png"
          :disabled="loading"
          :on-change="onFilesChanged"
          :on-remove="onFilesRemoved"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖放图片到此处，或<em>点击选择</em></div>
          <template #tip><div class="el-upload__tip">支持 1–20 张 JPEG/PNG，单张最大 20 MiB</div></template>
        </el-upload>
        <div class="actions">
          <span>已选择 {{ selectedFiles.length }} 张图片</span>
          <div>
            <el-button :disabled="loading" @click="clear">清空</el-button>
            <el-button type="primary" :loading="loading" :disabled="!canSubmit" @click="submit">
              开始设施检测
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header><span>推理配置</span></template>
        <el-form label-position="top">
          <el-form-item label="置信度阈值">
            <el-slider v-model="conf" :min="0.05" :max="0.95" :step="0.05" show-input />
          </el-form-item>
          <el-form-item label="NMS IoU 阈值">
            <el-slider v-model="iou" :min="0.1" :max="0.9" :step="0.05" show-input />
          </el-form-item>
          <el-form-item label="输入尺寸">
            <el-select v-model="imageSize" style="width: 100%">
              <el-option :value="512" label="512 × 512" />
              <el-option :value="640" label="640 × 640" />
              <el-option :value="800" label="800 × 800" />
              <el-option :value="1024" label="1024 × 1024" />
            </el-select>
          </el-form-item>
        </el-form>
        <el-descriptions v-if="modelInfo?.ready" :column="1" border>
          <el-descriptions-item label="模型">{{ modelInfo.model }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ modelInfo.version }}</el-descriptions-item>
          <el-descriptions-item label="运行引擎">{{ modelInfo.engine }} / {{ modelInfo.device }}</el-descriptions-item>
          <el-descriptions-item label="mAP50-95">{{ modelInfo.metrics?.map50_95 ?? '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
    </div>

    <template v-if="result">
      <el-card shadow="never">
        <template #header>
          <div class="card-title">
            <span>检测结果</span>
            <span>共 {{ result.total_images }} 张图、{{ result.total_objects }} 个目标、{{ result.total_inference_ms }} ms</span>
          </div>
        </template>
        <el-tabs v-if="result.images.length > 1" v-model="activeImage" type="card">
          <el-tab-pane
            v-for="(image, index) in result.images"
            :key="`${image.filename}-${index}`"
            :label="`${image.filename} (${image.total_objects})`"
            :name="index"
          />
        </el-tabs>
        <div v-if="currentImage" class="result-grid">
          <div class="image-panel">
            <img :src="currentImage.annotated_image_url" :alt="`${currentImage.filename} 检测结果`">
            <p>{{ currentImage.filename }} · {{ currentImage.width }} × {{ currentImage.height }} · {{ currentImage.inference_time_ms }} ms</p>
          </div>
          <el-table :data="currentImage.detections" max-height="520" empty-text="当前阈值下未检测到目标">
            <el-table-column prop="class_name_cn" label="类别" min-width="110" />
            <el-table-column prop="class_name" label="英文名" min-width="150" show-overflow-tooltip />
            <el-table-column label="置信度" width="100">
              <template #default="{ row }">{{ (row.confidence * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="边界框" min-width="210">
              <template #default="{ row }">
                {{ row.bbox.x1 }}, {{ row.bbox.y1 }}, {{ row.bbox.x2 }}, {{ row.bbox.y2 }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header><span>类别汇总</span></template>
        <div class="statistics">
          <el-tag v-for="item in result.class_statistics" :key="item.class_name" size="large" effect="plain">
            {{ item.class_name_cn }}（{{ item.class_name }}） × {{ item.count }}
          </el-tag>
          <el-empty v-if="!result.class_statistics.length" description="当前阈值下未检测到目标" />
        </div>
      </el-card>
    </template>
  </section>
</template>

<style scoped lang="scss">
.facility-page { display: flex; flex-direction: column; gap: 16px; }
.page-heading, .card-title, .actions { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
h1 { margin: 0 0 8px; font-size: 26px; color: #303133; }
p { margin: 0; color: #606266; }
.top-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(320px, .75fr); gap: 16px; }
.actions { margin-top: 16px; color: #606266; }
.result-grid { display: grid; grid-template-columns: minmax(420px, 1fr) minmax(480px, 1fr); gap: 18px; }
.image-panel img { display: block; width: 100%; max-height: 560px; object-fit: contain; background: #f5f7fa; border-radius: 6px; }
.image-panel p { margin-top: 10px; text-align: center; font-size: 13px; }
.statistics { display: flex; flex-wrap: wrap; gap: 12px; }
@media (max-width: 1100px) { .top-grid, .result-grid { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .page-heading, .actions { align-items: flex-start; flex-direction: column; } }
</style>

