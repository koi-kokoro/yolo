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
      <div v-if="!isBatch && annotatedImageSrc" class="result-image">
        <img :src="annotatedImageSrc" alt="分割标注图" @click="showFullImage = true" />
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
          <span class="stat-value">{{ isBatch ? result.total_images ?? 0 : 1 }} 张</span>
        </div>
        <div class="stat-item" v-if="isBatch">
          <span class="stat-label">成功处理</span>
          <span class="stat-value">{{ successfulImages }} 张</span>
        </div>

        <el-table
          v-if="classCountsArray.length > 0"
          :data="classCountsArray"
          size="small"
          style="margin-top: 12px"
        >
          <el-table-column prop="displayName" label="类别" />
          <el-table-column prop="count" label="像素数" width="90" />
          <el-table-column prop="ratio" label="占比" width="80">
            <template #default="{ row }">
              {{ (row.ratio * 100).toFixed(1) }}%
            </template>
          </el-table-column>
        </el-table>
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

const successfulImages = computed(() => {
  return props.result.successful_images ?? batchImages.value.length
})

const inferenceTimeText = computed(() => {
  const ms = props.result.total_inference_ms ?? props.result.inference_time_ms ?? 0
  return ms ? `${Math.round(ms)}ms` : '-'
})

const totalPixels = computed(() => {
  if (isBatch.value) {
    return Object.values(props.result.class_counts || {}).reduce((a, b) => a + b, 0)
  }
  return (props.result.image_width || 0) * (props.result.image_height || 0)
})

function previewImage(img) {
  previewSrc.value = img.src
  showFullImage.value = true
}

const classCountsArray = computed(() => {
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
</style>
