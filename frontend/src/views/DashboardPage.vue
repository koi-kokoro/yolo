<template>
  <div class="dashboard-page">
    <!-- ── 页面标题 + 时间范围选择 ── -->
    <div class="page-header">
      <h2>数据看板</h2>
      <el-radio-group v-model="periodDays" size="default" @change="loadAllData">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>

    <!-- ── 数字统计卡片 ── -->
    <el-row :gutter="16" class="stat-cards">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #ecf5ff">
            <el-icon :size="28" color="#409eff"><Document /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_tasks }}</div>
            <div class="stat-label">检测任务</div>
            <div class="stat-growth" :class="growthClass('tasks')">
              {{ formatGrowth(stats.growth?.tasks) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #f0f9eb">
            <el-icon :size="28" color="#67c23a"><PictureFilled /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ formatNumber(stats.total_images) }}</div>
            <div class="stat-label">处理图片</div>
            <div class="stat-growth" :class="growthClass('images')">
              {{ formatGrowth(stats.growth?.images) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #fdf6ec">
            <el-icon :size="28" color="#e6a23c"><Aim /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ formatNumber(stats.total_objects) }}</div>
            <div class="stat-label">检测目标</div>
            <div class="stat-growth" :class="growthClass('objects')">
              {{ formatGrowth(stats.growth?.objects) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #fef0f0">
            <el-icon :size="28" color="#f56c6c"><Timer /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.avg_inference_time }}<span class="unit">ms</span></div>
            <div class="stat-label">平均耗时</div>
            <div class="stat-growth" :class="growthClass('inference_time', true)">
              {{ formatGrowth(stats.growth?.inference_time) }}
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ── 图表区域 ── -->
    <el-row :gutter="16" class="chart-row">
      <!-- 每日检测趋势（折线图） -->
      <el-col :span="16">
        <el-card shadow="hover">
          <template #header>
            <span>每日检测趋势</span>
          </template>
          <div ref="trendChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <!-- 语义异常度—参考可信度矩阵 -->
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div class="chart-title">
              <span>异常度—参考可信度</span>
              <el-tooltip content="由语义 Mask、LoveDA 类别先验和验证集 IoU 派生，并非模型置信度">
                <el-icon class="chart-help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <div ref="classChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <!-- 输入域健康度 -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="chart-title">
              <span>输入域健康度</span>
              <el-tooltip content="按语义类别结构与 LoveDA 训练先验的距离划分域内、临界和域外">
                <el-icon class="chart-help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <div ref="sceneChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <!-- 任务类型分布（环形图） -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>任务类型分布</span>
          </template>
          <div ref="typeChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
/**
 * DashboardPage.vue — 数据看板
 *
 * 功能：
 *   - 数字统计卡片（带环比增长率）
 *   - ECharts 折线图：每日检测趋势
 *   - ECharts 饼图：类别分布
 *   - ECharts 柱状图：场景分布
 *   - ECharts 环形图：任务类型分布
 */
import {
  getDomainHealth,
  getSemanticRiskMatrix,
  getStatistics,
  getTrend,
  getTypeDistribution,
} from "@/api/dashboard";
import { Aim, Document, PictureFilled, QuestionFilled, Timer } from "@element-plus/icons-vue";
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref } from "vue";

// ── 响应式状态 ──
const periodDays = ref(30);
const stats = ref({
  total_tasks: 0,
  total_images: 0,
  total_objects: 0,
  avg_inference_time: 0,
  growth: {},
});

// ── 图表 DOM 引用 ──
const trendChartRef = ref(null);
const classChartRef = ref(null);
const sceneChartRef = ref(null);
const typeChartRef = ref(null);

// ── 图表实例（用于销毁） ──
let trendChart = null;
let classChart = null;
let sceneChart = null;
let typeChart = null;

// ── 格式化函数 ──
function formatNumber(num) {
  if (!num) return "0";
  if (num >= 10000) return (num / 10000).toFixed(1) + "w";
  if (num >= 1000) return (num / 1000).toFixed(1) + "k";
  return String(num);
}

