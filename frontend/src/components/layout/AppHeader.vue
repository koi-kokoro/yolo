<template>
  <header class="app-header">
    <div class="header-left">
      <el-button text class="collapse-btn" @click="$emit('toggle-sidebar')">
        <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
      </el-button>
      <div class="brand">
        <span class="brand-title">lee Agent Platform</span>
        <span class="brand-subtitle">YOLOv11 目标检测智能体平台</span>
      </div>
    </div>

    <div class="header-right">
      <el-dropdown trigger="click" @command="handleCommand">
        <button class="user-menu" type="button">
          <el-avatar :size="32" :src="userStore.avatar">
            {{ usernameInitial }}
          </el-avatar>
          <span class="username">{{ userStore.username || "用户" }}</span>
          <el-icon><ArrowDown /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              {{ userStore.isSuperuser ? "管理员" : "普通用户" }}
            </el-dropdown-item>
            <el-dropdown-item divided command="logout"
              >退出登录</el-dropdown-item
            >
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { useUserStore } from "@/stores/user";
import { ArrowDown, Expand, Fold } from "@element-plus/icons-vue";
import { computed } from "vue";
import { useRouter } from "vue-router";

defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["toggle-sidebar"]);

const router = useRouter();
const userStore = useUserStore();

const usernameInitial = computed(() =>
  (userStore.username || "U").slice(0, 1).toUpperCase(),
);

function handleCommand(command) {
  if (command === "logout") {
    userStore.logout();
    router.push("/login");
  }
}
</script>

<style lang="scss" scoped>
.app-header {
  height: $header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $spacing-lg;
  background: #fff;
  border-bottom: 1px solid $border-color-light;
  box-shadow: $shadow-sm;
}

.header-left,
.header-right,
.user-menu {
  display: flex;
  align-items: center;
}

.collapse-btn {
  width: 36px;
  height: 36px;
  margin-right: $spacing-md;
  font-size: 18px;
}

.brand {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.brand-title {
  font-size: 16px;
  font-weight: 700;
  color: $text-primary;
}

.brand-subtitle {
  margin-top: 3px;
  font-size: 12px;
  color: $text-secondary;
}

.user-menu {
  gap: $spacing-sm;
  border: 0;
  background: transparent;
  color: $text-regular;
  cursor: pointer;
}

.username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
