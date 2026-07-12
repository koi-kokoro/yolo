<template>
  <div class="main-layout">
    <AppSidebar :collapsed="sidebarCollapsed" />
    <section class="layout-body">
      <AppHeader
        :collapsed="sidebarCollapsed"
        @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
      />
      <main class="layout-content">
        <router-view />
      </main>
    </section>
  </div>
</template>

<script setup>
import { ref } from "vue";
import AppHeader from "./AppHeader.vue";
import AppSidebar from "./AppSidebar.vue";

const sidebarCollapsed = ref(false);
</script>

<style lang="scss" scoped>
.main-layout {
  min-height: 100vh;
  display: flex;
  background: $bg-color;
}

.layout-body {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.layout-content {
  flex: 1;
  min-width: 0;
  overflow: auto;
}
</style>
