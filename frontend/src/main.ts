import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { i18n } from './i18n'
import App from './App.vue'
import router from './router'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './assets/main.css'
import './assets/main.css'
import './style.css'
import 'vue-sonner/style.css'

createApp(App).use(createPinia()).use(i18n).use(router).mount('#app')
