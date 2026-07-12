import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { createApp } from "vue";

import "@/assets/styles/global.scss";
import { setupErrorReporting } from "@/utils/errorReporter";
import App from "./App.vue";
import router from "./router";
import pinia from "./stores";

const app = createApp(App);

setupErrorReporting(app);

app.use(pinia);
app.use(router);
app.use(ElementPlus, { locale: zhCn });

app.mount("#app");
