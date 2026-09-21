import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    // 开发期把 /api 代理到本地后端（生产由 ops-nginx 反代，T31）
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