function formatGrowth(value) {
  if (value === undefined || value === null) return "";
  if (value > 0) return `+${value}%`;
  if (value < 0) return `${value}%`;
  return "持平";
}

function growthClass(key, inverse = false) {
  const val = stats.value.growth?.[key];
  if (val === undefined || val === null || val === 0) return "growth-flat";
  // inverse=true 时，下降是好事（推理耗时越短越好）
  if (inverse) return val < 0 ? "growth-up" : "growth-down";
  return val > 0 ? "growth-up" : "growth-down";
}

// ── 加载所有数据 ──
async function loadAllData() {
  const days = periodDays.value;
  try {
    // 并行请求所有 API
    const [statsRes, trendRes, classRes, sceneRes, typeRes] = await Promise.all([
      getStatistics(days),
      getTrend(days),
      getSemanticRiskMatrix(days),
      getDomainHealth(days),
      getTypeDistribution(days),
    ]);

    stats.value = statsRes;
    renderTrendChart(trendRes.trend);
    renderClassChart(classRes.points);
    renderSceneChart(sceneRes.distribution);
    renderTypeChart(typeRes.distribution);
  } catch (err) {
    console.error("[看板数据加载失败]", err);
  }
}

// ── 渲染折线图：每日检测趋势 ──
function renderTrendChart(trend) {
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value);
  }

  const dates = trend.map((d) => d.date.slice(5)); // "MM-DD"
  const taskCounts = trend.map((d) => d.task_count);
  const objectCounts = trend.map((d) => d.object_count);

  trendChart.setOption({
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
    },
    legend: {
      data: ["检测任务", "检测目标"],
      bottom: 0,
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 40,
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { fontSize: 11 },
    },
    yAxis: [
      {
        type: "value",
        name: "任务数",
        axisLabel: { fontSize: 11 },
      },
      {
        type: "value",
        name: "目标数",
        axisLabel: { fontSize: 11 },
      },
    ],
    series: [
      {
        name: "检测任务",
        type: "line",
        data: taskCounts,
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(64,158,255,0.3)" },
            { offset: 1, color: "rgba(64,158,255,0.02)" },
          ]),
        },
        itemStyle: { color: "#409eff" },
      },
      {
        name: "检测目标",
        type: "line",
        yAxisIndex: 1,
        data: objectCounts,
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(103,194,58,0.3)" },
            { offset: 1, color: "rgba(103,194,58,0.02)" },
          ]),
        },
        itemStyle: { color: "#67c23a" },
      },
    ],
  });
}

// ── 渲染饼图：类别分布 ──
function renderClassChart(points = []) {
  if (!classChart) {
    classChart = echarts.init(classChartRef.value);
  }

  if (!points.length) {
    classChart.clear();
    classChart.setOption(emptyChartOption("暂无语义评估数据\n完成新的语义分割任务后自动生成"));
    return;
  }

  const reviewColors = {
    low: "#67c23a",
    medium: "#e6a23c",
    high: "#f56c6c",
  };
  const data = points.map((point) => ({
    name: point.name,
    value: [point.anomaly_score, point.reliability_score, point.total_pixels],
    taskId: point.task_id,
    taskType: point.task_type,
    reviewLevel: point.review_level,
    domainStatus: point.domain_status,
    itemStyle: { color: reviewColors[point.review_level] || "#909399" },
  }));

  classChart.clear();
  classChart.setOption({
    tooltip: {
      trigger: "item",
      formatter(params) {
        const value = params.value || [];
        const levelNames = { low: "低", medium: "中", high: "高" };
        return [
          `<strong>${params.name}</strong>`,
          `任务 #${params.data.taskId}`,
          `异常度：${value[0]}`,
          `参考可信度：${value[1]}`,
          `复核优先级：${levelNames[params.data.reviewLevel] || "未知"}`,
        ].join("<br/>");
      },
    },
    grid: {
      left: 50,
      right: 20,
      top: 28,
      bottom: 45,
    },
    xAxis: {
      type: "value",
      name: "异常度",
      min: 0,
      max: 100,
      axisLabel: { formatter: "{value}" },
    },
    yAxis: {
      type: "value",
      name: "参考可信度",
      min: 0,
      max: 100,
    },
    series: [
      {
        type: "scatter",
        data,
        symbolSize(value) {
          const pixels = Math.max(1, Number(value[2]) || 1);
          return Math.max(10, Math.min(28, 8 + Math.log10(pixels)));
        },
        emphasis: {
          scale: 1.35,
        },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", color: "#c0c4cc" },
          label: { color: "#909399", fontSize: 10 },
          data: [
            { xAxis: 25, name: "临界" },
            { xAxis: 45, name: "域外" },
            { yAxis: 50, name: "建议复核" },
          ],
        },
      },
    ],
  });
}

