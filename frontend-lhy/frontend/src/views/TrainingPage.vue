<template>
  <div class="training-page">
    <!-- ── 页面标题 ── -->
    <div class="page-header">
      <div>
        <h2 class="page-title">模型训练与监控</h2>
        <p class="page-subtitle">管理您的检测模型训练任务，实时查看指标曲线</p>
      </div>
      <el-button type="primary" round size="large" class="create-btn" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon> 新建训练任务
      </el-button>
    </div>

    <!-- ── 训练任务列表 ── -->
    <el-card class="custom-card task-list-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="card-title">训练任务列表</span>
          <el-button text bg type="primary" size="small" @click="fetchTasks" round>
            <el-icon><Refresh /></el-icon> 刷新状态
          </el-button>
        </div>
      </template>

      <el-table
        :data="taskList"
        style="width: 100%"
        v-loading="loadingTasks"
      >
        <el-table-column prop="task_uuid" label="任务 ID" />
        <el-table-column prop="model_name" label="模型">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" type="info">{{ row.model_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="device" label="设备" />
        <el-table-column label="进度">
          <template #default="{ row }">
            <div class="progress-wrapper">
              <el-progress
                :percentage="row.progress"
                :status="
                  row.status === 'completed'
                    ? 'success'
                    : row.status === 'failed'
                      ? 'exception'
                      : ''
                "
                :stroke-width="10"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Epoch" align="center">
          <template #default="{ row }">
            <span class="epoch-text">{{ row.current_epoch }} / {{ row.epochs }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="light" round>
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" />
        <el-table-column label="操作" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              link
              @click="selectTask(row)"
            >
              实时监控
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              size="small"
              type="danger"
              link
              @click="stopTask(row.id)"
            >
              停止
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ── 训练监控面板 ── -->
    <transition name="el-fade-in-linear">
      <div v-if="selectedTask" class="monitor-section">
        <!-- 任务信息栏 -->
        <div class="monitor-header-bar">
          <div class="monitor-title">
            <h3>任务 {{ selectedTask.task_uuid }} 监控面板</h3>
            <el-tag :type="statusType(selectedTask.status)" effect="dark" round size="small">
              {{ statusText(selectedTask.status) }}
            </el-tag>
          </div>
          <div class="monitor-tags">
            <span class="info-chip">模型: <b>{{ selectedTask.model_name }}</b></span>
            <span class="info-chip">设备: <b>{{ selectedTask.device }}</b></span>
            <span class="info-chip">进度: <b>{{ selectedTask.current_epoch }} / {{ selectedTask.epochs }}</b></span>
          </div>
        </div>

        <!-- 最新指标卡片 -->
        <el-row :gutter="20" class="metric-cards">
          <el-col :span="4" v-for="item in metricCards" :key="item.label">
            <div class="modern-metric-card">
              <div class="metric-label">{{ item.label }}</div>
              <div class="metric-value" :class="{ 'highlight': item.value !== '-' }">{{ item.value }}</div>
            </div>
          </el-col>
        </el-row>

        <!-- 训练曲线图表 -->
        <el-row :gutter="20" style="margin-top: 20px">
          <el-col :span="12">
            <el-card class="custom-card chart-card" shadow="hover">
              <div ref="lossChartRef" style="height: 380px"></div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card class="custom-card chart-card" shadow="hover">
              <div ref="mapChartRef" style="height: 380px"></div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </transition>

    <!-- ── 新建训练任务对话框 ── -->
    <el-dialog
      v-model="showCreateDialog"
      title="🚀 新建训练任务"
      width="650px"
      :close-on-click-modal="false"
      class="custom-dialog"
    >
      <el-form :model="trainForm" label-width="120px" class="create-form">
        <el-form-item label="检测场景">
          <el-select v-model="trainForm.scene_id" placeholder="选择场景" style="width: 100%">
            <el-option label="遥感目标检测" :value="1" />
            <el-option label="工业缺陷检测" :value="2" />
            <el-option label="农业病害检测" :value="3" />
          </el-select>
        </el-form-item>

        <el-form-item label="基础模型">
          <el-select v-model="trainForm.model_name" style="width: 100%">
            <el-option label="YOLO11n (Nano, 最快)" value="yolo11n" />
            <el-option label="YOLO11s (Small)" value="yolo11s" />
            <el-option label="YOLO11m (Medium)" value="yolo11m" />
            <el-option label="YOLO11l (Large)" value="yolo11l" />
            <el-option label="YOLO11x (XLarge, 最强)" value="yolo11x" />
          </el-select>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="批次大小">
              <el-input-number v-model="trainForm.batch_size" :min="1" :max="64" :step="2" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="图像尺寸">
              <el-select v-model="trainForm.img_size" style="width: 100%">
                <el-option label="416" :value="416" />
                <el-option label="512" :value="512" />
                <el-option label="640 (默认)" :value="640" />
                <el-option label="768" :value="768" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="训练设备">
          <el-radio-group v-model="trainForm.device">
            <el-radio-button value="cpu">CPU (本地)</el-radio-button>
            <el-radio-button value="0">GPU:0</el-radio-button>
            <el-radio-button value="1">GPU:1</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="优化器">
              <el-select v-model="trainForm.optimizer" style="width: 100%">
                <el-option label="SGD (推荐)" value="SGD" />
                <el-option label="Adam" value="Adam" />
                <el-option label="AdamW" value="AdamW" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="初始学习率">
              <el-input-number v-model="trainForm.lr0" :min="0.0001" :max="0.1" :step="0.001" :precision="4" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="训练轮数 (Epochs)" style="margin-top: 10px;">
          <el-slider v-model="trainForm.epochs" :min="5" :max="500" :step="10" show-input />
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false" round>取消</el-button>
          <el-button type="primary" @click="createTask" :loading="creating" round>
            启动训练
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import request from "@/utils/request";
import { Plus, Refresh } from "@element-plus/icons-vue";
import * as echarts from "echarts";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

// ── 状态变量 ──
const taskList = ref([]);
const loadingTasks = ref(false);
const selectedTask = ref(null);
const showCreateDialog = ref(false);
const creating = ref(false);

// ── 图表引用 ──
const lossChartRef = ref(null);
const mapChartRef = ref(null);
let lossChart = null;
let mapChart = null;

// ── 轮询定时器 ──
let pollTimer = null;

// ── 训练表单 ──
const trainForm = ref({
  scene_id: 1,
  model_name: "yolo11n",
  epochs: 50,
  batch_size: 8,
  img_size: 640,
  device: "cpu",
  optimizer: "SGD",
  lr0: 0.01,
});

// ── 计算属性：最新指标卡片 ──
const metricCards = computed(() => {
  if (!selectedTask.value) return [];
  const m = selectedTask.value.latest_metric;
  if (!m)
    return [
      {
        label: "Epoch",
        value: `${selectedTask.value.current_epoch}/${selectedTask.value.epochs}`,
      },
      { label: "进度", value: `${selectedTask.value.progress}%` },
      { label: "Box Loss", value: "-" },
      { label: "Cls Loss", value: "-" },
      { label: "mAP@50", value: "-" },
      { label: "mAP@50-95", value: "-" },
    ];
  return [
    { label: "Epoch", value: `${m.epoch}/${selectedTask.value.epochs}` },
    {
      label: "Box Loss",
      value: m.box_loss != null ? m.box_loss.toFixed(4) : "-",
    },
    {
      label: "Cls Loss",
      value: m.cls_loss != null ? m.cls_loss.toFixed(4) : "-",
    },
    {
      label: "Precision",
      value: m.precision != null ? (m.precision * 100).toFixed(1) + "%" : "-",
    },
    {
      label: "mAP@50",
      value: m.map50 != null ? (m.map50 * 100).toFixed(1) + "%" : "-",
    },
    {
      label: "mAP@50-95",
      value: m.map50_95 != null ? (m.map50_95 * 100).toFixed(1) + "%" : "-",
    },
  ];
});

// ── 状态映射 ──
function statusType(status) {
  const map = {
    pending: "info",
    running: "warning",
    completed: "success",
    failed: "danger",
    cancelled: "info",
  };
  return map[status] || "info";
}

function statusText(status) {
  const map = {
    pending: "等待中",
    running: "训练中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  return map[status] || status;
}

// ── 获取任务列表 ──
async function fetchTasks() {
  loadingTasks.value = true;
  try {
    const res = await request.get("/training/tasks");
    taskList.value = res.items || [];
  } catch (e) {
    console.error("获取任务列表失败", e);
  } finally {
    loadingTasks.value = false;
  }
}

// ── 选择任务并开始监控 ──
async function selectTask(task) {
  selectedTask.value = task;
  await nextTick();
  initCharts();
  fetchMetrics();
  startPolling();
}

// ── 初始化 ECharts 图表 ──
function initCharts() {
  if (lossChart) lossChart.dispose();
  if (mapChart) mapChart.dispose();

  if (lossChartRef.value) {
    lossChart = echarts.init(lossChartRef.value);
  }
  if (mapChartRef.value) {
    mapChart = echarts.init(mapChartRef.value);
  }
}

// ── 获取训练指标并更新图表 ──
async function fetchMetrics() {
  if (!selectedTask.value) return;
  try {
    const taskId = selectedTask.value.id || selectedTask.value.task?.id;
    const res = await request.get(`/training/metrics/${taskId}`);
    const metrics = res.metrics || [];

    // 更新任务状态
    const statusRes = await request.get(`/training/status/${taskId}`);
    if (statusRes) {
      selectedTask.value = { ...selectedTask.value, ...statusRes };

      // 同步更新任务列表中的进度（进度条 + Epoch 显示）
      if (statusRes.task) {
        const idx = taskList.value.findIndex(
          (t) => t.id === statusRes.task.id,
        );
        if (idx !== -1) {
          taskList.value[idx] = {
            ...taskList.value[idx],
            progress: statusRes.task.progress,
            current_epoch: statusRes.task.current_epoch,
            status: statusRes.task.status,
          };
        }
      }
    }

    if (metrics.length > 0) {
      updateCharts(metrics);
    }
  } catch (e) {
    console.error("获取训练指标失败", e);
  }
}

// ── 更新图表 ──
function updateCharts(metrics) {
  const epochs = metrics.map((m) => m.epoch);

  // Loss 曲线
  if (lossChart) {
    lossChart.setOption({
      backgroundColor: 'transparent',
      title: {
        text: "训练损失曲线 (Training Loss)",
        left: "20",
        top: "10",
        textStyle: { fontSize: 16, fontWeight: 'bold', color: '#ffffff' },
      },
      tooltip: { trigger: "axis", backgroundColor: 'rgba(30, 26, 22, 0.95)', borderColor: 'rgba(139, 115, 85, 0.3)', textStyle: { color: '#ffffff' } },
      legend: { data: ["Box Loss", "Cls Loss", "DFL Loss"], top: "10", right: "20", textStyle: { color: 'rgba(255, 255, 255, 0.7)' } },
      grid: { left: "8%", right: "5%", top: "20%", bottom: "10%", containLabel: true },
      xAxis: { type: "category", data: epochs, name: "Epoch", nameTextStyle: { color: 'rgba(255, 255, 255, 0.5)' }, axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.2)' } }, axisLabel: { color: 'rgba(255, 255, 255, 0.6)' } },
      yAxis: { type: "value", name: "Loss", nameTextStyle: { color: 'rgba(255, 255, 255, 0.5)' }, splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255, 255, 255, 0.08)' } }, axisLabel: { color: 'rgba(255, 255, 255, 0.6)' } },
      series: [
        {
          name: "Box Loss",
          type: "line",
          data: metrics.map((m) => m.box_loss),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 3, color: '#8B7355' },
          itemStyle: { color: '#8B7355' }
        },
        {
          name: "Cls Loss",
          type: "line",
          data: metrics.map((m) => m.cls_loss),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 3, color: '#CD5C5C' },
          itemStyle: { color: '#CD5C5C' }
        },
        {
          name: "DFL Loss",
          type: "line",
          data: metrics.map((m) => m.dfl_loss),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 3, color: '#DAA520' },
          itemStyle: { color: '#DAA520' }
        },
      ],
    });
  }

  // mAP 曲线
  if (mapChart) {
    mapChart.setOption({
      backgroundColor: 'transparent',
      title: {
        text: "评估指标曲线 (Metrics)",
        left: "20",
        top: "10",
        textStyle: { fontSize: 16, fontWeight: 'bold', color: '#ffffff' },
      },
      tooltip: { trigger: "axis", backgroundColor: 'rgba(30, 26, 22, 0.95)', borderColor: 'rgba(139, 115, 85, 0.3)', textStyle: { color: '#ffffff' } },
      legend: {
        data: ["mAP@50", "mAP@50-95", "Precision", "Recall"],
        top: "10", right: "20",
        textStyle: { color: 'rgba(255, 255, 255, 0.7)' }
      },
      grid: { left: "8%", right: "5%", top: "20%", bottom: "10%", containLabel: true },
      xAxis: { type: "category", data: epochs, name: "Epoch", nameTextStyle: { color: 'rgba(255, 255, 255, 0.5)' }, axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.2)' } }, axisLabel: { color: 'rgba(255, 255, 255, 0.6)' } },
      yAxis: { type: "value", name: "Score", max: 1, nameTextStyle: { color: 'rgba(255, 255, 255, 0.5)' }, splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255, 255, 255, 0.08)' } }, axisLabel: { color: 'rgba(255, 255, 255, 0.6)' } },
      series: [
        {
          name: "mAP@50",
          type: "line",
          data: metrics.map((m) => m.map50),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 3, color: '#6B8E23' },
          itemStyle: { color: '#6B8E23' },
        },
        {
          name: "mAP@50-95",
          type: "line",
          data: metrics.map((m) => m.map50_95),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 3, color: '#8B9A38' },
          itemStyle: { color: '#8B9A38' },
        },
        {
          name: "Precision",
          type: "line",
          data: metrics.map((m) => m.precision),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, type: "dashed", color: "#8B7355" },
          itemStyle: { color: "#8B7355" },
        },
        {
          name: "Recall",
          type: "line",
          data: metrics.map((m) => m.recall),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, type: "dashed", color: "#DAA520" },
          itemStyle: { color: "#DAA520" },
        },
      ],
    });
  }
}

