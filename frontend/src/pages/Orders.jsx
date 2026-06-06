import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getOrders, getOrderDetail, cancelOrder, getLogistics, createOrder } from '../api';

export default function Orders() {
  const { logoutUser } = useAuth();
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
    try {
      const d = await getOrders(page, 10);
      setOrders(d.items);
      setTotal(d.total);
    } catch (e) {
      setError(e.message);
    }
  }

  async function toggleExpand(id) {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      setLogistics(null);
      return;
    }
    setExpandedId(id);
    try {
      const [d, l] = await Promise.all([getOrderDetail(id), getLogistics(id).catch(() => null)]);
      setDetail(d);
      setLogistics(l);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleCancel(id) {
    if (!confirm('确定取消？')) return;
    try {
      await cancelOrder(id);
      loadOrders();
      setExpandedId(null);
    } catch (e) {
      setError(e.message);
    }
  }

  function addItemRow() {
    setNewItems([...newItems, { product_name: '', quantity: 1, price: '' }]);
  }

  function updateItem(i, f, v) {
    setNewItems(newItems.map((it, j) => j === i ? { ...it, [f]: v } : it));
  }

  async function handleCreate(e) {
    e.preventDefault();
    setError('');
    setSuccess('');
    const items = newItems.map(it => ({
      product_name: it.product_name.trim(),
      quantity: parseInt(it.quantity) || 1,
      price: parseFloat(it.price) || 0,
    }));
    if (items.some(it => !it.product_name || it.price <= 0)) {
      setError('请填写有效的商品信息');
      return;
    }
    try {
      await createOrder(items, newAddress || null);
      setSuccess('创建成功');
      setShowCreate(false);
      setNewItems([{ product_name: '', quantity: 1, price: '' }]);
      setNewAddress('');
      loadOrders();
    } catch (e) {
      setError(e.message);
    }
  }

  function statusClass(s) { return `order-badge status-${s}`; }
  function statusLabel(s) { return { pending:'待付款',paid:'已付款',shipped:'运输中',delivered:'已签收',cancelled:'已取消' }[s]||s; }

  return (
    <div className="app-page">
      <div className="app-shell">
        <header className="app-page-header">
          <button className="back-link" onClick={() => navigate('/chat')}>返回对话</button>
          <div className="page-heading">
            <p>Orders</p>
            <h1>我的订单</h1>
          </div>
          <div className="page-actions">
            <span className="page-count">{total}</span>
            <button className="btn btn-sm btn-primary" onClick={() => setShowCreate(!showCreate)}>{showCreate ? '收起' : '新建'}</button>
            <button className="btn btn-sm btn-secondary" onClick={() => { logoutUser(); navigate('/login'); }}>退出</button>
          </div>
        </header>

        {error && <div className="error-msg">{error}</div>}
        {success && <div className="success-msg">{success}</div>}

        {showCreate && (
          <section className="soft-card">
            <h2 className="section-title">新建订单</h2>
            <form onSubmit={handleCreate}>
              {newItems.map((item, i) => (
                <div key={i} className="order-form-row">
                  <input className="inline-input grow" placeholder="商品名称" value={item.product_name} onChange={e => updateItem(i,'product_name',e.target.value)} />
                  <input className="inline-input qty" type="number" placeholder="数量" value={item.quantity} onChange={e => updateItem(i,'quantity',e.target.value)} min="1" />
                  <input className="inline-input price" type="number" placeholder="单价" value={item.price} onChange={e => updateItem(i,'price',e.target.value)} min="0" step="0.01" />
                  <button type="button" className="btn btn-sm btn-danger" onClick={() => newItems.length > 1 && setNewItems(newItems.filter((_,j) => j !== i))}>删</button>
                </div>
              ))}
              <div className="order-form-row">
                <button type="button" className="btn btn-sm btn-secondary" onClick={addItemRow}>添加商品</button>
                <input className="inline-input grow" placeholder="收货地址（选填）" value={newAddress} onChange={e => setNewAddress(e.target.value)} />
              </div>
              <button type="submit" className="btn btn-primary">提交</button>
            </form>
          </section>
        )}

        <section className="list-stack">
          {orders.map(order => (
            <article key={order.id} className="order-item" onClick={() => toggleExpand(order.id)}>
              <div className="order-header">
                <div className="order-main">
                  <span className="order-no">{order.order_no}</span>
                  <span className="order-date">{new Date(order.created_at).toLocaleDateString()}</span>
                </div>
                <div className="order-side">
                  <span className={statusClass(order.status)}>{statusLabel(order.status)}</span>
                  <strong>¥{order.total_amount}</strong>
                </div>
              </div>
              {expandedId === order.id && detail && (
                <div className="order-detail" onClick={e => e.stopPropagation()}>
                  <p className="detail-title">商品明细</p>
                  {detail.items?.map((item,i) => (
                    <div key={i} className="order-detail-row"><span>{item.product_name} x{item.quantity}</span><span>¥{item.price}</span></div>
                  ))}
                  {detail.shipping_address && <p className="detail-note">地址：{detail.shipping_address}</p>}
                  {logistics && <div className="logistics-card"><p>快递：{logistics.company || '暂无'} | 单号：{logistics.tracking_no || '暂无'}</p><p>状态：{logistics.status}</p></div>}
                  {(order.status === 'pending' || order.status === 'paid') && <button className="btn btn-sm btn-danger mt-2" onClick={() => handleCancel(order.id)}>取消订单</button>}
                </div>
              )}
            </article>
          ))}
        </section>

        {total > 10 && (
          <div className="pagination-bar">
            <button className="btn btn-sm btn-secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span>{page}/{Math.ceil(total / 10)}</span>
            <button className="btn btn-sm btn-secondary" disabled={page * 10 >= total} onClick={() => setPage(p => p + 1)}>下一页</button>
          </div>
        )}
      </div>
    </div>
  );
}
