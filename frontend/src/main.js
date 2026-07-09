import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import { createAppPinia } from './stores'
import { setupErrorReporting } from './utils/errorReporter'
import './assets/styles/reset.scss'
import './assets/styles/global.scss'

const app = createApp(App)

setupErrorReporting(app)
app.use(createAppPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
