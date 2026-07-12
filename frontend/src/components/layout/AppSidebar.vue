<template>
  <aside class="app-sidebar" :class="{ collapsed }">
    <div class="sidebar-logo">
      <img src="/favicon.svg" alt="logo" />
      <span v-if="!collapsed">lee</span>
    </div>

    <el-menu
      :default-active="activePath"
      :collapse="collapsed"
      router
      class="sidebar-menu"
      background-color="#304156"
      text-color="#bfcbd9"
      active-text-color="#409eff"
    >
      <el-menu-item index="/chat">
        <el-icon><ChatDotRound /></el-icon>
        <template #title>智能对话</template>
      </el-menu-item>
      <el-menu-item index="/detection">
        <el-icon><Aim /></el-icon>
        <template #title>检测工作台</template>
      </el-menu-item>
      <el-menu-item index="/training">
        <el-icon><Cpu /></el-icon>
        <template #title>模型训练</template>
      </el-menu-item>
      <el-menu-item index="/history">
        <el-icon><Clock /></el-icon>
        <template #title>历史记录</template>
      </el-menu-item>
      <el-menu-item index="/dashboard">
        <el-icon><DataAnalysis /></el-icon>
        <template #title>数据看板</template>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<script setup>
import {
  Aim,
  ChatDotRound,
  Clock,
  Cpu,
  DataAnalysis,
} from "@element-plus/icons-vue";
import { computed } from "vue";
import { useRoute } from "vue-router";

defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
});

const route = useRoute();
const activePath = computed(() => route.path);
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  height: 100vh;
  flex-shrink: 0;
  background: $sidebar-bg;
  transition: width 0.2s ease;
  overflow: hidden;

  &.collapsed {
    width: $sidebar-collapsed-width;
  }
}

.sidebar-logo {
  height: $header-height;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $spacing-sm;
  color: #fff;
  font-weight: 700;
  letter-spacing: 0;

  img {
    width: 28px;
    height: 28px;
  }
}

.sidebar-menu {
  border-right: 0;
}
</style>
