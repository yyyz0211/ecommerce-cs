import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'

/*
 * React 应用的入口文件
 *
 * 【流程】
 * 1. 找到 index.html 里的 <div id="root"></div>
 * 2. 把我们写的 App 组件渲染进去
 * 3. BrowserRouter 提供路由功能（URL 变化时切换页面）
 * 4. StrictMode 在开发时帮我们发现潜在问题
 *
 * 【为什么包裹 BrowserRouter？】
 * React Router 需要知道当前 URL 是什么，BrowserRouter 用浏览器原生
 * History API 来管理 URL，让页面切换不刷新整个页面（SPA 的核心特性）
 */
/*
 * React 应用的入口文件
 *
 * 【流程】
 * 1. 找到 index.html 里的 <div id="root"></div>
 * 2. 把我们写的 App 组件渲染进去
 * 3. BrowserRouter 提供路由功能（URL 变化时切换页面）
 * 4. StrictMode 在开发时帮我们发现潜在问题
 *
 * 【为什么包裹 BrowserRouter？】
 * React Router 需要知道当前 URL 是什么，BrowserRouter 用浏览器原生
 * History API 来管理 URL，让页面切换不刷新整个页面（SPA 的核心特性）
 */
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
