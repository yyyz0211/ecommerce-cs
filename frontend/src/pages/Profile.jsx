import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { updateMyInfo } from '../api';

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
      await updateMyInfo({ phone: phone || null, default_address: address || null });
      const token = localStorage.getItem('token');
      if (token) await loginUser(token);
      setEditing(false);
      setSuccess('保存成功');
    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-page">
      <div className="app-shell narrow">
        <header className="app-page-header">
          <button className="back-link" onClick={() => navigate('/chat')}>返回对话</button>
          <div className="page-heading">
            <p>Profile</p>
            <h1>个人信息</h1>
          </div>
          <button className="btn btn-sm btn-secondary" onClick={() => { logoutUser(); navigate('/login'); }}>退出</button>
        </header>

        {error && <div className="error-msg">{error}</div>}
        {success && <div className="success-msg">{success}</div>}

        <section className="soft-card profile-card">
          <div className="profile-avatar">{(user?.username || 'U').slice(0, 1).toUpperCase()}</div>
          <h2>{user?.username}</h2>
          <p>{user?.phone || '未设置手机号'}</p>

          {editing ? (
            <div className="profile-edit">
              <div className="form-group"><label>手机号</label><input type="text" value={phone} onChange={e => setPhone(e.target.value)} /></div>
              <div className="form-group"><label>收货地址</label><input type="text" value={address} onChange={e => setAddress(e.target.value)} /></div>
              <div className="profile-actions">
                <button className="btn btn-primary" onClick={handleSave} disabled={loading}>{loading ? '保存中...' : '保存'}</button>
                <button className="btn btn-secondary" onClick={() => { setEditing(false); setPhone(user?.phone || ''); setAddress(user?.default_address || ''); setError(''); }}>取消</button>
              </div>
            </div>
          ) : (
            <>
              <div className="profile-info-list">
                <div><span>用户名</span><strong>{user?.username}</strong></div>
                <div><span>手机号</span><strong>{user?.phone || '未设置'}</strong></div>
                <div><span>地址</span><strong>{user?.default_address || '未设置'}</strong></div>
                <div><span>注册时间</span><strong>{user?.created_at ? new Date(user.created_at).toLocaleString() : '-'}</strong></div>
              </div>
              <button className="btn btn-primary mt-3" onClick={() => setEditing(true)}>编辑资料</button>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
