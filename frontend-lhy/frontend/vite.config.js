import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
       "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },

  // ── CSS 预处理器配置 ──────────────────────────────
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/assets/styles/variables.scss" as *;`,
      },
    },
  },

  // ── 开发服务器配置 ────────────────────────────────
   server: {
    port: 5173,
    proxy: {
      // REST API 代理
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // WebSocket 代理（关键！）
      "/api/detection/camera": {
        target: "ws://localhost:8000",
        ws: true,  // 启用 WebSocket 代理
        changeOrigin: true,
      },
    },
  },

  // ── Vitest 测试配置 ───────────────────────────────
  test: {
    environment: "happy-dom",
    setupFiles: ["./tests/setup.js"],
    include: ["tests/**/*.{test,spec}.{js,ts}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
    },
  },
});