// ── 轮询监控 ──
function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    if (selectedTask.value) {
      fetchMetrics();
    }
  }, 5000); // 每 5 秒轮询一次
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ── 创建训练任务 ──
async function createTask() {
  creating.value = true;
  try {
    const res = await request.post("/training/start", trainForm.value);
    ElMessage.success(`训练任务已创建：${res.task_uuid}`);
    showCreateDialog.value = false;
    await fetchTasks();
    // 自动选中新创建的任务
    if (res.id) {
      const newTask = taskList.value.find((t) => t.id === res.id);
      if (newTask) selectTask(newTask);
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "创建训练任务失败");
  } finally {
    creating.value = false;
  }
}

// ── 停止训练任务 ──
async function stopTask(taskId) {
  try {
    await ElMessageBox.confirm(
      "确定要停止当前训练任务吗？训练进度将被保留。",
      "确认停止",
      {
        type: "warning",
      },
    );
    await request.post(`/training/stop/${taskId}`);
    ElMessage.success("训练任务已停止");
    await fetchTasks();
  } catch (e) {
    if (e !== "cancel") {
      ElMessage.error("停止训练失败");
    }
  }
}

// ── 生命周期 ──
onMounted(() => {
  fetchTasks();
});

onBeforeUnmount(() => {
  stopPolling();
  if (lossChart) lossChart.dispose();
  if (mapChart) mapChart.dispose();
});
</script>

