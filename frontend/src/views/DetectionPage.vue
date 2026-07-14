<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'

import ClassStatistics from '@/components/semantic/ClassStatistics.vue'
import SemanticResultViewer from '@/components/semantic/SemanticResultViewer.vue'
import SemanticUploader from '@/components/semantic/SemanticUploader.vue'
import { useSemanticStore } from '@/stores/semantic'
import { formatInputSize, resolveRuntimeModelIdentity } from '@/utils/semanticModelIdentity'

const store = useSemanticStore()
const { modelInfo, currentTask, history, uploading, loadingHistory, error, canSubmit } = storeToRefs(store)
const uploader = ref()

const statusMap = {
  pending: { label: '排队中', type: 'warning' },
  running: { label: '推理中', type: 'primary' },
  succeeded: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}
const taskStatus = computed(() => statusMap[currentTask.value?.status] || { label: '未创建', type: 'info' })
const metadata = computed(() => currentTask.value?.result?.inference_metadata || {})
const actualModel = computed(() => resolveRuntimeModelIdentity({
  inferenceMetadata: metadata.value,
  runtimeInfo: modelInfo.value,
}))
const legend = computed(() => modelInfo.value?.classes || currentTask.value?.result?.class_statistics || [])

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}

async function submit(file) {
  try {
    await store.createTask(file)
    ElMessage.success('任务已创建，正在等待推理')
  } catch {}
}

async function openTask(row) {
  try { await store.openTask(row.task_uuid) } catch {}
}

async function refreshSignedUrls() {
  try {
    await store.refreshCurrentTask()
    ElMessage.success('结果链接已刷新')
  } catch {}
}

function resetTask() {
  store.clearCurrentTask()
  uploader.value?.clear()
}

onMounted(() => {
  store.fetchModelInfo().catch(() => {})
  store.fetchHistory().catch(() => {})
})
onBeforeUnmount(() => store.dispose())
</script>

