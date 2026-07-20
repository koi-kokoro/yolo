<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const formRef = ref()

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [
    { required: true, message: '请输入用户名或邮箱', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度为 3-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 个字符', trigger: 'blur' },
  ],
}

async function handleSubmit() {
  await formRef.value?.validate()
  loading.value = true

  try {
    await userStore.login(form)
    router.push(route.query.redirect || '/chat')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-card">
      <div class="auth-card__brand">
        <span class="auth-card__mark">AI</span>
        <div>
          <p class="auth-kicker">RSOD AGENT PLATFORM</p>
          <h1 class="auth-title">登录平台</h1>
        </div>
      </div>
      <p class="auth-subtitle">使用已注册账号进入遥感智能分析工作台。</p>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="handleSubmit">
        <el-form-item label="用户名或邮箱" prop="username">
          <el-input v-model.trim="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-button type="primary" :loading="loading" class="auth-submit" @click="handleSubmit">登录</el-button>
      </el-form>
      <div class="auth-actions">
        <span>还没有账号</span>
        <RouterLink to="/register">立即注册</RouterLink>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.auth-submit {
  width: 100%;
  margin-top: 6px;
}

.auth-actions a {
  color: $primary-color;
  font-weight: 600;
}
</style>
