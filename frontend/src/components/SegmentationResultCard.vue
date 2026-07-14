<template>
  <div class="segmentation-result-card">
    <div class="card-header">
      <el-icon><DataAnalysis /></el-icon>
      <span>语义分割结果</span>
      <el-tag size="small" type="success">
        {{ isBatch ? `${successfulImages} 张图` : `${totalPixels} 像素` }}
      </el-tag>
    </div>

    <div class="card-body">
      <!-- Single image annotated result -->
      <div v-if="!isBatch && !isVideo && annotatedImageSrc" class="result-image">
        <img :src="annotatedImageSrc" alt="分割标注图" @click="showFullImage = true" />
      </div>

      <!-- Video key-frame grid -->
      <div v-if="isVideo && videoFrames.length > 0" class="result-images-grid">
        <div
          v-for="(frame, index) in videoFrames"
          :key="index"
          class="grid-image"
          @click="previewImage(frame)"
        >
          <img :src="frame.src" :alt="frame.name" />
          <span class="image-name">{{ frame.name }}</span>
        </div>
      </div>

      <!-- Batch / ZIP image grid -->
      <div v-if="isBatch && batchImages.length > 0" class="result-images-grid">
        <div
          v-for="(img, index) in batchImages"
          :key="index"
          class="grid-image"
          @click="previewImage(img)"
        >
          <img :src="img.src" :alt="img.name" />
          <span class="image-name">{{ img.name }}</span>
        </div>
      </div>

      <!-- Statistics -->
      <div class="result-stats">
        <div class="stat-item">
          <span class="stat-label">推理耗时</span>
          <span class="stat-value">{{ inferenceTimeText }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">图片数量</span>
          <span class="stat-value">{{ isBatch ? result.total_images ?? 0 : isVideo ? result.processed_frames ?? 0 : 1 }} 张</span>
        </div>
        <div class="stat-item" v-if="isBatch">
          <span class="stat-label">成功处理</span>
          <span class="stat-value">{{ successfulImages }} 张</span>
        </div>
        <div class="stat-item" v-if="isVideo">
          <span class="stat-label">总帧数</span>
          <span class="stat-value">{{ result.total_frames ?? 0 }}</span>
        </div>

        <el-table
          v-if="classCountsArray.length > 0"
          :data="classCountsArray"
          size="small"
          style="margin-top: 12px"
        >
          <el-table-column prop="displayName" label="类别" />
          <el-table-column v-if="!isVideo" prop="count" label="像素数" width="90" />
          <el-table-column :label="isVideo ? '总占比' : '占比'" width="90">
            <template #default="{ row }">
              {{ (row.ratio * 100).toFixed(1) }}%
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="isVideo && videoFrameSummaries.length > 0" class="video-analysis">
        <div class="analysis-section-title">逐帧分析</div>
        <div v-for="(summary, index) in videoFrameSummaries" :key="index" class="frame-summary">
          <div class="frame-summary-header">
            <span class="frame-summary-title">{{ summary.frame_label || `第 ${summary.frame_index + 1} 帧` }}</span>
            <span class="frame-summary-time">{{ summary.timestamp ?? 0 }}s</span>
          </div>
          <div class="analysis-text">{{ summary.analysis_text }}</div>
          <div class="ratio-list">
            <div v-for="(item, ratioIndex) in summary.class_ratios" :key="ratioIndex" class="ratio-row">
              <span class="ratio-name">{{ item.display_name || item.name }}</span>
              <div class="ratio-bar-track">
                <div class="ratio-bar-fill" :style="{ width: `${Math.max(4, (item.ratio || 0) * 100)}%` }"></div>
              </div>
              <span class="ratio-value">{{ ((item.ratio || 0) * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>

        <div v-if="ratioTrend.length > 0" class="trend-panel">
          <div class="analysis-section-title">占比变化趋势</div>
          <svg viewBox="0 0 320 140" class="trend-chart">
            <line x1="20" y1="110" x2="300" y2="110" class="trend-axis" />
            <line x1="20" y1="20" x2="20" y2="110" class="trend-axis" />
            <polyline
              v-for="series in ratioTrend"
              :key="series.name"
              :points="buildTrendPoints(series.values)"
              class="trend-line"
              :style="{ stroke: getTrendColor(series.name) }"
            />
          </svg>
          <div class="trend-legend">
            <span v-for="series in ratioTrend" :key="series.name" class="legend-item">
              <span class="legend-dot" :style="{ background: getTrendColor(series.name) }"></span>
              {{ series.display_name || series.name }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="showFullImage" title="分割标注图" width="80%">
      <img v-if="previewSrc" :src="previewSrc" style="width: 100%" alt="分割标注图" />
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * SegmentationResultCard — render a semantic segmentation result inside a chat message.
 */
import { DataAnalysis } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'

const props = defineProps({
  result: {
    type: Object,
    required: true,
  },
})

const showFullImage = ref(false)
const previewSrc = ref(null)

const isBatch = computed(() => {
  return props.result.mode === 'batch' || props.result.mode === 'zip'
})

const isVideo = computed(() => {
  return props.result.mode === 'video'
})

const annotatedImageSrc = computed(() => {
  const r = props.result
  if (r.annotated_image) {
    return `data:image/jpeg;base64,${r.annotated_image}`
  }
  if (r.annotated_image_url) {
    return r.annotated_image_url
  }
  return null
})

const batchImages = computed(() => {
  const images = props.result.annotated_images || []
  return images
    .filter((img) => img.annotated_image)
    .map((img) => ({
      name: img.filename || 'image',
      src: `data:image/jpeg;base64,${img.annotated_image}`,
    }))
})

const videoFrames = computed(() => {
  const frames = props.result.key_frames || []
  return frames
    .filter((frame) => frame.annotated_image_base64)
    .map((frame, index) => ({
      name: `第 ${frame.frame_index ?? index + 1} 帧 · ${frame.timestamp ?? 0}s`,
      src: `data:image/jpeg;base64,${frame.annotated_image_base64}`,
    }))
})

const videoFrameSummaries = computed(() => {
  const summaries = props.result.frame_summaries || []
  return summaries.map((summary, index) => ({
    ...summary,
    frame_label: props.result.frame_labels?.[index] || `第 ${summary.frame_index + 1} 帧`,
  }))
})

const ratioTrend = computed(() => props.result.ratio_trend || [])

const successfulImages = computed(() => {
  return props.result.successful_images ?? batchImages.value.length
})

const inferenceTimeText = computed(() => {
  const ms = props.result.total_inference_time ?? props.result.total_inference_ms ?? props.result.inference_time_ms ?? 0
  return ms ? `${Math.round(ms)}ms` : '-'
})

const totalPixels = computed(() => {
  if (isVideo.value) {
    return Object.values(props.result.class_counts || {}).reduce((a, b) => a + b, 0)
  }
  if (isBatch.value) {
    return Object.values(props.result.class_counts || {}).reduce((a, b) => a + b, 0)
  }
  return (props.result.image_width || 0) * (props.result.image_height || 0)
})

function previewImage(img) {
  previewSrc.value = img.src
  showFullImage.value = true
}

function getTrendColor(name) {
  const palette = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399']
  const index = (name?.length || 0) % palette.length
  return palette[index]
}

function buildTrendPoints(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return ''
  }
  const width = 280
  const height = 90
  const maxValue = Math.max(0.01, ...values.map((value) => Number(value) || 0))
  return values
    .map((value, index) => {
      const x = 20 + (index / Math.max(1, values.length - 1)) * width
      const y = 110 - ((Number(value) || 0) / maxValue) * height
      return `${x},${y}`
    })
    .join(' ')
}

const classCountsArray = computed(() => {
  if (isVideo.value) {
    const counts = props.result.class_counts || {}
    const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1
    return Object.entries(counts).map(([name, count]) => ({
      displayName: name,
      count: Number(count) || 0,
      ratio: (Number(count) || 0) / total,
    }))
  }

  const statistics = props.result.class_statistics || []
  if (statistics.length > 0) {
    return statistics.map((item) => ({
      displayName: item.display_name || item.name,
      count: item.pixel_count || 0,
      ratio: item.ratio || 0,
    }))
  }
  const counts = props.result.class_counts || {}
  const total = totalPixels.value || 1
  return Object.entries(counts).map(([name, count]) => ({
    displayName: name,
    count,
    ratio: count / total,
  }))
})
</script>

<style lang="scss" scoped>
.segmentation-result-card {
  margin-top: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #e0e0e0;
  font-weight: 600;
  font-size: 14px;
}

.card-body {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px;
}

.result-image {
  flex: 1;
  min-width: 0;

  img {
    width: 100%;
    max-height: 300px;
    object-fit: contain;
    border-radius: 4px;
    cursor: pointer;
    transition: opacity 0.2s;

    &:hover {
      opacity: 0.8;
    }
  }
}

.result-images-grid {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;

  .grid-image {
    text-align: center;
    cursor: pointer;

    img {
      width: 100%;
      height: 100px;
      object-fit: cover;
      border-radius: 4px;
      border: 1px solid #e0e0e0;
      transition: opacity 0.2s;

      &:hover {
        opacity: 0.8;
      }
    }

    .image-name {
      display: block;
      font-size: 11px;
      color: #909399;
      margin-top: 4px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

.result-stats {
  flex: 0 0 220px;

  .stat-item {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 13px;
  }

  .stat-label {
    color: #909399;
  }

  .stat-value {
    font-weight: 600;
    color: #303133;
  }
}

.video-analysis {
  flex: 1 1 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.analysis-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.frame-summary {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 10px;
  background: #fafafa;
}

.frame-summary-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 12px;
  color: #606266;
}

.frame-summary-title {
  font-weight: 600;
  color: #303133;
}

.analysis-text {
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}

.ratio-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ratio-row {
  display: grid;
  grid-template-columns: 90px 1fr 44px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.ratio-name {
  color: #606266;
}

.ratio-bar-track {
  height: 8px;
  border-radius: 999px;
  background: #e4e7ed;
  overflow: hidden;
}

.ratio-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #409eff, #67c23a);
}

.ratio-value {
  color: #303133;
  text-align: right;
}

.trend-panel {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 10px;
  background: #fafafa;
}

.trend-chart {
  width: 100%;
  height: 140px;
}

.trend-axis {
  stroke: #c0c4cc;
  stroke-width: 1;
}

.trend-line {
  fill: none;
  stroke-width: 2.5;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.trend-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
