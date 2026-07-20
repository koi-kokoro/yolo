<template>
  <div class="dashboard-page">
    <!-- ── 页面标题 + 时间范围选择 ── -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">数据看板</h2>
        <p class="page-subtitle">实时监控检测任务数据与趋势分析</p>
      </div>
      <el-radio-group v-model="periodDays" size="default" @change="loadAllData">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>

    <!-- ── 数字统计卡片 ── -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon earth-primary">
            <el-icon :size="28"><Document /></el-icon>
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
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon earth-success">
            <el-icon :size="28"><PictureFilled /></el-icon>
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
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon earth-warning">
            <el-icon :size="28"><Aim /></el-icon>
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
        <el-card shadow="never" class="stat-card">
          <div class="stat-icon earth-danger">
            <el-icon :size="28"><Timer /></el-icon>
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
    <el-row :gutter="20" class="chart-row">
      <!-- 每日检测趋势（折线图） -->
      <el-col :span="16">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <span class="card-title">每日检测趋势</span>
          </template>
          <div ref="trendChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <!-- 类别分布（饼图） -->
      <el-col :span="8">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <span class="card-title">类别分布</span>
          </template>
          <div ref="classChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <!-- 场景分布（柱状图） -->
      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <span class="card-title">场景分布</span>
          </template>
          <div ref="sceneChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <!-- 任务类型分布（环形图） -->
      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <span class="card-title">任务类型分布</span>
          </template>
          <div ref="typeChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import {
    getClassDistribution,
    getSceneDistribution,
    getStatistics,
    getTrend,
    getTypeDistribution,
} from "@/api/dashboard";
import { Aim, Document, PictureFilled, Timer } from "@element-plus/icons-vue";
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref } from "vue";

const periodDays = ref(30);
const stats = ref({
  total_tasks: 0,
  total_images: 0,
  total_objects: 0,
  avg_inference_time: 0,
  growth: {},
});

const trendChartRef = ref(null);
const classChartRef = ref(null);
const sceneChartRef = ref(null);
const typeChartRef = ref(null);

let trendChart = null;
let classChart = null;
let sceneChart = null;
let typeChart = null;

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
  if (inverse) return val < 0 ? "growth-up" : "growth-down";
  return val > 0 ? "growth-up" : "growth-down";
}

async function loadAllData() {
  const days = periodDays.value;
  try {
    const [statsRes, trendRes, classRes, sceneRes, typeRes] = await Promise.all([
      getStatistics(days),
      getTrend(days),
      getClassDistribution(days),
      getSceneDistribution(days),
      getTypeDistribution(days),
    ]);

    stats.value = statsRes;
    renderTrendChart(trendRes.trend);
    renderClassChart(classRes.distribution);
    renderSceneChart(sceneRes.distribution);
    renderTypeChart(typeRes.distribution);
  } catch (err) {
    console.error("[看板数据加载失败]", err);
  }
}

function renderTrendChart(trend) {
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value);
  }

  const dates = trend.map((d) => d.date.slice(5));
  const taskCounts = trend.map((d) => d.task_count);
  const objectCounts = trend.map((d) => d.object_count);

  trendChart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      backgroundColor: "rgba(26, 22, 18, 0.95)",
      borderColor: "rgba(139, 115, 85, 0.3)",
      textStyle: { color: "#fff" },
    },
    legend: {
      data: ["检测任务", "检测目标"],
      bottom: 0,
      textStyle: { color: "rgba(255,255,255,0.7)" },
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
      axisLabel: { fontSize: 11, color: "rgba(255,255,255,0.5)" },
      axisLine: { lineStyle: { color: "rgba(255,255,255,0.1)" } },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: "value",
        name: "任务数",
        axisLabel: { fontSize: 11, color: "rgba(255,255,255,0.5)" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.1)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
        nameTextStyle: { color: "rgba(255,255,255,0.5)" },
      },
      {
        type: "value",
        name: "目标数",
        axisLabel: { fontSize: 11, color: "rgba(255,255,255,0.5)" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.1)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
        nameTextStyle: { color: "rgba(255,255,255,0.5)" },
      },
    ],
    series: [
      {
        name: "检测任务",
        type: "line",
        data: taskCounts,
        smooth: true,
        lineStyle: { width: 2, color: "#8B7355" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(139,115,85,0.3)" },
            { offset: 1, color: "rgba(139,115,85,0.02)" },
          ]),
        },
        itemStyle: { color: "#8B7355" },
      },
      {
        name: "检测目标",
        type: "line",
        yAxisIndex: 1,
        data: objectCounts,
        smooth: true,
        lineStyle: { width: 2, color: "#6B8E23" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(107,142,35,0.3)" },
            { offset: 1, color: "rgba(107,142,35,0.02)" },
          ]),
        },
        itemStyle: { color: "#6B8E23" },
      },
    ],
  });
}

