import request from '@/utils/request'

export function createSemanticTask(formData) {
  return request({
    url: '/semantic-tasks',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getSemanticTask(taskUuid) {
  return request({
    url: `/semantic-tasks/${taskUuid}`,
    method: 'get',
  })
}

export function listSemanticTasks(params = {}) {
  return request({
    url: '/semantic-tasks',
    method: 'get',
    params,
  })
}

export function getSemanticModelInfo() {
  return request({
    url: '/semantic-tasks/model-info',
    method: 'get',
  })
}
