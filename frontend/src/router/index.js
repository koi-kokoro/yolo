import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '@/components/layout/MainLayout.vue'
import { useUserStore } from '@/stores/user'

const appTitle = import.meta.env.VITE_APP_TITLE || 'RSOD Agent Platform'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginPage.vue'),
    meta: { title: '登录', guestOnly: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterPage.vue'),
    meta: { title: '注册', guestOnly: true },
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/chat',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardPage.vue'),
        meta: { title: '仪表盘', requiresAuth: true },
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/ChatPage.vue'),
        meta: { title: '智能对话', requiresAuth: true },
      },
      {
        path: 'detection',
        name: 'Detection',
        component: () => import('@/views/DetectionPage.vue'),
        meta: { title: '语义分割', requiresAuth: true },
      },
      {
        path: 'training',
        name: 'Training',
        component: () => import('@/views/TrainingPage.vue'),
        meta: { title: '模型管理', requiresAuth: true },
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/HistoryPage.vue'),
        meta: { title: '历史记录', requiresAuth: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const userStore = useUserStore()

  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  if (to.meta.guestOnly && userStore.isLoggedIn) {
    return { name: 'Chat' }
  }

  if (userStore.isLoggedIn && !userStore.user) {
    await userStore.fetchUserInfo().catch(() => userStore.logout())

    if (!userStore.isLoggedIn && to.meta.requiresAuth) {
      return { name: 'Login', query: { redirect: to.fullPath } }
    }
  }

  return true
})

router.afterEach((to) => {
  const pageTitle = to.meta.title ? `${to.meta.title} - ${appTitle}` : appTitle
  document.title = pageTitle
})

export default router
