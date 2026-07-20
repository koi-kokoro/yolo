<template>
  <div class="history-page">
    <div class="page-header">
      <h2>检测历史</h2>
      <div class="header-stats">
        <el-tag type="info">总计 {{ summary.total_tasks }} 次</el-tag>
        <el-tag type="success">今日 {{ summary.today_tasks }} 次</el-tag>
        <el-tag type="warning">处理中 {{ summary.status_counts?.processing || 0 }}</el-tag>
      </div>
    </div>

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

    <el-card shadow="never" class="table-card">
      <el-table :data="tasks" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="task_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="typeTagMap[row.task_type] || 'info'" size="small">
              {{ typeNameMap[row.task_type] || row.task_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagMap[row.status]" size="small">
              {{ statusNameMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="scene_name" label="场景" width="130" />
        <el-table-column
          prop="total_objects"
          label="目标数"
          width="80"
          align="center"
        />
        <el-table-column
          prop="total_inference_time"
          label="推理耗时"
          width="100"
          align="center"
        >
          <template #default="{ row }">
            {{
              row.total_inference_time ? `${row.total_inference_time}ms` : "-"
            }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
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
            <span class="error-text">{{ taskDetail.task.error_message }}</span>
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
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(248, 250, 253, 0.72));
  border: 1px solid rgba(78, 103, 138, 0.14);
  border-radius: 12px;
  box-shadow: 0 10px 28px rgba(20, 33, 56, 0.06);

  h2 {
    margin: 0;
    font-size: 24px;
    color: $text-primary;
  }
}

.header-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-card {
  border-radius: 12px;

  :deep(.el-card__body) {
    padding: 16px 16px 4px;
  }

  :deep(.el-form) {
    display: flex;
    flex-wrap: wrap;
    gap: 0 8px;
  }
}

.table-card {
  overflow: hidden;
  border-radius: 12px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 详情抽屉 */
.detail-section {
  margin-top: 20px;
  padding: 14px;
  background: rgba(78, 103, 138, 0.05);
  border: 1px solid rgba(78, 103, 138, 0.1);
  border-radius: 10px;

  h4 {
    margin: 0 0 12px;
    font-size: 14px;
    color: $text-primary;
  }
}

.class-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.error-text {
  color: $danger-color;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }

  .pagination-wrapper {
    justify-content: flex-start;
  }

  .filter-card :deep(.el-form-item),
  .filter-card :deep(.el-select),
  .filter-card :deep(.el-date-editor) {
    width: 100% !important;
  }
}
</style>
