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
      <div class="app-header__brand">
        <span class="app-header__brand-mark">AI</span>
        <div class="app-header__brand-copy">
          <span class="app-header__brand-title">{{ appTitle }}</span>
          <span class="app-header__brand-subtitle">遥感智能分析工作台</span>
        </div>
      </div>
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
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: $header-height;
  padding: 0 20px;
  background: rgba(255, 255, 255, 0.84);
  border-bottom: 1px solid $border-color;
  box-shadow: 0 12px 34px rgba(20, 33, 56, 0.08);
  backdrop-filter: blur(20px);
}

.app-header__brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  font-size: 18px;
  font-weight: 700;
  color: $text-primary;
}

.app-header__brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  font-size: 13px;
  color: #fff;
  background: linear-gradient(135deg, $primary-color, $info-color);
  border-radius: 13px;
  box-shadow: 0 12px 24px rgba($primary-color, 0.24);
}

.app-header__brand-copy {
  display: grid;
  min-width: 0;
}

.app-header__brand-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: $text-primary;
}

.app-header__brand-subtitle {
  color: $text-secondary;
  font-size: 12px;
  font-weight: 500;
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
  background: rgba($primary-color, 0.06);
  border: 1px solid rgba($primary-color, 0.14);
  border-radius: 10px;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;

  &:hover {
    color: $text-primary;
    background: rgba($primary-color, 0.12);
    border-color: rgba($primary-color, 0.36);
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
  color: $text-primary;
  cursor: pointer;
  background: rgba($primary-color, 0.06);
  border: 1px solid $border-color;
  border-radius: 999px;
  transition: background-color 0.15s ease, border-color 0.15s ease;

  &:hover {
    background: rgba($primary-color, 0.12);
    border-color: rgba($primary-color, 0.36);
  }
}
</style>
