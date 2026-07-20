<template>
  <div class="main-layout">
    <!-- 顶部导航栏 -->
    <AppHeader />

    <!-- 下方区域：侧边栏 + 内容区 -->
    <div class="layout-body">
      <AppSidebar />

      <!-- 页面内容区 -->
      <main class="layout-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import AppHeader from './AppHeader.vue';
import AppSidebar from './AppSidebar.vue';
</script>

<style lang="scss" scoped>
.main-layout {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(26, 22, 18, 0.95) 0%, rgba(10, 10, 12, 0.98) 100%);
}

.layout-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  border-radius: 16px 16px 0 0;
  margin-top: -8px;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.3);
}

.layout-content {
  flex: 1;
  padding: 0;
  background: transparent;
  overflow: hidden;
  position: relative;
}
</style>
