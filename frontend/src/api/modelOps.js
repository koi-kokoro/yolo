import request from '@/utils/request'

export function evaluateSemanticModel(data = {}) {
  return request({
    url: '/semantic-models/evaluate',
    method: 'post',
    data,
    timeout: 600000, // Evaluation can take several minutes on CPU.
  })
}

export function exportSemanticModel(data = {}) {
  return request({
    url: '/semantic-models/export',
    method: 'post',
    data,
  })
}

export function listSemanticModelVersions() {
  return request({
    url: '/semantic-models/versions',
    method: 'get',
  })
}

export function downloadSemanticModel(versionId) {
  return `/api/semantic-models/download/${versionId}`
}

export function predictSemanticImage(formData) {
  return request({
    url: '/semantic-models/predict',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}
