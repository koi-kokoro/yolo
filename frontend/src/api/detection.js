import request from '@/utils/request'

export const getDetectionModelInfo = () => request.get('/detection/model-info')

export const detectSingle = (formData, params = {}) => request.post(
  '/detection/single',
  formData,
  { params, headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 },
)

export const detectBatch = (formData, params = {}) => request.post(
  '/detection/batch',
  formData,
  { params, headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 },
)

export const detectVideo = (formData) => request.post(
  '/detection/video',
  formData,
  { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 },
)

