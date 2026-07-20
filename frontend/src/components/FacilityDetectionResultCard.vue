<script setup>
import { computed, ref } from 'vue'
import { Aim } from '@element-plus/icons-vue'

const props = defineProps({
  result: { type: Object, required: true },
})

const activeIndex = ref(0)
const activeImage = computed(() => props.result.images?.[activeIndex.value] || null)
</script>

<template>
  <div class="facility-result-card">
    <div class="card-header">
      <el-icon><Aim /></el-icon>
      <span>DIOR 设施检测结果</span>
      <el-tag size="small" type="warning">{{ result.total_objects || 0 }} 个目标</el-tag>
    </div>
    <div class="card-body">
      <el-tabs v-if="(result.images?.length || 0) > 1" v-model="activeIndex" type="card">
        <el-tab-pane
          v-for="(image, index) in result.images"
          :key="`${image.filename}-${index}`"
          :label="`${image.filename} (${image.total_objects || 0})`"
          :name="index"
        />
      </el-tabs>
      <div v-if="activeImage" class="result-layout">
        <div class="result-image">
          <img
            v-if="activeImage.annotated_image_url"
            :src="activeImage.annotated_image_url"
            :alt="`${activeImage.filename} DIOR 检测结果`"
          >
          <div v-else class="image-unavailable">标注图不可用，请重新检测</div>
          <div class="image-meta">
            {{ activeImage.filename }} · {{ activeImage.width }}×{{ activeImage.height }} ·
            {{ activeImage.inference_time_ms || 0 }} ms
          </div>
        </div>
        <el-table
          :data="activeImage.detections || []"
          size="small"
          max-height="360"
          empty-text="当前阈值下未检测到设施目标"
        >
          <el-table-column prop="class_name_cn" label="类别" min-width="90" />
          <el-table-column label="置信度" width="90">
            <template #default="{ row }">{{ ((row.confidence || 0) * 100).toFixed(1) }}%</template>
          </el-table-column>
          <el-table-column label="边界框" min-width="185">
            <template #default="{ row }">
              {{ row.bbox?.x1 }}, {{ row.bbox?.y1 }}, {{ row.bbox?.x2 }}, {{ row.bbox?.y2 }}
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="class-summary">
        <el-tag
          v-for="item in result.class_statistics || []"
          :key="item.class_name"
          size="small"
          effect="plain"
        >
          {{ item.class_name_cn || item.class_name }} × {{ item.count }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.facility-result-card { margin-top: 12px; overflow: hidden; border: 1px solid #f3d19e; border-radius: 8px; background: #fff; }
.card-header { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid #f3d19e; background: #fdf6ec; font-weight: 600; }
.card-header .el-tag { margin-left: auto; }
.card-body { padding: 14px; }
.result-layout { display: grid; grid-template-columns: minmax(300px, .9fr) minmax(350px, 1.1fr); gap: 14px; }
.result-image img { display: block; width: 100%; max-height: 380px; object-fit: contain; border-radius: 5px; background: #f5f7fa; }
.image-unavailable { display: grid; min-height: 180px; place-items: center; color: #909399; background: #f5f7fa; }
.image-meta { margin-top: 8px; color: #606266; font-size: 12px; text-align: center; }
.class-summary { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
@media (max-width: 900px) { .result-layout { grid-template-columns: 1fr; } }
</style>
