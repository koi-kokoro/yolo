<template>
  <div class="history-page">
    <!-- ── 页面标题 + 快速统计 ── -->
    <div class="page-header">
      <h2>检测历史</h2>
      <div class="header-stats">
        <el-tag type="info">总计 {{ summary.total_tasks }} 次</el-tag>
        <el-tag type="success">今日 {{ summary.today_tasks }} 次</el-tag>
        <el-tag type="warning"
          >处理中 {{ summary.status_counts?.processing || 0 }}</el-tag
        >
      </div>
    </div>

    <!-- ── 筛选栏 ── -->
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" @submit.prevent="loadTasks">
        <el-form-item label="类型">
          <el-select
            v-model="filters.task_type"
            placeholder="全部"
            clearable
            style="width: 120px"
          >
            <el-option label="单图检测" value="single" />
            <el-option label="批量检测" value="batch" />
            <el-option label="ZIP 检测" value="zip" />
            <el-option label="视频检测" value="video" />
            <el-option label="摄像头" value="camera" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filters.status"
            placeholder="全部"
            clearable
            style="width: 120px"
          >
            <el-option label="已完成" value="completed" />
            <el-option label="处理中" value="processing" />
            <el-option label="失败" value="failed" />
            <el-option label="等待中" value="pending" />
          </el-select>
        </el-form-item>
        <el-form-item label="场景">
          <el-select
            v-model="filters.scene_id"
            placeholder="全部"
            clearable
            style="width: 150px"
          >
            <el-option
              v-for="scene in scenes"
              :key="scene.id"
              :label="scene.display_name"
              :value="scene.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 260px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadTasks">搜索</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ── 任务列表表格 ── -->
    <el-card shadow="never" class="table-card">
      <el-table :data="tasks" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" align="center" />
        <el-table-column prop="task_type" label="类型">
          <template #default="{ row }">
            <el-tag :type="typeTagMap[row.task_type] || 'info'" size="small">
              {{ typeNameMap[row.task_type] || row.task_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态">
          <template #default="{ row }">
            <el-tag :type="statusTagMap[row.status]" size="small">
              {{ statusNameMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="scene_name" label="场景" />
        <el-table-column prop="total_objects" label="目标数" align="center" />
        <el-table-column prop="total_inference_time" label="推理耗时" align="center">
          <template #default="{ row }">
            {{ row.total_inference_time ? `${row.total_inference_time}ms` : "-" }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row.id)"
              >详情</el-button
            >
            <el-button link type="danger" @click="handleDelete(row.id)"
              >删除</el-button
            >
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadTasks"
          @size-change="loadTasks"
        />
      </div>
    </el-card>

    <!-- ── 任务详情抽屉 ── -->
    <el-drawer v-model="drawerVisible" title="任务详情" size="500px">
      <template v-if="detailLoading">
        <div style="text-align: center; padding: 40px">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        </div>
      </template>
      <template v-else-if="taskDetail">
        <!-- 任务基本信息 -->
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="任务 ID">{{
            taskDetail.task.id
          }}</el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag size="small">{{
              typeNameMap[taskDetail.task.task_type]
            }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagMap[taskDetail.task.status]" size="small">
              {{ statusNameMap[taskDetail.task.status] }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="场景">{{
            taskDetail.task.scene_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="图片数">{{
            taskDetail.task.total_images
          }}</el-descriptions-item>
          <el-descriptions-item label="目标数">{{
            taskDetail.task.total_objects
          }}</el-descriptions-item>
          <el-descriptions-item label="推理耗时"
            >{{ taskDetail.task.total_inference_time }}ms</el-descriptions-item
          >
          <el-descriptions-item label="置信度">{{
            taskDetail.task.conf_threshold
          }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">
            {{ formatDate(taskDetail.task.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="完成时间" :span="2">
            {{ formatDate(taskDetail.task.completed_at) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="taskDetail.task.error_message"
            label="错误信息"
            :span="2"
          >
            <span style="color: #f56c6c">{{
              taskDetail.task.error_message
            }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 类别分布 -->
        <div
          v-if="Object.keys(taskDetail.class_counts).length"
          class="detail-section"
        >
          <h4>类别分布</h4>
          <div class="class-tags">
            <el-tag
              v-for="(count, name) in taskDetail.class_counts"
              :key="name"
              size="default"
            >
              {{ name }} x {{ count }}
            </el-tag>
          </div>
        </div>

        <!-- 检测结果列表 -->
        <div v-if="taskDetail.results.length" class="detail-section">
          <h4>检测结果（{{ taskDetail.results.length }} 条）</h4>
          <el-table
            :data="taskDetail.results"
            size="small"
            max-height="300"
            stripe
          >
            <el-table-column prop="class_name" label="类别" width="100" />
            <el-table-column label="置信度" width="80">
              <template #default="{ row }">
                {{ (row.confidence * 100).toFixed(1) }}%
              </template>
            </el-table-column>
            <el-table-column label="边界框">
              <template #default="{ row }">
                <span style="font-family: monospace; font-size: 11px">
                  [{{ row.bbox.map((v) => Math.round(v)).join(", ") }}]
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * HistoryPage.vue — 检测历史记录
 *
 * 功能：
 *   - 检测任务分页列表（表格展示）
 *   - 多条件筛选（类型/状态/场景/日期范围）
 *   - 任务详情抽屉（基本信息 + 类别分布 + 结果列表）
 *   - 删除任务（确认弹窗）
 */
import {
  deleteTask,
  getHistorySummary,
  getScenes,
  getTaskDetail,
  getTaskList,
} from "@/api/history";
import { Loading } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, reactive, ref } from "vue";

// ── 映射表 ──
const typeNameMap = {
  single: "单图检测",
  batch: "批量检测",
  zip: "ZIP 检测",
  video: "视频检测",
  camera: "摄像头",
};
const typeTagMap = {
  single: "primary",
  batch: "success",
  zip: "warning",
  video: "danger",
  camera: "info",
};
const statusNameMap = {
  completed: "已完成",
  processing: "处理中",
  failed: "失败",
  pending: "等待中",
};
const statusTagMap = {
  completed: "success",
  processing: "warning",
  failed: "danger",
  pending: "info",
};

// ── 状态 ──
const loading = ref(false);
const tasks = ref([]);
const scenes = ref([]);
const summary = ref({ total_tasks: 0, today_tasks: 0, status_counts: {} });
const dateRange = ref(null);

const filters = reactive({
  task_type: null,
  status: null,
  scene_id: null,
});

const pagination = reactive({
  page: 1,
  page_size: 10,
  total: 0,
});

// ── 详情抽屉 ──
const drawerVisible = ref(false);
const detailLoading = ref(false);
const taskDetail = ref(null);

// ── 日期格式化 ──
function formatDate(isoStr) {
  if (!isoStr) return "-";
  const d = new Date(isoStr);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ── 加载任务列表 ──
async function loadTasks() {
  loading.value = true;
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
    };
    if (filters.task_type) params.task_type = filters.task_type;
    if (filters.status) params.status = filters.status;
    if (filters.scene_id) params.scene_id = filters.scene_id;
    if (dateRange.value) {
      params.start_date = dateRange.value[0];
      params.end_date = dateRange.value[1];
    }

    const res = await getTaskList(params);
    tasks.value = res.items;
    pagination.total = res.total;
  } catch (err) {
    console.error("[加载任务列表失败]", err);
  } finally {
    loading.value = false;
  }
}

// ── 重置筛选 ──
function resetFilters() {
  filters.task_type = null;
  filters.status = null;
  filters.scene_id = null;
  dateRange.value = null;
  pagination.page = 1;
  loadTasks();
}

// ── 加载快速统计 ──
async function loadSummary() {
  try {
    summary.value = await getHistorySummary();
  } catch (err) {
    console.error("[加载统计失败]", err);
  }
}

// ── 加载场景列表 ──
async function loadScenes() {
  try {
    const res = await getScenes();
    scenes.value = res.scenes;
  } catch (err) {
    console.error("[加载场景列表失败]", err);
  }
}

// ── 查看详情 ──
async function viewDetail(taskId) {
  drawerVisible.value = true;
  detailLoading.value = true;
  taskDetail.value = null;
  try {
    taskDetail.value = await getTaskDetail(taskId);
  } catch (err) {
    ElMessage.error("加载任务详情失败");
    console.error("[加载详情失败]", err);
  } finally {
    detailLoading.value = false;
  }
}

// ── 删除任务 ──
async function handleDelete(taskId) {
  try {
    await ElMessageBox.confirm(
      `确定要删除任务 #${taskId} 吗？删除后不可恢复。`,
      "删除确认",
      {
        confirmButtonText: "确定删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );

    await deleteTask(taskId);
    ElMessage.success(`任务 #${taskId} 已删除`);

    // 刷新列表和统计
    loadTasks();
    loadSummary();
  } catch (err) {
    if (err !== "cancel") {
      ElMessage.error("删除失败");
    }
  }
}

onMounted(() => {
  loadTasks();
  loadSummary();
  loadScenes();
});
</script>

<style lang="scss" scoped>
.history-page {
  padding: 24px;
  background: linear-gradient(180deg, rgba(26, 22, 18, 0.95) 0%, rgba(10, 10, 12, 0.98) 100%);
  min-height: 100%;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(139, 115, 85, 0.1);

  h2 {
    margin: 0;
    font-size: 24px;
    font-weight: 700;
    color: #ffffff;
  }
}

.header-stats {
  display: flex;
  gap: 12px;
}

.filter-card {
  margin-bottom: 20px;
  border: 1px solid rgba(139, 115, 85, 0.15);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  background: rgba(30, 26, 22, 0.9);

  :deep(.el-card__body) {
    padding: 20px;
    color: rgba(255, 255, 255, 0.8);
  }

  :deep(.el-card__header) {
    border-bottom: 1px solid rgba(139, 115, 85, 0.1);
    color: #ffffff;
    font-weight: 600;
  }
}

.table-card {
  margin-bottom: 20px;
  border: 1px solid rgba(139, 115, 85, 0.15);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  background: rgba(30, 26, 22, 0.9);

  :deep(.el-card__body) {
    padding: 20px;
  }
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
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

    &:hover {
      background: rgba(139, 115, 85, 0.15);
    }

    &.selected {
      color: #8B7355;
    }
  }
}

:deep(.el-date-editor) {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;

  .el-input__inner {
    color: #ffffff;
  }
}

:deep(.el-date-picker__header-label) {
  color: rgba(255, 255, 255, 0.8);
}

:deep(.el-picker-panel) {
  background: rgba(30, 26, 22, 0.98);
  border: 1px solid rgba(139, 115, 85, 0.2);

  .el-picker-panel__footer {
    border-top: 1px solid rgba(139, 115, 85, 0.1);
  }
}

:deep(.el-calendar-table) {
  thead th {
    color: rgba(255, 255, 255, 0.6);
  }

  td {
    color: rgba(255, 255, 255, 0.8);
  }

  .el-calendar-day {
    &:hover {
      background: rgba(139, 115, 85, 0.15);
    }
  }

  .is-selected {
    background: rgba(139, 115, 85, 0.3) !important;
    color: #ffffff;
  }
}

:deep(.el-button--primary) {
  background: linear-gradient(135deg, #8B7355 0%, #A68B67 100%);
  border: none;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(139, 115, 85, 0.3);

  &:hover {
    background: linear-gradient(135deg, #A68B67 0%, #C4A87A 100%);
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

:deep(.el-tag--primary) {
  background: rgba(139, 115, 85, 0.15);
  border-color: rgba(139, 115, 85, 0.3);
  color: #8B7355;
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

/* ── 分页样式 ── */
:deep(.el-pagination) {
  .el-pagination__sizes,
  .el-pagination__total,
  .el-pagination__jump,
  .el-pager li {
    color: rgba(255, 255, 255, 0.7);
  }

  .el-pager li.is-active {
    background: #8B7355;
    color: #ffffff;
  }

  .el-pagination button {
    color: rgba(255, 255, 255, 0.7);
  }
}

/* ── 详情抽屉 ── */
:deep(.el-drawer) {
  background: rgba(26, 22, 18, 0.98);
  border-left: 1px solid rgba(139, 115, 85, 0.2);

  .el-drawer__header {
    border-bottom: 1px solid rgba(139, 115, 85, 0.1);
    color: #ffffff;
  }

  .el-drawer__title {
    color: #ffffff;
  }
}

.detail-section {
  margin-top: 24px;

  h4 {
    margin: 0 0 16px;
    font-size: 16px;
    color: rgba(255, 255, 255, 0.9);
    font-weight: 600;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(139, 115, 85, 0.1);
  }
}

.class-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

/* ── 描述列表样式 ── */
:deep(.el-descriptions) {
  background: transparent !important;
}
</style>