<template>
  <aside class="app-sidebar">
    <div class="sidebar-brand">
      <div class="brand-logo">
        <span>🌾</span>
      </div>
      <div class="brand-info">
        <h1 class="brand-title">RSOD</h1>
        <p class="brand-subtitle">目标检测智能体</p>
      </div>
    </div>
    
    <el-menu
      :default-active="activeMenu"
      :router="true"
      background-color="#1A1612"
      text-color="#C4B8A8"
      active-text-color="#8B7355"
    >
      <el-menu-item
        v-for="item in menuItems"
        :key="item.path"
        :index="item.path"
      >
        <el-icon>
          <component :is="item.icon" />
        </el-icon>
        <span>{{ item.title }}</span>
      </el-menu-item>
    </el-menu>

    <div class="sidebar-user">
      <el-dropdown trigger="click" @command="handleCommand">
        <div class="user-info">
          <el-avatar :size="36" :src="userStore.avatar || undefined">
            {{ userStore.username?.charAt(0)?.toUpperCase() }}
          </el-avatar>
          <div class="user-detail">
            <span class="username">{{ userStore.username }}</span>
            <span class="user-role">用户</span>
          </div>
          <el-icon class="user-arrow"><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">
              <el-icon><User /></el-icon>个人中心
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </aside>
</template>

<script setup>
import { useUserStore } from '@/stores/user'
import {
  ArrowDown,
  ChatDotRound,
  Clock,
  Cpu,
  DataAnalysis,
  Setting,
  SwitchButton,
  User
} from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => {
  return '/' + route.path.split('/')[1]
})

const menuItems = [
  { path: '/chat', title: '智能检测', icon: ChatDotRound },
  { path: '/training', title: '模型训练', icon: Cpu },
  { path: '/history', title: '历史记录', icon: Clock },
  { path: '/dashboard', title: '数据看板', icon: DataAnalysis },
  { path: '/settings', title: '系统设置', icon: Setting },
]

function handleCommand(command) {
  switch (command) {
    case 'profile':
      break
    case 'logout':
      ElMessageBox.confirm('确定要退出登录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }).then(() => {
        userStore.logout()
        router.push('/login')
      }).catch(() => {})
      break
  }
}
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  height: 100%;
  background: $sidebar-bg;
  overflow-y: auto;
  border-right: 1px solid rgba(139, 115, 85, 0.1);
  position: relative;
  display: flex;
  flex-direction: column;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(180deg, rgba(139, 115, 85, 0.05) 0%, transparent 25%);
    pointer-events: none;
  }
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 24px 20px;
  border-bottom: 1px solid rgba(139, 115, 85, 0.1);
  background: rgba(139, 115, 85, 0.03);
  position: relative;
  z-index: 2;
}

.brand-logo {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #8B7355 0%, #A68B67 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  box-shadow: 0 4px 16px rgba(139, 115, 85, 0.3);
}

.brand-info {
  flex: 1;
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
  color: #ffffff;
  margin: 0;
  letter-spacing: 1px;
}

.brand-subtitle {
  font-size: 11px;
  color: rgba(139, 115, 85, 0.8);
  margin: 2px 0 0;
  letter-spacing: 0.5px;
}

.el-menu {
  border-right: none;
  flex: 1;
  padding-top: 8px;
}

.el-menu-item {
  height: 52px;
  line-height: 52px;
  font-size: 14px;
  margin: 4px 12px;
  border-radius: 10px;
  position: relative;
  overflow: hidden;
  transition: all 0.25s ease;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 0;
    background: $primary-color;
    border-radius: 0 2px 2px 0;
    transition: height 0.25s ease;
  }

  &.is-active {
    background-color: rgba(139, 115, 85, 0.18) !important;
    font-weight: 600;
    box-shadow: 
      0 4px 16px rgba(139, 115, 85, 0.15),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);

    &::before {
      height: 60%;
    }
  }

  &:hover {
    background-color: rgba(255, 255, 255, 0.05) !important;
    
    &::before {
      height: 40%;
    }
  }

  .el-icon {
    margin-right: 12px;
    font-size: 18px;
    transition: transform 0.2s ease;
  }

  &:hover .el-icon {
    transform: scale(1.1);
  }
}

.sidebar-user {
  padding: 16px;
  border-top: 1px solid rgba(139, 115, 85, 0.1);
  background: rgba(139, 115, 85, 0.03);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 12px;
  transition: all 0.25s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.05);
  }
}

.user-detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.username {
  font-size: 14px;
  font-weight: 600;
  color: #ffffff;
}

.user-role {
  font-size: 11px;
  color: rgba(139, 115, 85, 0.7);
}

.user-arrow {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.5);
  transition: transform 0.25s ease;
}

.user-info:hover .user-arrow {
  transform: rotate(180deg);
}

:deep(.el-avatar) {
  background: linear-gradient(135deg, #8B7355 0%, #A68B67 100%);
  font-weight: 600;
}

:deep(.el-dropdown-menu) {
  background: rgba(26, 22, 18, 0.98);
  border: 1px solid rgba(139, 115, 85, 0.2);
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);

  .el-dropdown-item {
    color: rgba(255, 255, 255, 0.8);

    &:hover {
      background: rgba(139, 115, 85, 0.15);
      color: #fff;
    }

    &.is-divided {
      border-top-color: rgba(255, 255, 255, 0.08);
    }
  }
}
</style>
