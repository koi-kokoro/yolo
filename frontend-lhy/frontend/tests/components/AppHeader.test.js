import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import AppHeader from "@/components/layout/AppHeader.vue";

describe("AppHeader 组件", () => {
  it("组件文件应该存在", async () => {
    const wrapper = mount(AppHeader, {
      global: {
        stubs: {
          "el-dropdown": true,
          "el-dropdown-menu": true,
          "el-dropdown-item": true,
          "el-avatar": true,
          "el-icon": true,
        },
      },
    });
    expect(wrapper.exists()).toBe(true);
  });
});