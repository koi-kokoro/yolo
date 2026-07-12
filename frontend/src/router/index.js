import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/login",
    name: "Login",
    component: () => import("@/views/LoginPage.vue"),
    meta: { public: true },
  },
  {
    path: "/register",
    name: "Register",
    component: () => import("@/views/RegisterPage.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: () => import("@/components/layout/MainLayout.vue"),
    redirect: "/chat",
    children: [
      {
        path: "chat",
        name: "Chat",
        component: () => import("@/views/ChatPage.vue"),
        meta: { title: "智能对话" },
      },
      {
        path: "detection",
        name: "Detection",
        component: () => import("@/views/DetectionPage.vue"),
        meta: { title: "检测工作台" },
      },
      {
        path: "training",
        name: "Training",
        component: () => import("@/views/TrainingPage.vue"),
        meta: { title: "模型训练" },
      },
      {
        path: "history",
        name: "History",
        component: () => import("@/views/HistoryPage.vue"),
        meta: { title: "历史记录" },
      },
      {
        path: "dashboard",
        name: "Dashboard",
        component: () => import("@/views/DashboardPage.vue"),
        meta: { title: "数据看板" },
      },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/chat",
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const token = localStorage.getItem("rsod_token");

  if (!to.meta.public && !token) {
    return {
      path: "/login",
      query: { redirect: to.fullPath },
    };
  }

  if (to.meta.public && token) {
    return "/chat";
  }

  return true;
});

export default router;
