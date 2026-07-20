<template>
  <div class="settings-page">
    <div class="page-header">
      <h2>系统设置</h2>
      <p>调整账户信息和密码，保持当前登录状态下的个人配置一致。</p>
    </div>

    <el-row :gutter="24">
      <!-- 个人信息 -->
      <el-col :span="12">
        <el-card shadow="hover" class="settings-card profile-card">
          <template #header>
            <span>个人信息</span>
          </template>

          <el-form :model="profileForm" label-width="80px">
            <el-form-item label="用户名">
              <el-input :model-value="profileForm.username" disabled />
            </el-form-item>
            <el-form-item label="用户类型">
              <el-input :model-value="profileForm.is_superuser ? '管理员' : '普通用户'" disabled />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="profileForm.email" placeholder="请输入邮箱" />
            </el-form-item>
            <el-form-item label="手机号">
              <el-input v-model="profileForm.phone" placeholder="请输入手机号" />
            </el-form-item>
            <el-form-item label="注册时间">
              <el-input :model-value="formatDate(profileForm.created_at)" disabled />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="updateProfile" :loading="profileLoading">
                保存修改
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 修改密码 -->
      <el-col :span="12">
        <el-card shadow="hover" class="settings-card password-card">
          <template #header>
            <span>修改密码</span>
          </template>

          <el-form
            ref="passwordFormRef"
            :model="passwordForm"
            :rules="passwordRules"
            label-width="100px"
          >
            <el-form-item label="当前密码" prop="old_password">
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
                placeholder="请输入当前密码"
              />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
                placeholder="请输入新密码（至少 6 位）"
              />
            </el-form-item>
            <el-form-item label="确认新密码" prop="confirm_password">
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
                placeholder="请再次输入新密码"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="changePassword" :loading="passwordLoading">
                修改密码
              </el-button>
              <el-button @click="resetPasswordForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 关于系统 -->
    <el-card shadow="hover" class="settings-card about-card">
      <template #header>
        <span>关于系统</span>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="系统名称">RSOD Agent Platform</el-descriptions-item>
        <el-descriptions-item label="版本号">v0.1.0</el-descriptions-item>
        <el-descriptions-item label="检测模型">YOLO11n</el-descriptions-item>
        <el-descriptions-item label="前端框架">Vue 3 + Element Plus</el-descriptions-item>
        <el-descriptions-item label="后端框架">FastAPI + SQLAlchemy</el-descriptions-item>
        <el-descriptions-item label="数据库">PostgreSQL + Redis + MinIO</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
/**
 * SettingsPage.vue — 系统设置
 *
 * 功能：
 *   - 个人信息查看与修改（邮箱、手机号）
 *   - 密码修改（旧密码验证 + 新密码确认）
 *   - 系统信息展示
 */
import request from "@/utils/request";
import { useUserStore } from "@/stores/user";
import { ElMessage } from "element-plus";
import { onMounted, reactive, ref } from "vue";

const userStore = useUserStore();

// ── 个人信息 ──
const profileForm = reactive({
  username: "",
  is_superuser: false,
  email: "",
  phone: "",
  created_at: null,
});
const profileLoading = ref(false);

// ── 修改密码 ──
const passwordFormRef = ref(null);
const passwordForm = reactive({
  old_password: "",
  new_password: "",
  confirm_password: "",
});
const passwordLoading = ref(false);

const passwordRules = {
  old_password: [{ required: true, message: "请输入当前密码", trigger: "blur" }],
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 6, message: "密码至少 6 位", trigger: "blur" },
  ],
  confirm_password: [
    { required: true, message: "请确认新密码", trigger: "blur" },
    {
      validator: (rule, value, callback) => {
        if (value !== passwordForm.new_password) {
          callback(new Error("两次输入的密码不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
};

// ── 日期格式化 ──
function formatDate(dateStr) {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleString("zh-CN");
}

// ── 加载用户信息 ──
async function loadUserInfo() {
  try {
    const res = await request.get("/auth/me");
    profileForm.username = res.username;
    profileForm.is_superuser = Boolean(res.is_superuser);
    profileForm.email = res.email;
    profileForm.phone = res.phone || "";
    profileForm.created_at = res.created_at;
  } catch (err) {
    console.error("[加载用户信息失败]", err);
  }
}

// ── 更新个人信息 ──
async function updateProfile() {
  profileLoading.value = true;
  try {
    await request.put("/user/profile", null, {
      params: {
        email: profileForm.email,
        phone: profileForm.phone,
      },
    });
    ElMessage.success("个人信息已更新");
  } catch (err) {
    console.error("[更新个人信息失败]", err);
  } finally {
    profileLoading.value = false;
  }
}

// ── 修改密码 ──
async function changePassword() {
  // 表单验证
  const valid = await passwordFormRef.value.validate().catch(() => false);
  if (!valid) return;

  passwordLoading.value = true;
  try {
    await request.put("/user/password", null, {
      params: {
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password,
      },
    });
    ElMessage.success("密码修改成功，请重新登录");
    resetPasswordForm();
  } catch (err) {
    console.error("[修改密码失败]", err);
  } finally {
    passwordLoading.value = false;
  }
}

// ── 重置密码表单 ──
function resetPasswordForm() {
  passwordForm.old_password = "";
  passwordForm.new_password = "";
  passwordForm.confirm_password = "";
  passwordFormRef.value?.resetFields();
}

onMounted(() => {
  loadUserInfo();
});
</script>

<style lang="scss" scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 18px 20px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(248, 250, 253, 0.72));
  border: 1px solid rgba(78, 103, 138, 0.14);
  border-radius: 12px;
  box-shadow: 0 10px 28px rgba(20, 33, 56, 0.06);

  h2 {
    margin: 0;
    font-size: 24px;
    color: $text-primary;
  }

  p {
    margin: 0;
    color: $text-secondary;
  }
}

:deep(.el-card) {
  border-radius: 12px;
}

.settings-card {
  height: 100%;

  :deep(.el-card__header) {
    position: relative;
    padding-left: 20px;

    &::before {
      position: absolute;
      top: 50%;
      left: 10px;
      width: 3px;
      height: 18px;
      content: '';
      background: $primary-color;
      border-radius: 999px;
      transform: translateY(-50%);
    }
  }
}

.profile-card {
  :deep(.el-card__header::before) {
    background: $primary-color;
  }
}

.password-card {
  :deep(.el-card__header::before) {
    background: $warning-color;
  }
}

.about-card {
  margin-top: 6px;

  :deep(.el-card__header::before) {
    background: $info-color;
  }
}

@media (max-width: 960px) {
  :deep(.el-col) {
    width: 100%;
    max-width: 100%;
    flex: 0 0 100%;
  }
}
</style>
