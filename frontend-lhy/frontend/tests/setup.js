/**
 * Vitest 全局 setup
 * 在每个测试文件执行前自动运行
 */

import { vi } from "vitest";

vi.mock("element-plus", async () => {
  const actual = await vi.importActual("element-plus");
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    },
  };
});

vi.mock("@/stores/user", () => ({
  useUserStore: vi.fn(() => ({
    username: "testuser",
    avatar: undefined,
    logout: vi.fn(),
  })),
}));

vi.mock("vue-router", () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
  })),
  createRouter: vi.fn(() => ({
    install: vi.fn(),
    beforeEach: vi.fn(),
  })),
  createWebHistory: vi.fn(),
}));

vi.mock("@element-plus/icons-vue", () => ({
  ArrowDown: vi.fn(),
  User: vi.fn(),
  SwitchButton: vi.fn(),
}));