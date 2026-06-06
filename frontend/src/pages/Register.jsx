import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register } from '../api';

/*
 * Register 页面
 *
 * 和 Login 结构几乎一样，只是多了一个手机号字段
 *
 * 【useNavigate】
 * react-router-dom 提供的 Hook，用于"代码触发跳转"
 * 注册成功后跳转到 /login 而不是自动登录，
 * 让用户感受两次操作的区别
 */

export default function Register() {
  const navigate = useNavigate();  // 用于代码跳转
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (password.length < 6) {
      setError('密码至少 6 位');
      return;
    }

    try {
      setLoading(true);
      await register(username, password, phone || null);
      // 成功后跳转到登录页
      navigate('/login', { state: { message: '注册成功，请登录' } });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>注册新账号</h1>
        <p className="subtitle">创建账号开始购物</p>

        {error && <div className="error-msg">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="2-50 个字符"
              required
            />
          </div>

          <div className="form-group">
            <label>密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 6 位"
              required
            />
          </div>

          <div className="form-group">
            <label>手机号（选填）</label>
            <input
              type="text"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="选填"
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '注册中...' : '注册'}
          </button>
        </form>

        <div className="link">
          已有账号？<Link to="/login">去登录</Link>
        </div>
      </div>
    </div>
  );
}
