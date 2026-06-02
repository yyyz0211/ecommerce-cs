import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getOrders, getOrderDetail, cancelOrder, getLogistics, createOrder } from '../api';

export default function Orders() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [logistics, setLogistics] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newItems, setNewItems] = useState([{ product_name: '', quantity: 1, price: '' }]);
  const [newAddress, setNewAddress] = useState('');

  useEffect(() => { loadOrders(); }, [page]);
  async function loadOrders() {
    setError('');
    try { const d = await getOrders(page, 10); setOrders(d.items); setTotal(d.total); }
    catch (e) { setError(e.message); }
  }

  async function toggleExpand(id) {
    if (expandedId === id) { setExpandedId(null); setDetail(null); setLogistics(null); return; }
    setExpandedId(id);
    try { const [d, l] = await Promise.all([getOrderDetail(id), getLogistics(id).catch(() => null)]); setDetail(d); setLogistics(l); }
    catch (e) { setError(e.message); }
  }

  async function handleCancel(id) { if (!confirm('确定取消？')) return; try { await cancelOrder(id); loadOrders(); setExpandedId(null); } catch (e) { setError(e.message); } }

  function addItemRow() { setNewItems([...newItems, { product_name: '', quantity: 1, price: '' }]); }
  function updateItem(i, f, v) { setNewItems(newItems.map((it, j) => j === i ? { ...it, [f]: v } : it)); }

  async function handleCreate(e) {
    e.preventDefault(); setError(''); setSuccess('');
    const items = newItems.map(it => ({ product_name: it.product_name.trim(), quantity: parseInt(it.quantity)||1, price: parseFloat(it.price)||0 }));
    if (items.some(it => !it.product_name || it.price <= 0)) { setError('请填写有效的商品信息'); return; }
    try { await createOrder(items, newAddress || null); setSuccess('创建成功'); setShowCreate(false); setNewItems([{ product_name: '', quantity: 1, price: '' }]); setNewAddress(''); loadOrders(); }
    catch (e) { setError(e.message); }
  }

  function statusClass(s) { return `order-badge status-${s}`; }
  function statusLabel(s) { return { pending:'待付款',paid:'已付款',shipped:'运输中',delivered:'已签收',cancelled:'已取消' }[s]||s; }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span onClick={() => navigate('/chat')} style={{ cursor: 'pointer', fontSize: 13, color: '#1f93ff' }}>← 返回对话</span>
          <h2 style={{ fontSize: 20, fontWeight: 700 }}>我的订单 ({total})</h2>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-sm btn-primary" onClick={() => setShowCreate(!showCreate)}>{showCreate?'收起':'+ 新建'}</button>
          <button className="btn btn-sm btn-secondary" onClick={() => { logoutUser(); navigate('/login'); }}>退出</button>
        </div>
      </div>

      {error && <div className="error-msg">{error}</div>}
      {success && <div className="success-msg">{success}</div>}

      {showCreate && (
        <div className="card">
          <h3 style={{ fontSize:15, marginBottom:14 }}>新建订单</h3>
          <form onSubmit={handleCreate}>
            {newItems.map((item, i) => (
              <div key={i} className="flex-between gap-2" style={{ marginBottom:8 }}>
                <input className="inline-input" placeholder="商品名称" value={item.product_name} onChange={e => updateItem(i,'product_name',e.target.value)} style={{flex:3}} />
                <input className="inline-input" type="number" placeholder="数量" value={item.quantity} onChange={e => updateItem(i,'quantity',e.target.value)} style={{width:70}} min="1" />
                <input className="inline-input" type="number" placeholder="单价" value={item.price} onChange={e => updateItem(i,'price',e.target.value)} style={{width:100}} min="0" step="0.01" />
                <button type="button" className="btn btn-sm btn-danger" onClick={() => newItems.length>1 && setNewItems(newItems.filter((_,j)=>j!==i))}>删</button>
              </div>
            ))}
            <div className="flex-between gap-2" style={{marginBottom:10}}>
              <button type="button" className="btn btn-sm btn-secondary" onClick={addItemRow}>+ 添加</button>
              <input className="inline-input" placeholder="收货地址（选填）" value={newAddress} onChange={e => setNewAddress(e.target.value)} style={{flex:1}} />
            </div>
            <button type="submit" className="btn btn-primary">提交</button>
          </form>
        </div>
      )}

      {orders.map(order => (
        <div key={order.id} className="order-item" onClick={() => toggleExpand(order.id)}>
          <div className="order-header">
            <div><span className="order-no">{order.order_no}</span><span className="order-date">{new Date(order.created_at).toLocaleDateString()}</span></div>
            <div className="flex-between gap-2">
              <span className={statusClass(order.status)}>{statusLabel(order.status)}</span>
              <span style={{fontWeight:600}}>¥{order.total_amount}</span>
            </div>
          </div>
          {expandedId===order.id && detail && (
            <div className="order-detail" onClick={e => e.stopPropagation()}>
              <p style={{fontWeight:600,marginBottom:6}}>商品明细</p>
              {detail.items?.map((item,i) => (<div key={i} className="order-detail-row"><span>{item.product_name} x{item.quantity}</span><span>¥{item.price}</span></div>))}
              {detail.shipping_address && <p className="mt-2" style={{fontSize:13,color:'#666'}}>地址：{detail.shipping_address}</p>}
              {logistics && <div className="logistics-card"><p>快递：{logistics.company||'暂无'} | 单号：{logistics.tracking_no||'暂无'}</p><p>状态：{logistics.status}</p></div>}
              {(order.status==='pending'||order.status==='paid') && <button className="btn btn-sm btn-danger mt-2" onClick={()=>handleCancel(order.id)}>取消订单</button>}
            </div>
          )}
        </div>
      ))}

      {total>10 && (
        <div className="flex-between mt-3" style={{justifyContent:'center',gap:12}}>
          <button className="btn btn-sm btn-secondary" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>上一页</button>
          <span style={{fontSize:13,color:'#999'}}>{page}/{Math.ceil(total/10)}</span>
          <button className="btn btn-sm btn-secondary" disabled={page*10>=total} onClick={()=>setPage(p=>p+1)}>下一页</button>
        </div>
      )}
    </div>
  );
}
