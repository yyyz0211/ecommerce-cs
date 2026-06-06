import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getAfterSales, getOrders, createAfterSale } from '../api';

export default function AfterSales() {
  const { logoutUser } = useAuth();
  const navigate = useNavigate();
  const [records, setRecords] = useState([]);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [orders, setOrders] = useState([]);
  const [selectedOrderId, setSelectedOrderId] = useState('');
  const [afterType, setAfterType] = useState('return');
  const [afterReason, setAfterReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { loadRecords(); loadMyOrders(); }, []);

  async function loadRecords() {
    try { setRecords(await getAfterSales()); }
    catch(e) { setError(e.message); }
  }

  async function loadMyOrders() {
    try {
      const d = await getOrders(1, 100);
      setOrders((d.items || []).filter(o => ['paid','shipped','delivered'].includes(o.status)));
    } catch {
      setOrders([]);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (!selectedOrderId) { setError('请选择订单'); return; }
    if (!afterReason.trim()) { setError('请填写原因'); return; }
    setSubmitting(true);
    try {
      await createAfterSale(parseInt(selectedOrderId), afterType, afterReason.trim());
      setSuccess('已提交');
      setShowForm(false);
      setAfterReason('');
      setSelectedOrderId('');
      loadRecords();
    } catch(e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  function typeLabel(t) { return {return:'退货',refund:'退款',exchange:'换货'}[t] || t; }
  function statusInfo(s) {
    const m = {pending:{l:'待处理',c:'status-pending'},approved:{l:'已通过',c:'status-delivered'},rejected:{l:'已拒绝',c:'status-cancelled'},completed:{l:'已完成',c:'status-delivered'}};
    return m[s] || {l:s,c:''};
  }

  return (
    <div className="app-page">
      <div className="app-shell">
        <header className="app-page-header">
          <button className="back-link" onClick={() => navigate('/chat')}>返回对话</button>
          <div className="page-heading">
            <p>After-sales</p>
            <h1>售后服务</h1>
          </div>
          <div className="page-actions">
            <span className="page-count">{records.length}</span>
            <button className="btn btn-sm btn-primary" onClick={() => setShowForm(!showForm)}>{showForm ? '收起' : '申请'}</button>
            <button className="btn btn-sm btn-secondary" onClick={() => { logoutUser(); navigate('/login'); }}>退出</button>
          </div>
        </header>

        {error && <div className="error-msg">{error}</div>}
        {success && <div className="success-msg">{success}</div>}

        {showForm && (
          <section className="soft-card">
            <h2 className="section-title">申请售后</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>选择订单</label>
                <select value={selectedOrderId} onChange={e => setSelectedOrderId(e.target.value)}>
                  <option value="">请选择</option>
                  {orders.map(o => <option key={o.id} value={o.id}>{o.order_no} - ¥{o.total_amount}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>类型</label>
                <select value={afterType} onChange={e => setAfterType(e.target.value)}>
                  <option value="return">退货</option>
                  <option value="refund">退款</option>
                  <option value="exchange">换货</option>
                </select>
              </div>
              <div className="form-group">
                <label>原因</label>
                <textarea value={afterReason} onChange={e => setAfterReason(e.target.value)} rows={3} placeholder="描述问题..." />
              </div>
              <button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? '提交中...' : '提交'}</button>
            </form>
          </section>
        )}

        {records.length === 0 ? (
          <div className="empty-state">暂无售后记录</div>
        ) : (
          <section className="list-stack">
            {records.map(record => {
              const status = statusInfo(record.status);
              return (
                <article key={record.id} className="soft-card compact-card">
                  <div className="record-header">
                    <div>
                      <strong>订单 #{record.order_id}</strong>
                      <span>{typeLabel(record.type)}</span>
                    </div>
                    <span className={`order-badge ${status.c}`}>{status.l}</span>
                  </div>
                  <p className="record-reason">{record.reason}</p>
                  <p className="record-time">{new Date(record.created_at).toLocaleString()}</p>
                </article>
              );
            })}
          </section>
        )}
      </div>
    </div>
  );
}
