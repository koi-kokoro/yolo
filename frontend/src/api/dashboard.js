/**
 * 数据看板 API 接口
 * 提供统计汇总、趋势、分布等数据查询
 */
import request from "@/utils/request";

/**
 * 获取汇总统计
 * @param {number} days - 统计最近 N 天（默认 30）
 * @returns {Promise} - { total_tasks, total_images, total_objects, avg_inference_time, growth }
 */
export function getStatistics(days = 30) {
  return request.get("/dashboard/statistics", { params: { days } });
}

/**
 * 获取每日检测趋势
 * @param {number} days - 统计最近 N 天（默认 30）
 * @returns {Promise} - { trend: [{ date, task_count, object_count, image_count }] }
 */
export function getTrend(days = 30) {
  return request.get("/dashboard/trend", { params: { days } });
}

/**
 * 获取类别分布
 * @param {number} days - 统计最近 N 天
 * @returns {Promise} - { distribution: [{ name, value }] }
 */
export function getClassDistribution(days = 30) {
  return request.get("/dashboard/class-dist", { params: { days } });
}

/**
 * 获取场景分布
 * @param {number} days - 统计最近 N 天
 * @returns {Promise} - { distribution: [{ name, value }] }
 */
export function getSceneDistribution(days = 30) {
  return request.get("/dashboard/scene-dist", { params: { days } });
}

/** 获取现有语义 Mask 派生的异常度—参考可信度矩阵。 */
export function getSemanticRiskMatrix(days = 30) {
  return request.get("/dashboard/semantic-risk-matrix", { params: { days } });
}

/** 获取输入域健康度（域内/临界/域外）。 */
export function getDomainHealth(days = 30) {
  return request.get("/dashboard/domain-health", { params: { days } });
}

/**
 * 获取任务类型分布
 * @param {number} days - 统计最近 N 天
 * @returns {Promise} - { distribution: [{ name, value }] }
 */
export function getTypeDistribution(days = 30) {
  return request.get("/dashboard/type-dist", { params: { days } });
}
