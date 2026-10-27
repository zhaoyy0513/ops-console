import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 开发期把 /api 代理到本地后端（生产由 ops-nginx 反代，T31）。
    // OPS_API_TARGET 可覆盖代理目标（多后端并行调试时用，如指向未占端口的新实例）
    proxy: {
      '/api': process.env.OPS_API_TARGET || 'http://127.0.0.1:25088',
    },
  },
})