// ── 渲染柱状图：场景分布 ──
function renderSceneChart(distribution = []) {
  if (!sceneChart) {
    sceneChart = echarts.init(sceneChartRef.value);
  }

  const validData = distribution.filter((item) => Number(item.value) > 0);
  if (!validData.length) {
    sceneChart.clear();
    sceneChart.setOption(emptyChartOption("暂无输入域评估数据"));
    return;
  }

  const colors = ["#67c23a", "#e6a23c", "#f56c6c"];
  sceneChart.clear();
  sceneChart.setOption({
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} 个样本 ({d}%)",
    },
    legend: { bottom: 0, itemGap: 24 },
    color: colors,
    series: [
      {
        type: "pie",
        radius: ["42%", "68%"],
        center: ["50%", "45%"],
        data: validData,
        label: { formatter: "{b}\n{c} ({d}%)", fontSize: 12 },
      },
    ],
  });
}

function emptyChartOption(message) {
  return {
    graphic: {
      type: "text",
      left: "center",
      top: "middle",
      style: {
        text: message,
        textAlign: "center",
        fill: "#909399",
        fontSize: 14,
        lineHeight: 22,
      },
    },
  };
}

// ── 渲染环形图：任务类型分布 ──
function renderTypeChart(distribution) {
  if (!typeChart) {
    typeChart = echarts.init(typeChartRef.value);
  }

  const colors = ["#409eff", "#67c23a", "#e6a23c", "#f56c6c", "#909399"];

  typeChart.setOption({
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} ({d}%)",
    },
    legend: {
      bottom: 0,
      itemGap: 16,
    },
    color: colors,
    series: [
      {
        type: "pie",
        radius: ["40%", "65%"],
        center: ["50%", "45%"],
        avoidLabelOverlap: false,
        data: distribution,
        label: {
          show: true,
          formatter: "{b}\n{d}%",
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: "bold",
          },
        },
      },
    ],
  });
}

// ── 窗口 resize 时自动调整图表 ──
function handleResize() {
  trendChart?.resize();
  classChart?.resize();
  sceneChart?.resize();
  typeChart?.resize();
}

onMounted(() => {
  loadAllData();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  trendChart?.dispose();
  classChart?.dispose();
  sceneChart?.dispose();
  typeChart?.dispose();
});
</script>

<style lang="scss" scoped>
.dashboard-page {
  padding: 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;

  h2 {
    margin: 0;
  }
}

/* 统计卡片 */
.stat-cards {
  margin-bottom: 16px;
}

.stat-card {
  :deep(.el-card__body) {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
  }
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;

  .unit {
    font-size: 14px;
    font-weight: 400;
    color: #909399;
    margin-left: 2px;
  }
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}

.stat-growth {
  font-size: 12px;
  margin-top: 4px;

  &.growth-up {
    color: #67c23a;
    &::before {
      content: "↑ ";
    }
  }

  &.growth-down {
    color: #f56c6c;
    &::before {
      content: "↓ ";
    }
  }

  &.growth-flat {
    color: #909399;
  }
}

/* 图表区域 */
.chart-row {
  margin-bottom: 16px;
}

.chart-container {
  height: 320px;
  width: 100%;
}

.chart-title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.chart-help {
  color: #909399;
  cursor: help;
}
</style>
