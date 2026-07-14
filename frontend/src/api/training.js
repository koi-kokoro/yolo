import request from '@/utils/request'

const ARTIFACT_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

function taskPath(taskId) {
  const id = Number(taskId)
  if (!Number.isInteger(id) || id <= 0) throw new TypeError('训练任务 ID 无效')
  return `/training/tasks/${id}`
}

export function createTrainingTask(data) {
  return request({ url: '/training/tasks', method: 'post', data })
}

export function listTrainingTasks() {
  return request({ url: '/training/tasks', method: 'get' })
}

export function getTrainingTask(taskId) {
  return request({ url: taskPath(taskId), method: 'get' })
}

export function getTrainingMetrics(taskId, afterEpoch = 0) {
  const epoch = Math.max(0, Number.parseInt(afterEpoch, 10) || 0)
  return request({
    url: `${taskPath(taskId)}/metrics`,
    method: 'get',
    params: { after_epoch: epoch },
  })
}

export function stopTrainingTask(taskId) {
  return request({ url: `${taskPath(taskId)}/stop`, method: 'post' })
}

export function downloadTrainingArtifact(taskId, artifactName) {
  if (typeof artifactName !== 'string' || !ARTIFACT_NAME_PATTERN.test(artifactName)) {
    throw new TypeError('训练产物名称无效')
  }
  return request({
    url: `${taskPath(taskId)}/artifacts/${encodeURIComponent(artifactName)}`,
    method: 'get',
    responseType: 'blob',
  })
}
