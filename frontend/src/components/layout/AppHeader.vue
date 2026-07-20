<script setup>
import { ArrowDown, Expand, Fold, SwitchButton } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const appTitle = import.meta.env.VITE_APP_TITLE || 'RSOD Agent Platform'

defineProps({
  sidebarCollapsed: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['toggle-sidebar'])

function handleLogout() {
  userStore.logout()
  router.push('/login')
}
</script>

<template>
  <header class="app-header">
    <div class="app-header__leading">
      <button
        class="app-header__sidebar-toggle"
        type="button"
        :aria-label="sidebarCollapsed ? '显示任务栏' : '隐藏任务栏'"
        :title="sidebarCollapsed ? '显示任务栏' : '隐藏任务栏'"
        @click="$emit('toggle-sidebar')"
      >
        <el-icon :size="20">
          <Expand v-if="sidebarCollapsed" />
          <Fold v-else />
        </el-icon>
      </button>
      <div class="app-header__brand">{{ appTitle }}</div>
    </div>
    <el-dropdown trigger="click">
      <button class="app-header__user" type="button">
        <span>{{ userStore.username || '用户' }}</span>
        <el-icon><ArrowDown /></el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item :icon="SwitchButton" @click="handleLogout">退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </header>
</template>

<style scoped lang="scss">
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: $header-height;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid $border-color;
}

.app-header__brand {
  font-size: 18px;
  font-weight: 700;
  color: $text-color;
}

.app-header__leading {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.app-header__sidebar-toggle {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  color: $text-secondary;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 8px;
  transition: color 0.15s ease, background-color 0.15s ease;

  &:hover {
    color: $text-color;
    background: $background-color;
  }

  &:focus-visible {
    outline: 2px solid rgba($primary-color, 0.45);
    outline-offset: 2px;
  }
}

.app-header__user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
  color: $text-color;
  cursor: pointer;
  background: #fff;
  border: 1px solid $border-color;
  border-radius: 6px;
}
</style>
