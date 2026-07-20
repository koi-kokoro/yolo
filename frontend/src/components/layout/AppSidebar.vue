<script setup>
import * as Icons from '@element-plus/icons-vue'

defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
})

const menus = [
  { path: '/dashboard', title: '态势看板', icon: 'Grid' },
  { path: '/chat', title: '智能对话', icon: 'ChatDotRound' },
  { path: '/detection', title: '语义分割', icon: 'DataAnalysis' },
  { path: '/training', title: '模型中枢', icon: 'TrendCharts' },
  { path: '/history', title: '任务归档', icon: 'Files' },
  { path: '/settings', title: '系统设置', icon: 'Setting' },
]

const icons = Icons
</script>

<template>
  <aside class="app-sidebar" :class="{ 'app-sidebar--collapsed': collapsed }" :aria-hidden="collapsed">
    <div class="app-sidebar__summary">
      <span>RSOD AGENT</span>
      <strong>遥感智能分析工作台</strong>
      <small>Detection · Segmentation · RAG</small>
    </div>
    <el-menu router :default-active="$route.path" class="app-sidebar__menu">
      <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
        <el-icon><component :is="icons[item.icon]" /></el-icon>
        <span>{{ item.title }}</span>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<style scoped lang="scss">
.app-sidebar {
  flex: 0 0 var(--sidebar-current-width, $sidebar-width);
  width: var(--sidebar-current-width, $sidebar-width);
  height: calc(100vh - $header-height);
  padding: 16px 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(247, 250, 254, 0.94));
  border-right: 1px solid $border-color;
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.7);
  overflow-y: auto;
  overflow-x: hidden;
  transition: width 0.22s ease, flex-basis 0.22s ease, border-color 0.22s ease;
}

.app-sidebar--collapsed {
  visibility: hidden;
  border-right-color: transparent;
}

.app-sidebar__menu {
  --el-menu-active-color: #17325f;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: rgba(79, 124, 255, 0.08);
  --el-menu-text-color: rgba(58, 72, 98, 0.82);

  border-right: 0;
  padding-bottom: 16px;
  background: transparent;

  :deep(.el-menu-item) {
    flex-shrink: 0 !important;
    height: 46px;
    margin: 6px 0;
    border: 1px solid transparent;
    border-radius: 14px;

    .el-icon {
      flex-shrink: 0 !important;
      width: 24px !important;
      height: 18px !important;
    }

    &.is-active {
      color: $text-primary;
      background: linear-gradient(135deg, rgba($primary-color, 0.12), rgba($info-color, 0.06));
      border-color: rgba($primary-color, 0.22);
      box-shadow: 0 12px 24px rgba($primary-color, 0.1);
    }
  }
}

.app-sidebar__summary {
  display: grid;
  gap: 5px;
  padding: 14px;
  margin-bottom: 12px;
  background: rgba($primary-color, 0.05);
  border: 1px solid rgba($primary-color, 0.18);
  border-radius: 18px;
}

.app-sidebar__summary span {
  font-size: 11px;
  color: $primary-light;
  letter-spacing: 0.14em;
}

.app-sidebar__summary strong {
  color: $text-primary;
  font-size: 15px;
}

.app-sidebar__summary small {
  color: $text-secondary;
}


@media (max-width: 768px) {
  .app-sidebar {
    flex-basis: auto;
    width: 100%;
    height: auto;
    max-height: calc(100vh - $header-height);
  }

  .app-sidebar--collapsed {
    display: none;
  }
}
</style>
