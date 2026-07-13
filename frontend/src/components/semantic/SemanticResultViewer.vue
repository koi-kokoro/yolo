<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ task: { type: Object, default: null } })
const active = ref('overlay')
const images = computed(() => {
  const result = props.task?.result
  return [
    { key: 'source', label: '原图', url: props.task?.source_url },
    { key: 'index', label: '索引 Mask', url: result?.index_mask_url },
    { key: 'color', label: '彩色 Mask', url: result?.color_mask_url },
    { key: 'overlay', label: '叠加图', url: result?.overlay_url },
  ].filter((item) => item.url)
})
const current = computed(() => images.value.find((item) => item.key === active.value) || images.value[0])
watch(images, (items) => { if (items.length && !items.some((item) => item.key === active.value)) active.value = items[0].key }, { immediate: true })
</script>

<template>
  <div class="result-viewer">
    <el-empty v-if="!task" description="创建或选择任务后查看结果" />
    <div v-else-if="['pending', 'running'].includes(task.status)" class="result-viewer__state">
      <el-icon class="is-loading" size="30"><Loading /></el-icon>
      <p>{{ task.status === 'pending' ? '任务排队中' : '模型推理中' }}，请稍候…</p>
    </div>
    <el-result v-else-if="task.status === 'failed'" icon="error" title="分割失败" :sub-title="task.error?.message || '任务执行失败'" />
    <template v-else-if="task.status === 'succeeded' && current">
      <el-segmented v-model="active" :options="images.map(({ key, label }) => ({ value: key, label }))" />
      <div class="result-viewer__canvas"><el-image :src="current.url" :preview-src-list="images.map((item) => item.url)" fit="contain" /></div>
      <div class="result-viewer__links"><a v-for="item in images" :key="item.key" :href="item.url" target="_blank" rel="noopener">打开{{ item.label }}</a></div>
    </template>
  </div>
</template>

<script>
import { Loading } from '@element-plus/icons-vue'
export default { components: { Loading } }
</script>

<style scoped>
.result-viewer__state { padding: 100px 20px; text-align: center; color: #606266; }
.result-viewer__canvas { display: grid; place-items: center; min-height: 420px; margin-top: 16px; border-radius: 8px; background: #f5f7fa; overflow: hidden; }
.result-viewer__canvas :deep(.el-image) { width: 100%; height: 500px; }
.result-viewer__links { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; }
.result-viewer__links a { color: #409eff; text-decoration: none; }
</style>
