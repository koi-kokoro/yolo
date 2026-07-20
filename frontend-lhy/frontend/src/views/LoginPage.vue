<template>
  <div class="login-page">
    <div class="grid-background"></div>
    <div class="map-outline"></div>
    <div class="gradient-overlay"></div>

    <div class="login-content">
      <div class="login-left">
        <div class="left-card">
          <div class="card-shine"></div>
          
          <div class="brand-section">
            <div class="brand-logo">
              <span>🌾</span>
            </div>
            <h1 class="brand-title">RSOD</h1>
            <h2 class="brand-subtitle">目标检测智能体</h2>
            <p class="brand-description">基于遥感影像的土地类型识别与变化监测系统</p>
          </div>
          
          <div class="feature-grid">
            <div class="feature-card">
              <div class="feature-icon earth-primary">
                <span>📷</span>
              </div>
              <div class="feature-info">
                <div class="feature-name">高分辨率识别</div>
                <div class="feature-desc">精准识别土地利用类型</div>
              </div>
            </div>
            <div class="feature-card">
              <div class="feature-icon earth-success">
                <span>📊</span>
              </div>
              <div class="feature-info">
                <div class="feature-name">多维度分析</div>
                <div class="feature-desc">提供全面数据洞察</div>
              </div>
            </div>
            <div class="feature-card">
              <div class="feature-icon earth-warning">
                <span>🗺️</span>
              </div>
              <div class="feature-info">
                <div class="feature-name">边界提取</div>
                <div class="feature-desc">自动识别地块边界</div>
              </div>
            </div>
            <div class="feature-card">
              <div class="feature-icon earth-danger">
                <span>📈</span>
              </div>
              <div class="feature-info">
                <div class="feature-name">趋势监控</div>
                <div class="feature-desc">实时追踪变化趋势</div>
              </div>
            </div>
          </div>

          <div class="tips-section">
            <span class="tips-icon">💡</span>
            <span>提示：登录后可进行图片检测与数据分析</span>
          </div>
        </div>
      </div>

      <div class="login-right">
        <div class="login-card">
          <div class="card-shine"></div>
          
          <div class="login-body">
            <div class="login-header">
              <h2>欢迎登录</h2>
              <p>请登录您的账户</p>
            </div>

            <form ref="formRef" @submit.prevent="handleLogin" class="login-form">
              <div class="form-item">
                <div class="input-wrapper">
                  <span class="input-icon">👤</span>
                  <input
                    v-model="loginForm.username"
                    type="text"
                    placeholder="用户名"
                    class="login-input"
                  />
                </div>
                <span v-if="errors.username" class="error-message">{{ errors.username }}</span>
              </div>

              <div class="form-item">
                <div class="input-wrapper">
                  <span class="input-icon">🔒</span>
                  <input
                    v-model="loginForm.password"
                    :type="showPassword ? 'text' : 'password'"
                    placeholder="密码"
                    class="login-input"
                    @keyup.enter="handleLogin"
                  />
                  <button
                    type="button"
                    class="toggle-password"
                    @click="showPassword = !showPassword"
                  >
                    <svg v-if="!showPassword" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                      <line x1="12" y1="1" x2="12" y2="3"/>
                      <line x1="12" y1="21" x2="12" y2="23"/>
                      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                      <line x1="1" y1="12" x2="3" y2="12"/>
                      <line x1="21" y1="12" x2="23" y2="12"/>
                      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                    </svg>
                  </button>
                </div>
                <span v-if="errors.password" class="error-message">{{ errors.password }}</span>
              </div>

              <div class="form-item btn-item">
                <button
                  class="login-btn"
                  :disabled="loading"
                  type="submit"
                >
                  <span v-if="loading" class="btn-loading"></span>
                  <span>{{ loading ? '登录中...' : '登 录' }}</span>
                </button>
              </div>
            </form>

            <div class="login-footer">
              <span>还没有账号？</span>
              <router-link to="/register">立即注册</router-link>
            </div>
          </div>

          <div class="copyright">
            <p>RSOD 目标检测智能体 © 2026</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)
const showPassword = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
})

const errors = reactive({
  username: '',
  password: '',
})

function validateForm() {
  errors.username = ''
  errors.password = ''
  
  if (!loginForm.username) {
    errors.username = '请输入用户名'
    return false
  }
  if (loginForm.username.length < 3 || loginForm.username.length > 50) {
    errors.username = '用户名长度为 3-50 个字符'
    return false
  }
  
  if (!loginForm.password) {
    errors.password = '请输入密码'
    return false
  }
  if (loginForm.password.length < 6) {
    errors.password = '密码至少 6 个字符'
    return false
  }
  
  return true
}

