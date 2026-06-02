import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getAfterSales, getOrders, createAfterSale } from '../api';

export default function AfterSales() {
  const { user, logoutUser } = useAuth();
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

  async function loadRecords() { try { setRecords(await getAfterSales()); } catch(e) { setError(e.message); } }
  async function loadMyOrders() { try { const d = await getOrders(1, 100); setOrders((d.items||[]).filter(o => ['paid','shipped','delivered'].includes(o.status))); } catch {} }

  async function handleSubmit(e) {
    e.preventDefault(); setError('');
    if (!selectedOrderId) { setError('请选择订单'); return; }
    if (!afterReason.trim()) { setError('请填写原因'); return; }
    setSubmitting(true);
    try { await createAfterSale(parseInt(selectedOrderId), afterType, afterReason.trim()); setSuccess('已提交'); setShowForm(false); loadRecords(); }
    catch(e) { setError(e.message); }
    finally { setSubmitting(false); }
  }

  function typeLabel(t) { return {return:'退货',refund:'退款',exchange:'换货'}[t]||t; }
  function statusInfo(s) {
    const m = {pending:{l:'待处理',c:'status-pending'},approved:{l:'已通过',c:'status-delivered'},rejected:{l:'已拒绝',c:'status-cancelled'},completed:{l:'已完成',c:'status-delivered'}};
    return m[s]||{l:s,c:''};
  }

  return (
    <div style={{maxWidth:800,margin:'0 auto',padding:20}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:20}}>
        <div style={{display:'flex',alignItems:'center',gap:16}}>
          <span onClick={()=>navigate('/chat')} style={{cursor:'pointer',fontSize:13,color:'#1f93ff'}}>← 返回对话</span>
          <h2 style={{fontSize:20,fontWeight:700}}>我的售后 ({records.length})</h2>
        </div>
        <div style={{display:'flex',gap:8}}>
          <button className="btn btn-sm btn-primary" onClick={()=>setShowForm(!showForm)}>{showForm?'收起':'+ 申请'}</button>
          <button className="btn btn-sm btn-secondary" onClick={()=>{logoutUser();navigate('/login')}}>退出</button>
        </div>
      </div>

      {error && <div className="error-msg">{error}</div>}
      {success && <div className="success-msg">{success}</div>}

      {showForm && (
        <div className="card">
          <h3 style={{fontSize:15,marginBottom:14}}>申请售后</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-group"><label>选择订单</label><select value={selectedOrderId} onChange={e=>setSelectedOrderId(e.target.value)}><option value="">-- 请选择 --</option>{orders.map(o=>(<option key={o.id} value={o.id}>{o.order_no} - ¥{o.total_amount}</option>))}</select></div>
            <div className="form-group"><label>类型</label><select value={afterType} onChange={e=>setAfterType(e.target.value)}><option value="return">退货</option><option value="refund">退款</option><option value="exchange">换货</option></select></div>
            <div className="form-group"><label>原因</label><textarea value={afterReason} onChange={e=>setAfterReason(e.target.value)} rows={3} placeholder="描述问题..." /></div>
            <button type="submit" className="btn btn-primary" disabled={submitting}>{submitting?'提交中...':'提交'}</button>
          </form>
        </div>
      )}

      {records.length===0 ? <p style={{textAlign:'center',padding:40,color:'#999'}}>暂无售后记录</p> : records.map(r => { const s = statusInfo(r.status);
        return (<div key={r.id} className="card"><div className="flex-between" style={{marginBottom:6}}><div><strong>订单 #{r.order_id}</strong><span style={{marginLeft:12,color:'#999'}}>{typeLabel(r.type)}</span></div><span className={`order-badge ${s.c}`}>{s.l}</span></div><p style={{color:'#666'}}>{r.reason}</p><p style={{fontSize:12,color:'#999',marginTop:6}}>{new Date(r.created_at).toLocaleString()}</p></div>);
      })}
    </div>
  );
}
