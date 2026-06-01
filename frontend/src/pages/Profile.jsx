import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { updateMyInfo } from '../api';

/*
 * Profile 页面
 *
 * 功能：查看个人信息、修改手机号和收货地址
 * 特点：编辑状态和查看状态切换用 editing 变量控制
 */

export default function Profile() {
  const { user, loginUser, logoutUser } = useAuth();
  const navigate = useNavigate();

  const [editing, setEditing] = useState(false);
  const [phone, setPhone] = useState(user?.phone || '');
  const [address, setAddress] = useState(user?.default_address || '');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSave() {
    setError('');
    setSuccess('');
    try {
      setLoading(true);
      const data = { phone: phone || null, default_address: address || null };
      await updateMyInfo(data);
      // 更新 Context 中的用户信息，同步页面显示
      const token = localStorage.getItem('token');
      if (token) await loginUser(token);
      setEditing(false);
      setSuccess('保存成功');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    logoutUser();
    navigate('/login');
  }

  return (
    <div>
      <nav className="navbar">
        <div className="navbar-left">
          <span className="navbar-logo">客服系统</span>
          <NavLink to="/chat">对话</NavLink>
          <NavLink to="/orders">订单</NavLink>
          <NavLink to="/after-sales">售后</NavLink>
          <NavLink to="/profile" className={({ isActive }) => isActive ? 'active' : ''}>我的</NavLink>
        </div>
        <div className="navbar-right">
          <span>{user?.username}</span>
          <button className="btn-logout" onClick={handleLogout}>退出</button>
        </div>
      </nav>

      <div className="page">
        <div className="card">
          <div className="flex-between">
            <h2 style={{ fontSize: 18 }}>个人信息</h2>
            {!editing && (
              <button className="btn btn-sm btn-primary" onClick={() => setEditing(true)}>
                编辑
              </button>
            )}
          </div>

          {error && <div className="error-msg">{error}</div>}
          {success && <div className="success-msg">{success}</div>}

          {editing ? (
            /* 编辑模式 */
            <div style={{ marginTop: 16 }}>
              <div className="form-group">
                <label>手机号</label>
                <input
                  type="text"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>默认收货地址</label>
                <input
                  type="text"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                />
              </div>
              <div className="flex-between gap-2">
                <button className="btn btn-primary" onClick={handleSave} disabled={loading}>
                  {loading ? '保存中...' : '保存'}
                </button>
                <button className="btn btn-secondary" onClick={() => {
                  setEditing(false);
                  setPhone(user?.phone || '');
                  setAddress(user?.default_address || '');
                  setError('');
                }}>
                  取消
                </button>
              </div>
            </div>
          ) : (
            /* 查看模式 */
            <div style={{ marginTop: 16, fontSize: 14, lineHeight: 2 }}>
              <p><strong>用户名：</strong>{user?.username}</p>
              <p><strong>手机号：</strong>{user?.phone || '未设置'}</p>
              <p><strong>收货地址：</strong>{user?.default_address || '未设置'}</p>
              <p style={{ color: '#999', fontSize: 12 }}>
                注册时间：{user?.created_at ? new Date(user.created_at).toLocaleString() : '-'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