async function handleLogin() {
  if (!validateForm()) return

  loading.value = true
  try {
    await userStore.login({
      username: loginForm.username,
      password: loginForm.password,
    })

    ElMessage.success('登录成功')

    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } catch {
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.login-page {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #1a1510 0%, #0d0d0f 50%, #1a1510 100%);
  position: relative;
  overflow: hidden;
}

.grid-background {
  position: absolute;
  inset: 0;
  background-image: 
    linear-gradient(rgba(218, 165, 32, 0.1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(218, 165, 32, 0.1) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.8;
}

.map-outline {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 1200 800' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M100,200 Q200,150 300,180 T500,160 T700,200 T900,180 T1100,220' fill='none' stroke='rgba(218,165,32,0.25)' stroke-width='1.5'/%3E%3Cpath d='M150,350 Q250,300 350,330 T550,310 T750,350 T950,330 T1050,370' fill='none' stroke='rgba(218,165,32,0.2)' stroke-width='1.5'/%3E%3Cpath d='M200,500 Q300,450 400,480 T600,460 T800,500 T1000,480' fill='none' stroke='rgba(218,165,32,0.15)' stroke-width='1.5'/%3E%3Cpath d='M100,600 Q200,550 350,580 T600,560 T850,600 T1100,580' fill='none' stroke='rgba(218,165,32,0.12)' stroke-width='1.5'/%3E%3Ccircle cx='300' cy='250' r='150' fill='none' stroke='rgba(218,165,32,0.1)' stroke-width='1.5'/%3E%3Ccircle cx='700' cy='450' r='200' fill='none' stroke='rgba(218,165,32,0.08)' stroke-width='1.5'/%3E%3Ccircle cx='900' cy='600' r='100' fill='none' stroke='rgba(218,165,32,0.06)' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
  background-size: cover;
  opacity: 0.7;
}

.gradient-overlay {
  position: absolute;
  inset: 0;
  background: 
    radial-gradient(ellipse at 20% 30%, rgba(218, 165, 32, 0.2) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 70%, rgba(184, 134, 11, 0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 50%, rgba(218, 165, 32, 0.08) 0%, transparent 70%);
  animation: overlay-pulse 10s ease-in-out infinite;
}

@keyframes overlay-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.8; }
}

.login-content {
  display: flex;
  width: 100%;
  max-width: 1200px;
  gap: 0;
  padding: 40px;
  position: relative;
  z-index: 1;
  align-items: stretch;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: center;
    gap: 0;
  }
}

.login-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;

  @media (max-width: 768px) {
    text-align: center;
  }
}

.left-card {
  padding: 48px 40px;
  background: rgba(15, 13, 10, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 20px 0 0 20px;
  border: 2px solid rgba(218, 165, 32, 0.3);
  border-right: none;
  box-shadow: 
    0 25px 50px rgba(0, 0, 0, 0.7),
    0 0 80px rgba(218, 165, 32, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
  position: relative;
  overflow: hidden;
  height: 100%;
  min-height: 560px;
  display: flex;
  flex-direction: column;

  @media (max-width: 768px) {
    border-radius: 20px 20px 0 0;
    border-right: 2px solid rgba(218, 165, 32, 0.3);
    min-height: auto;
  }
}

.card-shine {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(218, 165, 32, 0.5) 50%, transparent 100%);
  pointer-events: none;
}

.brand-section {
  text-align: center;
  margin-bottom: 32px;
}

.brand-logo {
  width: 100px;
  height: 100px;
  background: linear-gradient(135deg, #DAA520 0%, #8B7355 50%, #A68B67 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  margin: 0 auto 24px;
  box-shadow: 
    0 12px 32px rgba(139, 115, 85, 0.4),
    0 0 60px rgba(218, 165, 32, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.brand-title {
  font-size: 48px;
  font-weight: 800;
  color: #ffffff;
  margin: 0 0 8px;
  letter-spacing: -1px;
  text-shadow: 0 0 40px rgba(218, 165, 32, 0.3);
}

.brand-subtitle {
  font-size: 20px;
  font-weight: 500;
  color: #DAA520;
  margin: 0 0 12px;
  letter-spacing: 2px;
}

.brand-description {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
  line-height: 1.6;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 28px;
  flex: 1;
}

.feature-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 16px;
  background: rgba(35, 30, 25, 0.8);
  border: 1px solid rgba(139, 115, 85, 0.35);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  transition: all 0.25s ease;

  &:hover {
    background: rgba(35, 30, 25, 0.95);
    border-color: rgba(139, 115, 85, 0.5);
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
  }
}

.feature-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 22px;

  &.earth-primary {
    background: rgba(139, 115, 85, 0.15);
    color: #8B7355;
  }

  &.earth-success {
    background: rgba(107, 142, 35, 0.15);
    color: #6B8E23;
  }

  &.earth-warning {
    background: rgba(218, 165, 32, 0.15);
    color: #DAA520;
  }

  &.earth-danger {
    background: rgba(205, 92, 92, 0.15);
    color: #CD5C5C;
  }
}

.feature-info {
  flex: 1;
  min-width: 0;
}

.feature-name {
  font-size: 14px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
}

.feature-desc {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 4px;
}

.tips-section {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 20px;
  background: rgba(218, 165, 32, 0.08);
  border-radius: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
}

.tips-icon {
  font-size: 14px;
}

.login-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.login-card {
  width: 100%;
  padding: 48px 48px;
  background: rgba(15, 13, 10, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 0 20px 20px 0;
  border: 2px solid rgba(218, 165, 32, 0.3);
  border-left: none;
  box-shadow: 
    0 25px 50px rgba(0, 0, 0, 0.7),
    0 0 80px rgba(218, 165, 32, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
  position: relative;
  overflow: hidden;
  height: 100%;
  min-height: 560px;
  display: flex;
  flex-direction: column;

  @media (max-width: 768px) {
    border-radius: 0 0 20px 20px;
    border-left: 2px solid rgba(218, 165, 32, 0.3);
    min-height: auto;
  }
}

.login-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 20px 0;
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
  flex-shrink: 0;
}

.login-header h2 {
  font-size: 26px;
  font-weight: 600;
  color: #ffffff;
  margin: 0 0 8px;
}

.login-header p {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.4);
  margin: 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
  flex: 1;
  justify-content: center;
}

.form-item {
  display: flex;
  flex-direction: column;
}

.btn-item {
  margin-top: 16px;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  background-color: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(218, 165, 32, 0.3);
  border-radius: 10px;
  padding: 0 18px;
  height: 52px;
  transition: all 0.25s ease;

  &:hover {
    border-color: rgba(218, 165, 32, 0.5);
  }

  &:focus-within {
    border-color: #DAA520;
    box-shadow: 0 0 0 3px rgba(218, 165, 32, 0.15);
  }
}

.input-icon {
  font-size: 18px;
  color: rgba(218, 165, 32, 0.6);
  margin-right: 14px;
  flex-shrink: 0;
}

.login-input {
  flex: 1;
  height: 100%;
  background-color: transparent;
  border: none;
  outline: none;
  color: #ffffff;
  font-size: 15px;

  &::placeholder {
    color: rgba(255, 255, 255, 0.35);
  }

  &:-webkit-autofill,
  &:-webkit-autofill:hover,
  &:-webkit-autofill:focus,
  &:-webkit-autofill:active {
    -webkit-box-shadow: 0 0 0 1000px rgba(0, 0, 0, 0.4) inset !important;
    -webkit-text-fill-color: #ffffff !important;
    caret-color: #DAA520 !important;
    transition: background-color 5000s ease-in-out 0s;
  }
}

.toggle-password {
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  color: rgba(218, 165, 32, 0.5);
  transition: color 0.2s ease;

  &:hover {
    color: #DAA520;
  }
}

.error-message {
  display: block;
  color: #CD5C5C;
  font-size: 12px;
  margin-top: 8px;
}

.login-btn {
  width: 100%;
  height: 52px;
  background: linear-gradient(135deg, #DAA520 0%, #8B7355 50%, #A68B67 100%);
  border: none;
  border-radius: 10px;
  color: #0d0d0f;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 2px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  box-shadow: 0 6px 24px rgba(218, 165, 32, 0.4);
  transition: all 0.25s ease;

  &:hover:not(:disabled) {
    background: linear-gradient(135deg, #FFD700 0%, #DAA520 50%, #C4A87A 100%);
    box-shadow: 0 8px 30px rgba(218, 165, 32, 0.5);
    transform: translateY(-2px);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .btn-loading {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(0, 0, 0, 0.3);
    border-top-color: #0d0d0f;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-footer {
  text-align: center;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.4);
  margin-top: auto;
  padding-top: 20px;

  a {
    color: #DAA520;
    margin-left: 4px;
    text-decoration: none;
    transition: color 0.2s ease;

    &:hover {
      color: #FFD700;
      text-decoration: underline;
    }
  }
}

.copyright {
  text-align: center;
  padding-top: 16px;
  border-top: 1px solid rgba(218, 165, 32, 0.1);
  margin-top: 16px;

  p {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.2);
    margin: 0;
  }
}
</style>
