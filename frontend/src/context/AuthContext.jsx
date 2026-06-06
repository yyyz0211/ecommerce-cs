import { createContext, useContext, useState, useEffect } from 'react';
import { getMyInfo } from '../api';

/*
 * AuthContext — 全局用户认证状态
 *
 * 【什么是 Context？】
 * React 中父子组件传值用 props，但如果很多页面都要知道"是否已登录"，
 * 每一层都传 props 会非常繁琐（这叫 prop drilling）。
 * Context 让任意深度的子组件都能直接读取数据，无需层层传递。
 *
 * 【这里存储什么？】
 * user:  当前用户信息（null = 未登录） → 用于显示用户名、校验权限
 * token: JWT 令牌（null = 未登录）    → 用于 API 请求
 * loading: 应用启动时正在恢复登录状态 → 防止闪烁
 *
 * 【流程】
 * 1. App 启动 → AuthProvider 检查 localStorage 有无 token
 * 2. 有 token → 调用 /api/users/me 验证 → 成功则设置 user
 * 3. 无 token 或验证失败 → 显示登录页
 * 4. 登录成功后 → setUser + setToken → 所有使用 useAuth() 的组件自动更新
 */

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);      // 【useState】React 的状态变量，值变化时自动重新渲染
  const [loading, setLoading] = useState(true); // 初始为 true，表示"正在检查登录状态"

  // 【useEffect】组件挂载时执行一次，[] 表示不依赖任何值变化
  useEffect(() => {
    // 页面刷新后尝试恢复登录状态
    const savedToken = localStorage.getItem('token');
    if (savedToken) {
      // 验证 token 是否还有效
      getMyInfo()
        .then((data) => {
          setUser(data);  // token 有效，设置用户信息
        })
        .catch(() => {
          // token 无效或过期，清除残留数据
          localStorage.removeItem('token');
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);  // 没有 token，直接结束 loading
    }
  }, []);

  // 登录：保存 token 到 localStorage + 设置内存中的 user
  function loginUser(tokenValue) {
    localStorage.setItem('token', tokenValue);
    // 立即拿用户信息
    return getMyInfo().then((data) => setUser(data));
  }

  // 退出：清除所有登录状态
  function logoutUser() {
    localStorage.removeItem('token');
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, loginUser, logoutUser }}>
      {children}
    </AuthContext.Provider>
  );
}

/*
 * useAuth() — 其他组件调用这个函数就能拿到 { user, loading, loginUser, logoutUser }
 * 不用这个 Hook 的话，每个组件都要写 useContext(AuthContext)
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth 必须在 AuthProvider 内部使用');
  }
  return context;
}
