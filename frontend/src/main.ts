import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { i18n } from './i18n'
import App from './App.vue'
import router from './router'
import './style.css'

createApp(App).use(createPinia()).use(i18n).use(router).mount('#app')
