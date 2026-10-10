import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 开发模式下把 API 请求代理到 Python 后端，前端无需关心跨域
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // 第三方库单独分包（v1.8.2，CODE_REVIEW.md B8）：
        // 框架与 Markdown 渲染的更新频率远低于业务代码，分开后能长期命中浏览器缓存。
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          markdown: ['marked', 'dompurify'],
        },
      },
    },
  },
})
