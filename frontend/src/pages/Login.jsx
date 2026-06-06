import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { login as apiLogin } from '../api';

/*
 * Login 页面
 *
 * 【受控组件】
 * React 中表单输入不是直接读 DOM，而是用 state 管理值：
 * 1. 用户输入 → onChange → setUsername(e.target.value) → 更新 state
 * 2. 渲染时 <input value={username}> → 显示最新的 state
 * 这保证"界面始终 = state"，数据流单向可控
 *
 * 【async/await 流程】
 * 1. setLoading(true)  → 按钮变灰、显示"登录中..."
 * 2. await apiLogin()  → 等后端返回
 * 3. loginUser(token)  → 保存 token + 跳转
 * 4. catch 设置 error   → 显示错误信息
 * 5. finally            → setLoading(false)，按钮恢复
 */

export default function Login() {
  const { loginUser } = useAuth();  // 从 Context 拿 loginUser 函数
  const [username, setUsername] = useState('');   // 用户名输入框的值
  const [password, setPassword] = useState('');   // 密码输入框的值
  const [error, setError] = useState('');          // 错误提示信息
  const [loading, setLoading] = useState(false);   // 是否正在提交

  async function handleSubmit(e) {
    e.preventDefault();  // 阻止表单默认提交（会刷新页面）
    setError('');

    try {
      setLoading(true);
      const data = await apiLogin(username, password);
      await loginUser(data.access_token);
      // 登录成功后 React Router 会自动根据路由守卫跳到 /chat
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>电商客服系统</h1>
        <p className="subtitle">登录您的账号开始使用</p>

        {error && <div className="error-msg">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              required
            />
          </div>

          <div className="form-group">
            <label>密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '登录中...' : '登录'}
          </button>
        </form>

        <div className="link">
          还没有账号？<Link to="/register">立即注册</Link>
        </div>
      </div>
    </div>
  );
}
