<script setup>
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
</script>

<template>
  <div class="main-layout">
    <AppHeader />
    <div class="main-layout__body">
      <AppSidebar />
      <main class="main-layout__content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped lang="scss">
.main-layout {
  min-height: 100vh;
  background: $background-color;
}

.main-layout__body {
  display: flex;
  min-height: calc(100vh - $header-height);
}

.main-layout__content {
  flex: 1;
  min-width: 0;
  padding: 24px;
}

@media (max-width: 768px) {
  .main-layout__body {
    flex-direction: column;
  }

  .main-layout__content {
    padding: 16px;
  }
}
</style>
