<script setup>
import * as Icons from '@element-plus/icons-vue'

defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
})

const menus = [
  { path: '/dashboard', title: '仪表盘', icon: 'Grid' },
  { path: '/chat', title: '智能对话', icon: 'ChatDotRound' },
  { path: '/detection', title: '智能检测', icon: 'DataAnalysis' },
  { path: '/training', title: '模型管理', icon: 'TrendCharts' },
  { path: '/history', title: '历史记录', icon: 'Files' },
  { path: '/settings', title: '系统设置', icon: 'Setting' },
]

const icons = Icons
</script>

<template>
  <aside class="app-sidebar" :class="{ 'app-sidebar--collapsed': collapsed }" :aria-hidden="collapsed">
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
  // 1. 必须用明确的 height 限制住侧边栏，不要用 min-height 任由它无限长高
  height: calc(100vh - $header-height); 
  background: #fff;
  border-right: 1px solid $border-color;
  // 2. 允许纵向滚动（如果以后菜单项变多，可以丝滑滚动）
  overflow-y: auto; 
  overflow-x: hidden;
  transition: width 0.22s ease, flex-basis 0.22s ease, border-color 0.22s ease;
}

.app-sidebar--collapsed {
  visibility: hidden;
  border-right-color: transparent;
}

.app-sidebar__menu {
  border-right: 0;
  padding-bottom: 16px; /* 留出一点底部呼吸空间 */

  // 3. 强行锁死 Element 菜单项和图标的 Flex 收缩，防止 Chrome 乱裁切
  :deep(.el-menu-item) {
    flex-shrink: 0 !important;
    
    .el-icon {
      flex-shrink: 0 !important;
      width: 24px !important;
      height: 18px !important;
    }
  }
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
