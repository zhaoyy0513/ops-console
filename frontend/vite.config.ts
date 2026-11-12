import { fileViewerRenderers } from '@file-viewer/vite-plugin'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // fileViewerRenderers：把 @file-viewer 的渲染资产拷到 dist/file-viewer/（知识库文档预览用）。
  // 只声明运维场景实际会传的格式——不声明则按已装 preset 全量拷贝（含 CAD/3D/Typst 的
  // 100MB+ WASM），内部工具不值得为此付体积。
  plugins: [
    vue(),
    tailwindcss(),
    fileViewerRenderers({
      formats: [
        'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'pptx', 'ppt', 'ofd',
        'txt', 'md', 'log', 'json', 'xml', 'yaml', 'html', 'htm',
        'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg',
        'mp4', 'webm', 'mp3', 'wav',
      ],
      copyAssets: true,
    }),
  ],
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