<template>
  <section class="semantic-page">
    <div class="semantic-page__heading">
      <div><h1>土地覆盖语义分割</h1><p>上传单张遥感图，生成索引 Mask、彩色 Mask、叠加图及 LoveDA 7 类像素统计。</p></div>
      <el-tag v-if="modelInfo" :type="modelInfo.ready ? 'success' : 'danger'" size="large">模型{{ modelInfo.ready ? '已就绪' : '不可用' }}</el-tag>
    </div>

    <el-alert v-if="modelInfo && !modelInfo.ready" type="error" :closable="false" show-icon :title="modelInfo.message || '语义分割模型暂不可用，请联系管理员检查部署配置。'" />
    <el-alert v-if="error" type="warning" :closable="false" show-icon :title="error" class="semantic-page__alert" />

    <div class="semantic-page__grid">
      <el-card shadow="never">
        <template #header><div class="card-title"><span>创建任务</span><el-button v-if="currentTask" link type="primary" @click="resetTask">新建任务</el-button></div></template>
        <SemanticUploader ref="uploader" :disabled="!canSubmit" :loading="uploading" @submit="submit" />
        <el-descriptions v-if="modelInfo" :column="2" border class="model-info">
          <el-descriptions-item label="实际推理模型">{{ actualModel.modelName }}</el-descriptions-item>
          <el-descriptions-item label="实际推理版本">{{ actualModel.modelVersion }}</el-descriptions-item>
          <el-descriptions-item label="引擎">{{ actualModel.engine }}</el-descriptions-item>
          <el-descriptions-item label="Provider">{{ actualModel.provider }}</el-descriptions-item>
          <el-descriptions-item label="输入尺寸">{{ formatInputSize(actualModel.inputSize) }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="legend.length" class="legend"><span v-for="item in legend" :key="item.class_id ?? item.id"><i :style="{ background: `rgb(${item.rgb.join(',')})` }" />{{ item.display_name || item.name }}</span></div>
      </el-card>

      <el-card shadow="never">
        <template #header><div class="card-title"><span>当前任务</span><el-tag :type="taskStatus.type">{{ taskStatus.label }}</el-tag></div></template>
        <el-empty v-if="!currentTask" description="尚未创建或选择任务" />
        <template v-else>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="文件名">{{ currentTask.original_filename }}</el-descriptions-item>
            <el-descriptions-item label="任务关联记录">{{ currentTask.model_version?.version || '—' }}</el-descriptions-item>
            <el-descriptions-item label="实际推理版本">{{ actualModel.modelVersion }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDate(currentTask.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ formatDate(currentTask.completed_at) }}</el-descriptions-item>
          </el-descriptions>
          <el-button v-if="currentTask.status === 'succeeded'" class="refresh-button" @click="refreshSignedUrls">刷新签名 URL</el-button>
        </template>
      </el-card>
    </div>

    <el-card shadow="never" class="semantic-page__section">
      <template #header><span>分割结果</span></template>
      <SemanticResultViewer :task="currentTask" />
    </el-card>

    <div v-if="currentTask?.status === 'succeeded'" class="semantic-page__grid semantic-page__section">
      <el-card shadow="never">
        <template #header><span>类别统计</span></template>
        <ClassStatistics :statistics="currentTask.result?.class_statistics" />
      </el-card>
      <el-card shadow="never">
        <template #header><span>推理元数据</span></template>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="推理耗时">{{ currentTask.result?.inference_time_ms }} ms</el-descriptions-item>
          <el-descriptions-item label="总耗时">{{ currentTask.result?.total_time_ms }} ms</el-descriptions-item>
          <el-descriptions-item label="实际推理模型">{{ actualModel.modelName }}</el-descriptions-item>
          <el-descriptions-item label="实际推理版本">{{ actualModel.modelVersion }}</el-descriptions-item>
          <el-descriptions-item label="实际引擎">{{ actualModel.engine }}</el-descriptions-item>
          <el-descriptions-item label="Provider / Device">{{ actualModel.provider }}</el-descriptions-item>
          <el-descriptions-item label="源尺寸">{{ formatInputSize(metadata.source_size) }}</el-descriptions-item>
          <el-descriptions-item label="输入尺寸">{{ formatInputSize(actualModel.inputSize) }}</el-descriptions-item>
          <el-descriptions-item label="缩放模式">{{ metadata.resize_mode || '—' }}</el-descriptions-item>
          <el-descriptions-item label="运行时版本">{{ metadata.runtime_version || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
    </div>

    <el-card shadow="never" class="semantic-page__section">
      <template #header><div class="card-title"><span>最近任务</span><el-button link type="primary" :loading="loadingHistory" @click="store.fetchHistory()">刷新</el-button></div></template>
      <el-table :data="history" v-loading="loadingHistory" @row-click="openTask">
        <el-table-column prop="original_filename" label="文件名" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusMap[row.status]?.type">{{ statusMap[row.status]?.label || row.status }}</el-tag></template></el-table-column>
        <el-table-column label="尺寸" width="130"><template #default="{ row }">{{ row.image_width }} × {{ row.image_height }}</template></el-table-column>
        <el-table-column label="总耗时" width="110"><template #default="{ row }">{{ row.total_time_ms ? `${row.total_time_ms} ms` : '—' }}</template></el-table-column>
        <el-table-column label="创建时间" min-width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<style scoped lang="scss">
.semantic-page { display: flex; flex-direction: column; gap: 16px; }
.semantic-page__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
h1 { margin: 0 0 8px; font-size: 26px; color: #303133; } p { margin: 0; color: #606266; }
.semantic-page__grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(340px, .8fr); gap: 16px; }
.semantic-page__section { margin-top: 0; }
.semantic-page__alert { margin-top: -6px; }
.card-title { display: flex; align-items: center; justify-content: space-between; }
.model-info { margin-top: 18px; }
.legend { display: flex; flex-wrap: wrap; gap: 12px 18px; margin-top: 16px; color: #606266; font-size: 13px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }.legend i { width: 14px; height: 14px; border: 1px solid #dcdfe6; border-radius: 3px; }
.refresh-button { margin-top: 14px; }
:deep(.el-table__row) { cursor: pointer; }
@media (max-width: 1000px) { .semantic-page__grid { grid-template-columns: 1fr; } }
</style>
