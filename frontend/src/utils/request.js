import router from "@/router";
import { useUserStore } from "@/stores/user";
import axios from "axios";
import { ElMessage } from "element-plus";

const request = axios.create({
  baseURL: "/api",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

request.interceptors.request.use(
  (config) => {
    const userStore = useUserStore();
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const { response } = error;

    if (response) {
      switch (response.status) {
        case 401: {
          ElMessage.error("登录已过期，请重新登录");
          const userStore = useUserStore();
          userStore.logout();
          router.push({
            path: "/login",
            query: { redirect: router.currentRoute.value.fullPath },
          });
          break;
        }
        case 403:
          ElMessage.error("没有权限执行此操作");
          break;
        case 404:
          ElMessage.error("请求的资源不存在");
          break;
        case 422: {
          const detail = response.data?.detail;
          if (Array.isArray(detail)) {
            ElMessage.error(detail[0]?.msg || "参数验证失败");
          } else {
            ElMessage.error(detail || "参数验证失败");
          }
          break;
        }
        case 500:
          ElMessage.error("服务器内部错误");
          break;
        default:
          ElMessage.error(
            response.data?.detail || `请求失败 (${response.status})`,
          );
      }
    } else {
      ElMessage.error("网络连接异常，请检查后端服务是否启动");
    }

    return Promise.reject(error);
  },
);

export default request;
