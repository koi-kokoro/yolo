import { getUserInfoApi, loginApi } from "@/api/auth";
import { defineStore } from "pinia";

const TOKEN_KEY = "rsod_token";
const USER_KEY = "rsod_user";

export const useUserStore = defineStore("user", {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    username: (state) => state.user?.username || "",
    avatar: (state) => state.user?.avatar || "",
    roles: (state) => state.user?.roles || [],
    isSuperuser: (state) => state.user?.is_superuser || false,
  },

  actions: {
    async login(credentials) {
      const res = await loginApi(credentials);

      this.token = res.access_token;
      localStorage.setItem(TOKEN_KEY, res.access_token);

      this.user = res.user;
      localStorage.setItem(USER_KEY, JSON.stringify(res.user));

      return res;
    },

    async fetchUserInfo() {
      try {
        const user = await getUserInfoApi();
        this.user = user;
        localStorage.setItem(USER_KEY, JSON.stringify(user));
      } catch {
        this.logout();
      }
    },

    logout() {
      this.token = "";
      this.user = null;
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },
  },
});
