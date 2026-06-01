import { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getOrders, getOrderDetail, cancelOrder, getLogistics } from '../api';

/*
 * Orders 页面
 *
 * 【核心概念】
 * 列表渲染：用 .map() 把订单数组转成 JSX 元素
 * 条件渲染：expandedId 不为 null 时才显示订单详情
 * 状态提升：点击哪个订单就把它的 id 存到 expandedId
 */

export default function Orders() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();

  const [orders, setOrders] = useState([]);     // 订单列表
  const [total, setTotal] = useState(0);         // 总订单数
  const [page, setPage] = useState(1);           // 当前页码
  const [expandedId, setExpandedId] = useState(null);  // 当前展开的订单 ID
  const [detail, setDetail] = useState(null);    // 展开订单的详情
  const [logistics, setLogistics] = useState(null); // 展开订单的物流
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 页面加载时获取订单
  useEffect(() => {
    loadOrders();
  }, [page]);  // page 变化时重新加载

  async function loadOrders() {
    setLoading(true);
    setError('');
    try {
      const data = await getOrders(page, 10);
      setOrders(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  /* 点击订单：展开/收起详情 */
  async function toggleExpand(orderId) {
    if (expandedId === orderId) {
      // 同一个订单 → 收起
      setExpandedId(null);
      setDetail(null);
      setLogistics(null);
    } else {
      // 不同订单 → 加载详情
      setExpandedId(orderId);
      setError('');
      try {
        const [orderDetail, logisticsData] = await Promise.all([
          getOrderDetail(orderId),
          getLogistics(orderId).catch(() => null),  // 可能没有物流，不报错
        ]);
        setDetail(orderDetail);
        setLogistics(logisticsData);
      } catch (err) {
        setError(err.message);
      }
    }
  }

  /* 取消订单 */
  async function handleCancel(orderId) {
    if (!confirm('确定要取消这个订单吗？')) return;
    try {
      await cancelOrder(orderId);
      loadOrders();  // 刷新列表
      setExpandedId(null);
    } catch (err) {
      setError(err.message);
    }
  }

  /* 退出 */
  function handleLogout() {
    logoutUser();
    navigate('/login');
  }

  /* 订单状态标签的 CSS 类名：status-{status} */
  function statusClass(status) {
    return `order-status status-${status}`;
  }

  /* 状态中文映射 */
  function statusLabel(status) {
    const map = { pending: '待付款', paid: '已付款', shipped: '运输中', delivered: '已签收', cancelled: '已取消' };
    return map[status] || status;
  }

  return (
    <div>
      <nav className="navbar">
        <div className="navbar-left">
          <span style={{ fontWeight: 700 }}>客服系统</span>
          <NavLink to="/chat">对话</NavLink>
          <NavLink to="/orders" className={({ isActive }) => isActive ? 'active' : ''}>订单</NavLink>
          <NavLink to="/profile">我的</NavLink>
        </div>
        <div className="navbar-right">
          <span>{user?.username}</span>
          <button className="btn btn-sm btn-secondary" onClick={handleLogout}>退出</button>
        </div>
      </nav>

      <div className="page">
        <div className="flex-between">
          <h2 style={{ fontSize: 18 }}>我的订单（共 {total} 笔）</h2>
        </div>

        {error && <div className="error-msg mt-2">{error}</div>}

        {loading ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#999' }}>加载中...</p>
        ) : (
          orders.map((order) => (
            <div key={order.id} className="order-item">
              {/* 订单头部（始终可见） */}
              <div className="order-header" onClick={() => toggleExpand(order.id)}>
                <div>
                  <span className="order-no">{order.order_no}</span>
                  <span style={{ fontSize: 13, color: '#999', marginLeft: 12 }}>
                    {new Date(order.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className={statusClass(order.status)}>{statusLabel(order.status)}</span>
                  <span style={{ fontWeight: 600 }}>¥{order.total_amount}</span>
                </div>
              </div>

              {/* 展开的详情（expandedId === order.id 时才显示） */}
              {expandedId === order.id && detail && (
                <div className="order-detail">
                  {/* 商品列表 */}
                  <p style={{ fontWeight: 600, marginBottom: 6 }}>商品明细：</p>
                  {detail.items?.map((item, i) => (
                    <div key={i} className="flex-between" style={{ marginBottom: 4 }}>
                      <span>{item.product_name} × {item.quantity}</span>
                      <span>¥{item.price}</span>
                    </div>
                  ))}

                  {/* 收货地址 */}
                  {detail.shipping_address && (
                    <p style={{ marginTop: 8, fontSize: 13, color: '#666' }}>
                      收货地址：{detail.shipping_address}
                    </p>
                  )}

                  {/* 物流 */}
                  {logistics && (
                    <div style={{ marginTop: 8, padding: '8px 12px', background: '#f9fafb', borderRadius: 6, fontSize: 13 }}>
                      <p><strong>快递公司：</strong>{logistics.company || '暂无'}</p>
                      <p><strong>快递单号：</strong>{logistics.tracking_no || '暂无'}</p>
                      <p><strong>物流状态：</strong>{logistics.status}</p>
                    </div>
                  )}

                  {/* 取消按钮 — 仅 pending/paid 状态显示 */}
                  {(order.status === 'pending' || order.status === 'paid') && (
                    <button
                      className="btn btn-danger btn-sm mt-2"
                      onClick={() => handleCancel(order.id)}
                    >
                      取消订单
                    </button>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {/* 分页 */}
        {total > 10 && (
          <div className="flex-between mt-2" style={{ justifyContent: 'center', gap: 12 }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </button>
            <span style={{ fontSize: 13 }}>第 {page} 页</span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page * 10 >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
