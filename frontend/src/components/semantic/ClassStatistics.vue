<script setup>
import { computed } from 'vue'

const props = defineProps({ statistics: { type: Array, default: () => [] } })
const sorted = computed(() => [...props.statistics].sort((a, b) => a.class_id - b.class_id))
const formatPercent = (ratio) => `${(Number(ratio || 0) * 100).toFixed(2)}%`
const formatPixels = (count) => Number(count || 0).toLocaleString('zh-CN')
const color = (rgb) => `rgb(${(rgb || [0, 0, 0]).join(',')})`
</script>

<template>
  <el-table :data="sorted" stripe class="class-statistics">
    <el-table-column label="图例" width="72">
      <template #default="{ row }"><span class="swatch" :style="{ backgroundColor: color(row.rgb) }" /></template>
    </el-table-column>
    <el-table-column prop="class_id" label="ID" width="64" />
    <el-table-column label="类别" min-width="130">
      <template #default="{ row }">{{ row.display_name || row.name }} <small>{{ row.name }}</small></template>
    </el-table-column>
    <el-table-column label="像素数" min-width="120" align="right">
      <template #default="{ row }">{{ formatPixels(row.pixel_count) }}</template>
    </el-table-column>
    <el-table-column label="占比" min-width="210">
      <template #default="{ row }"><el-progress :percentage="Number((row.ratio * 100).toFixed(2))" :stroke-width="12" :color="color(row.rgb)"><span>{{ formatPercent(row.ratio) }}</span></el-progress></template>
    </el-table-column>
  </el-table>
</template>

<style scoped lang="scss">
.swatch { display: inline-block; width: 24px; height: 16px; border: 1px solid rgba(78, 103, 138, 0.24); border-radius: 3px; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.55); }
small { margin-left: 5px; color: $text-secondary; }
</style>
