<script setup>
import { ChatDotRound, DataAnalysis, Files, Grid, TrendCharts } from '@element-plus/icons-vue'

const menus = [
  { path: '/dashboard', title: '仪表盘', icon: Grid },
  { path: '/chat', title: '智能对话', icon: ChatDotRound },
  { path: '/detection', title: '目标检测', icon: DataAnalysis },
  { path: '/training', title: '模型训练', icon: TrendCharts },
  { path: '/history', title: '历史记录', icon: Files },
]
</script>

<template>
  <aside class="app-sidebar">
    <el-menu router :default-active="$route.path" class="app-sidebar__menu">
      <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.title }}</span>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<style scoped lang="scss">
.app-sidebar {
  width: $sidebar-width;
  min-height: calc(100vh - $header-height);
  background: #fff;
  border-right: 1px solid $border-color;
}

.app-sidebar__menu {
  border-right: 0;
}
</style>
