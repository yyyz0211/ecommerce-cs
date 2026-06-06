import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/*
 * Vite 配置文件
 *
 * 【什么是 Vite？】
 * Vite 是前端构建工具：
 * 1. 开发时启动一个本地服务器（localhost:5173）
 * 2. 自动刷新浏览器（改了代码立刻看到效果）
 * 3. 打包时把 JS/CSS 压缩优化
 *
 * 【proxy 是什么？】
 * 前端运行在 localhost:5173，后端在 localhost:8000
 * 浏览器默认不允许跨域请求（安全策略）
 * proxy 让 Vite 开发服务器做"中间人"：
 *   浏览器 → localhost:5173/api/... → Vite 转发 → localhost:8000/api/...
 *
 * 这样前端代码里写 "/api/users/me" 就行，不用写完整 URL
 */
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // 后端地址
        changeOrigin: true,
      },
    },
  },
})
