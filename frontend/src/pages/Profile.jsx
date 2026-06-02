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
    setError(''); setSuccess('');
    try {
      setLoading(true);
      await updateMyInfo({ phone: phone || null, default_address: address || null });
      const token = localStorage.getItem('token');
      if (token) await loginUser(token);
      setEditing(false); setSuccess('保存成功');
    } catch(e) { setError(e.message); }
    finally { setLoading(false); }
  }

  return (
    <div style={{maxWidth:600,margin:'0 auto',padding:20}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:20}}>
        <div style={{display:'flex',alignItems:'center',gap:16}}>
          <span onClick={()=>navigate('/chat')} style={{cursor:'pointer',fontSize:13,color:'#1f93ff'}}>← 返回对话</span>
          <h2 style={{fontSize:20,fontWeight:700}}>个人信息</h2>
        </div>
        <button className="btn btn-sm btn-secondary" onClick={()=>{logoutUser();navigate('/login')}}>退出</button>
      </div>

      {error && <div className="error-msg">{error}</div>}
      {success && <div className="success-msg">{success}</div>}

      <div className="card">
        {editing ? (
          <div>
            <div className="form-group"><label>手机号</label><input type="text" value={phone} onChange={e=>setPhone(e.target.value)} /></div>
            <div className="form-group"><label>收货地址</label><input type="text" value={address} onChange={e=>setAddress(e.target.value)} /></div>
            <div className="flex-between gap-2">
              <button className="btn btn-primary" onClick={handleSave} disabled={loading}>{loading?'保存中...':'保存'}</button>
              <button className="btn btn-secondary" onClick={()=>{setEditing(false);setPhone(user?.phone||'');setAddress(user?.default_address||'');setError('')}}>取消</button>
            </div>
          </div>
        ) : (
          <div style={{fontSize:14,lineHeight:2.2}}>
            <div className="profile-info-row"><span className="profile-label">用户名</span><span>{user?.username}</span></div>
            <div className="profile-info-row"><span className="profile-label">手机号</span><span>{user?.phone||'未设置'}</span></div>
            <div className="profile-info-row"><span className="profile-label">地址</span><span>{user?.default_address||'未设置'}</span></div>
            <div className="profile-info-row"><span className="profile-label">注册时间</span><span>{user?.created_at?new Date(user.created_at).toLocaleString():'-'}</span></div>
            <button className="btn btn-sm btn-primary mt-3" onClick={()=>setEditing(true)}>编辑资料</button>
          </div>
        )}
      </div>
    </div>
  );
}
