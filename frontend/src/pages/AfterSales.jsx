import { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getAfterSales, getOrders, createAfterSale } from '../api';

/*
 * AfterSales 页面 — 我的售后
 *
 * 功能：
 *  1. 查看售后列表（提交过的退换货/退款记录）
 *  2. 提交新的售后申请（选择订单 + 类型 + 原因）
 */

export default function AfterSales() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();

  // ── 售后列表 ──
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // ── 新建售后表单 ──
  const [showForm, setShowForm] = useState(false);
  const [orders, setOrders] = useState([]);          // 可申请售后的订单列表
  const [selectedOrderId, setSelectedOrderId] = useState('');
  const [afterType, setAfterType] = useState('return');
  const [afterReason, setAfterReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadRecords();
    loadMyOrders();
  }, []);

  async function loadRecords() {
    setLoading(true);
    try {
      const data = await getAfterSales();
      setRecords(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // 加载所有订单（用于下拉选择，不做筛选，让用户自己判断）
  async function loadMyOrders() {
    try {
      const data = await getOrders(1, 100);
      setOrders(data.items || []);
    } catch (err) {
      console.error('加载订单失败：', err);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSuccess('');
    if (!selectedOrderId) { setError('请选择订单'); return; }
    if (!afterReason.trim()) { setError('请填写售后原因'); return; }

    setSubmitting(true);
    try {
      await createAfterSale(parseInt(selectedOrderId), afterType, afterReason.trim());
      setSuccess('售后申请已提交');
      setShowForm(false);
      setSelectedOrderId('');
      setAfterReason('');
      loadRecords();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  function handleLogout() {
    logoutUser();
    navigate('/login');
  }

  /* 类型中文 */
  function typeLabel(type) {
    return { return: '退货', refund: '退款', exchange: '换货' }[type] || type;
  }

  /* 状态中文 + CSS */
  function statusInfo(status) {
    const map = {
      pending:    { label: '待处理', cls: 'status-pending' },
      approved:   { label: '已通过', cls: 'status-delivered' },
      rejected:   { label: '已拒绝', cls: 'status-cancelled' },
      completed:  { label: '已完成', cls: 'status-delivered' },
    };
    return map[status] || { label: status, cls: '' };
  }

  return (
    <div>
      <nav className="navbar">
        <div className="navbar-left">
          <span className="navbar-logo">客服系统</span>
          <NavLink to="/chat">对话</NavLink>
          <NavLink to="/orders">订单</NavLink>
          <NavLink to="/after-sales" className={({ isActive }) => isActive ? 'active' : ''}>售后</NavLink>
          <NavLink to="/profile">我的</NavLink>
        </div>
        <div className="navbar-right">
          <span>{user?.username}</span>
          <button className="btn-logout" onClick={handleLogout}>退出</button>
        </div>
      </nav>

      <div className="page">
        <div className="flex-between">
          <h2 style={{ fontSize: 18 }}>我的售后（共 {records.length} 条）</h2>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => { setShowForm(!showForm); setError(''); setSuccess(''); }}
          >
            {showForm ? '收起' : '+ 申请售后'}
          </button>
        </div>

        {error && <div className="error-msg mt-2">{error}</div>}
        {success && <div className="success-msg mt-2">{success}</div>}

        {/* 新建售后表单 */}
        {showForm && (
          <div className="card">
            <h3 style={{ fontSize: 15, marginBottom: 14 }}>申请售后</h3>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>选择订单</label>
                <select
                  value={selectedOrderId}
                  onChange={(e) => setSelectedOrderId(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
                >
                  <option value="">-- 请选择 --</option>
                  {orders.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.order_no} - ¥{o.total_amount} ({o.status})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>售后类型</label>
                <select
                  value={afterType}
                  onChange={(e) => setAfterType(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
                >
                  <option value="return">退货</option>
                  <option value="refund">退款</option>
                  <option value="exchange">换货</option>
                </select>
              </div>

              <div className="form-group">
                <label>售后原因</label>
                <textarea
                  value={afterReason}
                  onChange={(e) => setAfterReason(e.target.value)}
                  rows={3}
                  placeholder="请描述您遇到的问题..."
                />
              </div>

              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? '提交中...' : '提交申请'}
              </button>
            </form>
          </div>
        )}

        {/* 售后列表 */}
        {loading ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#999' }}>加载中...</p>
        ) : records.length === 0 ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#999' }}>暂无售后记录</p>
        ) : (
          records.map((r) => {
            const s = statusInfo(r.status);
            return (
              <div key={r.id} className="card" style={{ fontSize: 14 }}>
                <div className="flex-between" style={{ marginBottom: 8 }}>
                  <div>
                    <strong>订单 #{r.order_id}</strong>
                    <span style={{ marginLeft: 12, color: '#6b7280' }}>{typeLabel(r.type)}</span>
                  </div>
                  <span className={`order-badge ${s.cls}`}>{s.label}</span>
                </div>
                <p style={{ color: '#555', marginBottom: 4 }}>{r.reason}</p>
                <p style={{ fontSize: 12, color: '#999' }}>
                  {new Date(r.created_at).toLocaleString()}
                </p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