function renderClassChart(distribution) {
  if (!classChart) {
    classChart = echarts.init(classChartRef.value);
  }

  classChart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} ({d}%)",
      backgroundColor: "rgba(26, 22, 18, 0.95)",
      borderColor: "rgba(139, 115, 85, 0.3)",
      textStyle: { color: "#fff" },
    },
    legend: {
      type: "scroll",
      orient: "vertical",
      right: 10,
      top: 20,
      bottom: 20,
      textStyle: { color: "rgba(255,255,255,0.7)" },
    },
    color: ["#8B7355", "#A68B67", "#6B8E23", "#DAA520", "#CD5C5C", "#A0A0A0"],
    series: [
      {
        type: "pie",
        radius: "65%",
        center: ["35%", "50%"],
        data: distribution,
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: "rgba(0,0,0,0.3)",
          },
        },
        label: {
          formatter: "{b}\n{d}%",
          fontSize: 12,
          color: "rgba(255,255,255,0.8)",
        },
      },
    ],
  });
}

function renderSceneChart(distribution) {
  if (!sceneChart) {
    sceneChart = echarts.init(sceneChartRef.value);
  }

  sceneChart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(26, 22, 18, 0.95)",
      borderColor: "rgba(139, 115, 85, 0.3)",
      textStyle: { color: "#fff" },
    },
    grid: {
      left: 80,
      right: 20,
      top: 20,
      bottom: 30,
    },
    xAxis: {
      type: "value",
      axisLabel: { fontSize: 11, color: "rgba(255,255,255,0.5)" },
      axisLine: { lineStyle: { color: "rgba(255,255,255,0.1)" } },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
    },
    yAxis: {
      type: "category",
      data: distribution.map((d) => d.name),
      axisLabel: { fontSize: 12, color: "rgba(255,255,255,0.7)" },
      axisLine: { lineStyle: { color: "rgba(255,255,255,0.1)" } },
      splitLine: { show: false },
    },
    series: [
      {
        type: "bar",
        data: distribution.map((d) => d.value),
        barWidth: "50%",
        itemStyle: {
          borderRadius: [0, 4, 4, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: "#8B7355" },
            { offset: 1, color: "#A68B67" },
          ]),
        },
        label: {
          show: true,
          position: "right",
          fontSize: 12,
          color: "rgba(255,255,255,0.8)",
        },
      },
    ],
  });
}

function renderTypeChart(distribution) {
  if (!typeChart) {
    typeChart = echarts.init(typeChartRef.value);
  }

  typeChart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} ({d}%)",
      backgroundColor: "rgba(26, 22, 18, 0.95)",
      borderColor: "rgba(139, 115, 85, 0.3)",
      textStyle: { color: "#fff" },
    },
    legend: {
      bottom: 0,
      itemGap: 16,
      textStyle: { color: "rgba(255,255,255,0.7)" },
    },
    color: ["#8B7355", "#6B8E23", "#DAA520", "#CD5C5C", "#A0A0A0"],
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
          color: "rgba(255,255,255,0.8)",
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: "bold",
            color: "#fff",
          },
        },
      },
    ],
  });
}

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
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.header-left {
  .page-title {
    margin: 0 0 4px 0;
    font-size: 24px;
    font-weight: 700;
    color: #ffffff;
  }

  .page-subtitle {
    margin: 0;
    font-size: 14px;
    color: rgba(255, 255, 255, 0.6);
  }
}

:deep(.el-radio-button) {
  .el-radio-button__inner {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.7);

    &:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(139, 115, 85, 0.3);
      color: #ffffff;
    }
  }

  &.is-active {
    .el-radio-button__inner {
      background: linear-gradient(135deg, #8B7355 0%, #A68B67 100%);
      border-color: #8B7355;
      color: #ffffff;
    }
  }
}

.stat-cards {
  margin-bottom: 20px;
}

.stat-card {
  background: rgba(35, 30, 25, 0.95);
  border: 1px solid rgba(139, 115, 85, 0.35);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);

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

  &.earth-primary {
    background: rgba(139, 115, 85, 0.15);
    color: #8B7355;
  }

  &.earth-success {
    background: rgba(107, 142, 35, 0.15);
    color: #6B8E23;
  }

  &.earth-warning {
    background: rgba(218, 165, 32, 0.15);
    color: #DAA520;
  }

  &.earth-danger {
    background: rgba(205, 92, 92, 0.15);
    color: #CD5C5C;
  }
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.2;

  .unit {
    font-size: 14px;
    font-weight: 400;
    color: rgba(255, 255, 255, 0.5);
    margin-left: 2px;
  }
}

.stat-label {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 2px;
}

.stat-growth {
  font-size: 12px;
  margin-top: 4px;

  &.growth-up {
    color: #6B8E23;
    &::before {
      content: "↑ ";
    }
  }

  &.growth-down {
    color: #CD5C5C;
    &::before {
      content: "↓ ";
    }
  }

  &.growth-flat {
    color: rgba(255, 255, 255, 0.4);
  }
}

.chart-row {
  margin-bottom: 20px;
}

.chart-card {
  background: rgba(35, 30, 25, 0.95);
  border: 1px solid rgba(139, 115, 85, 0.35);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);

  :deep(.el-card__header) {
    border-bottom: 1px solid rgba(139, 115, 85, 0.25);
    padding: 16px 20px;
  }

  :deep(.el-card__body) {
    padding: 20px;
  }
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #ffffff;
}

.chart-container {
  height: 320px;
  width: 100%;
}
</style>
