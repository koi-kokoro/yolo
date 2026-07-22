/**
 * Image analysis API wrappers used by the chat shortcut buttons.
 *
 * Shortcut buttons call these endpoints directly (bypassing the LLM agent)
 * for zero-latency inference.
 */
import request from '@/utils/request'

/**
 * Segment a single image.
 * @param {FormData} formData - contains a single `file` field
 * @returns {Promise<object>} segmentation result card payload
 */
export function segmentSingle(formData) {
  return request.post('/segmentation/single', formData, {
    timeout: 120000,
  })
}

/**
 * Run LoveDA segmentation and DIOR facility detection on multiple images.
 * @param {FormData} formData - contains multiple `files` fields
 * @returns {Promise<object>} semantic result plus optional `facility_detection`
 */
export function segmentBatch(formData) {
  return request.post('/segmentation/batch', formData, {
    timeout: 180000,
  })
}

/**
 * Segment all images inside a ZIP archive.
 * @param {FormData} formData - contains a single `file` field (the ZIP)
 * @returns {Promise<object>} ZIP segmentation result card payload
 */
export function segmentZip(formData) {
  return request.post('/segmentation/zip', formData, {
    timeout: 300000,
  })
}

/**
 * Segment a video by sampling key frames.
 * @param {FormData} formData - contains a single `file` field
 * @returns {Promise<object>} video segmentation result payload
 */
export function segmentVideo(formData) {
  return request.post('/segmentation/video', formData, {
    timeout: 300000,
  })
}
