import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Register from './pages/Register';
import Chat from './pages/Chat';
import Orders from './pages/Orders';
import Profile from './pages/Profile';

/*
 * App.jsx — 应用的"骨架"
 *
 * 【什么是组件？】
 * React 中一切皆组件。一个函数返回 HTML（JSX），就是一个组件。
 * App 是根组件，它负责"路由"——根据浏览器 URL 决定显示哪个页面。
 *
 * 【什么是路由？】
 * 传统网站：/login → 服务器返回 login.html
 * SPA（单页应用）：/login → React 原地替换成 Login 组件，不刷新页面
 * 这里用 react-router-dom 来做这件事
 *
 * 【Routes / Route】的写法
 * <Routes> 里放多个 <Route>，URL 匹配到哪个就渲染哪个组件
 * path="*" 是兜底路由："一旦没匹配上，就跳到 /chat"
 *
 * 【ProtectedRoute 是什么？】
 * 某些页面必须登录才能看（如 /chat、/orders）
 * 如果未登录就访问，自动跳到 /login
 */

/** 路由守卫组件：检查是否已登录，未登录则重定向 */
function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  // loading 阶段不渲染任何内容，避免"已登录但闪现登录页"的问题
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/** 未登录才能访问的路由（登录/注册页），已登录就跳对话页 */
function GuestRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/chat" replace />;
  return children;
}

export default function App() {
  return (
    /*
     * AuthProvider 包裹整个应用，让所有子组件都能通过 useAuth() 读取登录状态
     * 【Props】<AuthProvider> 和 </AuthProvider> 之间的内容会作为 children 传入
     */
    <AuthProvider>
      <Routes>
        {/* 登录/注册：已登录用户访问时自动跳对话页 */}
        <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
        <Route path="/register" element={<GuestRoute><Register /></GuestRoute>} />

        {/* 需要登录的页面 */}
        <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
        <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />

        {/* 默认跳转到对话页 */}
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </AuthProvider>
  );
}
