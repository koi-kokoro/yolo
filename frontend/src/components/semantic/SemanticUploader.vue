<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const props = defineProps({
  disabled: Boolean,
  loading: Boolean,
})
const emit = defineEmits(['submit'])

const file = ref(null)
const previewUrl = ref('')
const uploadRef = ref()
const acceptedTypes = new Set(['image/jpeg', 'image/png'])
const maxBytes = 20 * 1024 * 1024

const fileLabel = computed(() => file.value ? `${file.value.name} · ${(file.value.size / 1024 / 1024).toFixed(2)} MiB` : '')

function revokePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

function validate(candidate) {
  if (!acceptedTypes.has(candidate.type) || !/\.(jpe?g|png)$/i.test(candidate.name)) {
    ElMessage.warning('仅支持 JPEG 或 PNG 图片')
    return false
  }
  if (candidate.size > maxBytes) {
    ElMessage.warning('图片不能超过 20 MiB')
    return false
  }
  return true
}

function selectFile(uploadFile) {
  const candidate = uploadFile.raw
  if (!validate(candidate)) {
    uploadRef.value?.clearFiles()
    return
  }
  revokePreview()
  file.value = candidate
  previewUrl.value = URL.createObjectURL(candidate)
}

function clear() {
  file.value = null
  revokePreview()
  uploadRef.value?.clearFiles()
}

function submit() {
  if (file.value && !props.disabled && !props.loading) emit('submit', file.value)
}

defineExpose({ clear })
onBeforeUnmount(revokePreview)
</script>

<template>
  <div class="semantic-uploader">
    <el-upload
      ref="uploadRef"
      drag
      :auto-upload="false"
      :show-file-list="false"
      :limit="1"
      accept=".jpg,.jpeg,.png,image/jpeg,image/png"
      :disabled="disabled || loading"
      :on-change="selectFile"
    >
      <img v-if="previewUrl" :src="previewUrl" alt="待上传遥感图预览" class="semantic-uploader__preview">
      <template v-else>
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽遥感图到此处，或<em>点击选择</em></div>
        <div class="semantic-uploader__tip">单张 JPEG/PNG，最大 20 MiB</div>
      </template>
    </el-upload>
    <div v-if="file" class="semantic-uploader__actions">
      <span>{{ fileLabel }}</span>
      <div>
        <el-button :disabled="loading" @click="clear">重新选择</el-button>
        <el-button type="primary" :loading="loading" :disabled="disabled" @click="submit">创建语义分割任务</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.semantic-uploader {
  :deep(.el-upload) {
    width: 100%;
  }

  :deep(.el-upload-dragger) {
    width: 100%;
    padding: 30px 18px;
  }

  :deep(.el-icon--upload) {
    color: $primary-color;
  }
}

.semantic-uploader__preview {
  display: block;
  width: 100%;
  height: 280px;
  object-fit: contain;
  border-radius: 10px;
  background: rgba(78, 103, 138, 0.05);
}

.semantic-uploader__tip {
  margin-top: 8px;
  color: $text-secondary;
  font-size: 13px;
}

.semantic-uploader__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 14px;
  padding: 12px;
  color: $text-regular;
  background: rgba(78, 103, 138, 0.05);
  border: 1px solid rgba(78, 103, 138, 0.1);
  border-radius: 10px;
}

.semantic-uploader__actions > span {
  min-width: 0;
  overflow: hidden;
  color: $text-secondary;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 700px) {
  .semantic-uploader__actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .semantic-uploader__actions > div {
    display: flex;
    width: 100%;
    gap: 8px;
  }

  .semantic-uploader__actions :deep(.el-button) {
    flex: 1;
    margin-left: 0;
  }
}
</style>
