import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import AppIcon from '@/components/AppIcon.vue'
import '@/styles/global.css'
import 'vant/lib/index.css'

const app = createApp(App)
app.component('AppIcon', AppIcon)   // 全局图标组件（内联 SVG，不依赖字体）
app.use(createPinia())
app.use(router)
app.mount('#app')