<style lang="scss" scoped>
.training-page {
  padding: 24px;
  background: linear-gradient(180deg, rgba(26, 22, 18, 0.95) 0%, rgba(10, 10, 12, 0.98) 100%);
  min-height: 100%;
}

/* ── 页面标题区 ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;

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
  .create-btn {
    box-shadow: 0 4px 12px rgba(139, 115, 85, 0.3);
  }
}

/* ── 自定义卡片样式 ── */
.custom-card {
  border: 1px solid rgba(139, 115, 85, 0.15);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  background: rgba(30, 26, 22, 0.9);

  .el-card__header {
    border-bottom: 1px solid rgba(139, 115, 85, 0.1);
    color: #ffffff;
    font-weight: 600;
  }

  .el-card__body {
    color: rgba(255, 255, 255, 0.8);
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  .card-title {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
  }
}

.task-list-card {
  margin-bottom: 24px;
}

.progress-wrapper {
  padding-right: 20px;
}
.epoch-text {
  font-weight: 500;
  color: rgba(255, 255, 255, 0.7);
}

/* ── 表格样式 ── */
:deep(.el-table) {
  background: transparent !important;

  .el-table__header-wrapper {
    background: rgba(139, 115, 85, 0.1) !important;
    border-radius: 8px 8px 0 0;
  }

  .el-table__header-wrapper thead {
    background: rgba(139, 115, 85, 0.1) !important;
  }

  .el-table__header {
    background: transparent !important;
  }

  .el-table__header tr {
    background: rgba(139, 115, 85, 0.1) !important;
  }

  .el-table__header tr th {
    background: rgba(139, 115, 85, 0.15) !important;
    color: rgba(255, 255, 255, 0.95) !important;
    font-weight: 600 !important;
    border-bottom: 1px solid rgba(139, 115, 85, 0.2) !important;
  }

  .el-table__header th.el-table__cell {
    background: rgba(139, 115, 85, 0.15) !important;
    color: rgba(255, 255, 255, 0.95) !important;
  }

  .el-table__body {
    background: transparent !important;
  }

  .el-table__body tr {
    background: rgba(0, 0, 0, 0.3) !important;

    &:hover > td {
      background: rgba(139, 115, 85, 0.15) !important;
    }
  }

  .el-table__body td.el-table__cell {
    background: transparent !important;
    color: rgba(255, 255, 255, 0.8) !important;
    border-bottom: 1px solid rgba(139, 115, 85, 0.08);
  }

  .el-table__empty-text {
    color: rgba(255, 255, 255, 0.4);
  }

  .el-table__body-wrapper {
    background: transparent !important;
  }

  .el-table__row {
    background: rgba(0, 0, 0, 0.3) !important;
  }

  .el-table__cell {
    background: transparent !important;
    color: rgba(255, 255, 255, 0.8) !important;
  }
}

// 强制覆盖 Element Plus 的内联样式
:deep(.el-table__header-wrapper .el-table__header .el-table__row .el-table__cell) {
  background: rgba(139, 115, 85, 0.1) !important;
  color: rgba(255, 255, 255, 0.8) !important;
}

/* ── 进度条样式 ── */
:deep(.el-progress) {
  .el-progress-bar__outer {
    background: rgba(255, 255, 255, 0.1);
  }

  .el-progress-bar__inner {
    background: linear-gradient(90deg, #8B7355, #A68B67);
  }

  &.el-progress--success .el-progress-bar__inner {
    background: linear-gradient(90deg, #6B8E23, #8B9A38);
  }

  &.el-progress--exception .el-progress-bar__inner {
    background: linear-gradient(90deg, #CD5C5C, #B04040);
  }
}

/* ── 按钮样式 ── */
:deep(.el-button--primary) {
  background: linear-gradient(135deg, #8B7355 0%, #A68B67 100%);
  border: none;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(139, 115, 85, 0.3);

  &:hover {
    background: linear-gradient(135deg, #A68B67 0%, #C4A87A 100%);
  }
}

:deep(.el-button--danger) {
  color: #CD5C5C;
}

/* ── 标签样式 ── */
:deep(.el-tag) {
  border-radius: 8px;
}

:deep(.el-tag--info) {
  background: rgba(139, 115, 85, 0.15);
  border-color: rgba(139, 115, 85, 0.3);
  color: #8B7355;
}

:deep(.el-tag--success) {
  background: rgba(107, 142, 35, 0.15);
  border-color: rgba(107, 142, 35, 0.3);
  color: #6B8E23;
}

:deep(.el-tag--warning) {
  background: rgba(218, 165, 32, 0.15);
  border-color: rgba(218, 165, 32, 0.3);
  color: #DAA520;
}

:deep(.el-tag--danger) {
  background: rgba(205, 92, 92, 0.15);
  border-color: rgba(205, 92, 92, 0.3);
  color: #CD5C5C;
}

/* ── 监控区域 ── */
.monitor-section {
  margin-top: 10px;
}

.monitor-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  background: rgba(30, 26, 22, 0.9);
  padding: 16px 24px;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(139, 115, 85, 0.15);

  .monitor-title {
    display: flex;
    align-items: center;
    gap: 12px;
    h3 {
      margin: 0;
      font-size: 18px;
      color: #ffffff;
    }
  }

  .monitor-tags {
    display: flex;
    gap: 16px;
    .info-chip {
      background: rgba(139, 115, 85, 0.1);
      padding: 6px 16px;
      border-radius: 20px;
      font-size: 13px;
      color: rgba(255, 255, 255, 0.6);
      b {
        color: #8B7355;
        font-weight: 600;
        margin-left: 4px;
      }
    }
  }
}

/* ── 现代指标卡片 ── */
.metric-cards {
  margin-bottom: 8px;
}

.modern-metric-card {
  background: rgba(30, 26, 22, 0.9);
  border-radius: 12px;
  padding: 20px 16px;
  text-align: center;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  border-top: 4px solid rgba(139, 115, 85, 0.1);
  border: 1px solid rgba(139, 115, 85, 0.1);

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    border-top-color: #8B7355;
  }

  .metric-label {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.5);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .metric-value {
    font-size: 24px;
    font-weight: bold;
    color: rgba(255, 255, 255, 0.9);
    &.highlight {
      color: #8B7355;
    }
  }
}

/* ── 图表卡片 ── */
.chart-card {
  padding: 10px;
}

/* ── 弹窗美化 ── */
:deep(.custom-dialog) {
  border-radius: 16px;
  overflow: hidden;
  background: rgba(26, 22, 18, 0.98);
  border: 1px solid rgba(139, 115, 85, 0.2);

  .el-dialog__header {
    background: rgba(139, 115, 85, 0.05);
    margin-right: 0;
    padding-bottom: 20px;
    border-bottom: 1px solid rgba(139, 115, 85, 0.15);
  }

  .el-dialog__title {
    font-weight: 600;
    color: #ffffff;
  }

  .el-dialog__body {
    color: rgba(255, 255, 255, 0.8);
  }

  .el-dialog__footer {
    border-top: 1px solid rgba(139, 115, 85, 0.15);
    background: rgba(0, 0, 0, 0.2);
  }
}

.create-form {
  padding: 10px 20px 0 0;
}

/* ── 表单样式 ── */
:deep(.el-form-item__label) {
  color: rgba(255, 255, 255, 0.7);
}

:deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;

  &:hover {
    border-color: rgba(139, 115, 85, 0.4);
  }

  &.is-focus {
    border-color: #8B7355;
    box-shadow: 0 0 0 3px rgba(139, 115, 85, 0.15);
  }
}

:deep(.el-input__inner) {
  color: #ffffff;
  background: transparent;
}

:deep(.el-select .el-input__inner) {
  color: #ffffff;
}

:deep(.el-select-dropdown) {
  background: rgba(30, 26, 22, 0.98);
  border: 1px solid rgba(139, 115, 85, 0.2);

  .el-select-dropdown__item {
    color: rgba(255, 255, 255, 0.8);

    &.hover,
    &:hover {
      background: rgba(139, 115, 85, 0.15);
    }

    &.selected {
      color: #8B7355;
    }
  }
}

:deep(.el-radio-button) {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);

  &:first-child {
    border-radius: 10px 0 0 10px;
  }

  &:last-child {
    border-radius: 0 10px 10px 0;
  }

  .el-radio-button__inner {
    color: rgba(255, 255, 255, 0.7);
    border-color: rgba(255, 255, 255, 0.1);
  }

  &.is-active {
    .el-radio-button__inner {
      background: rgba(139, 115, 85, 0.2);
      color: #8B7355;
      border-color: #8B7355;
    }
  }
}

:deep(.el-slider__track) {
  background: #8B7355;
}

:deep(.el-slider__thumb) {
  border-color: #8B7355;
}

:deep(.el-input-number) {
  .el-input__inner {
    color: #ffffff;
  }
}

:deep(.el-button--default) {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
  border-radius: 10px;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #ffffff;
  }
}
</style>