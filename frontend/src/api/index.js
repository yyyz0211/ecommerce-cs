/*
 * API 调用封装层
 *
 * 【为什么需要这一层？】
 * 1. 所有后端请求集中在一个文件，改接口地址只改一处
 * 2. 自动带上 token（不用每个请求手动写 Authorization header）
 * 3. 统一处理错误
 */

const BASE = '/api';  // 开发时 Vite proxy 转发到 localhost:8000

/*
 * 读取浏览器里存的 token
 * 【为什么用 localStorage？】
 * token 需要"关了浏览器下次打开还在"，localStorage 数据不会自动清除
 * 如果用普通变量，刷新页面就丢了，用户得重新登录
 */
function getToken() {
  return localStorage.getItem('token');
}

/*
 * 每个 fetch 请求需要的通用 headers
 * Content-Type: 告诉后端"我发的是 JSON"
 * Authorization: JWT 令牌，后端用来识别当前用户
 */
function headers() {
  const h = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

/*
 * 统一处理响应：成功返回 data，失败抛异常
 * fetch() 在 HTTP 404/500 时不会自动抛异常，需要手动检查
 */
async function handleResponse(res) {
  // 先尝试解析 JSON，如果后端挂了返回 HTML，catch 给出提示
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error(`服务器返回了非 JSON 响应（状态码 ${res.status}），请检查后端是否正常运行`);
  }

  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    throw new Error(data.message || '请求失败');
  }
  return data;
}

// ══════════════════════════════════════════════════
// 认证相关
// ══════════════════════════════════════════════════

/** POST /api/auth/register — 注册新用户 */
export async function register(username, password, phone) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST', headers: headers(),
    body: JSON.stringify({ username, password, phone }),
  });
  return handleResponse(res);
}

/** POST /api/auth/login — 登录，返回 { access_token, token_type } */
export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST', headers: headers(),
    body: JSON.stringify({ username, password }),
  });
  return handleResponse(res);
}

/** POST /api/auth/refresh — 刷新 token */
export async function refreshToken() {
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST', headers: headers(),
  });
  return handleResponse(res);
}

// ══════════════════════════════════════════════════
// 用户
// ══════════════════════════════════════════════════

/** GET /api/users/me — 获取当前用户信息 */
export async function getMyInfo() {
  const res = await fetch(`${BASE}/users/me`, { headers: headers() });
  return handleResponse(res);
}

/** PATCH /api/users/me — 修改手机号或地址 */
export async function updateMyInfo(data) {
  const res = await fetch(`${BASE}/users/me`, {
    method: 'PATCH', headers: headers(),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ══════════════════════════════════════════════════
// 订单
// ══════════════════════════════════════════════════

/** GET /api/orders?page=&size= — 分页订单列表 */
export async function getOrders(page = 1, size = 10) {
  const res = await fetch(`${BASE}/orders?page=${page}&size=${size}`, { headers: headers() });
  return handleResponse(res);
}

/** POST /api/orders — 创建订单 */
export async function createOrder(items, shippingAddress) {
  const res = await fetch(`${BASE}/orders`, {
    method: 'POST', headers: headers(),
    body: JSON.stringify({ items, shipping_address: shippingAddress }),
  });
  return handleResponse(res);
}

/** GET /api/orders/{id} — 订单详情 */
export async function getOrderDetail(id) {
  const res = await fetch(`${BASE}/orders/${id}`, { headers: headers() });
  return handleResponse(res);
}

/** PATCH /api/orders/{id}/cancel — 取消订单 */
export async function cancelOrder(id) {
  const res = await fetch(`${BASE}/orders/${id}/cancel`, {
    method: 'PATCH', headers: headers(),
  });
  return handleResponse(res);
}

/** GET /api/orders/{id}/logistics — 物流信息 */
export async function getLogistics(id) {
  const res = await fetch(`${BASE}/orders/${id}/logistics`, { headers: headers() });
  return handleResponse(res);
}

// ══════════════════════════════════════════════════
// 售后
// ══════════════════════════════════════════════════

/** POST /api/after-sales — 提交售后 */
export async function createAfterSale(orderId, type, reason) {
  const res = await fetch(`${BASE}/after-sales`, {
    method: 'POST', headers: headers(),
    body: JSON.stringify({ order_id: orderId, type, reason }),
  });
  return handleResponse(res);
}

/** GET /api/after-sales — 售后列表 */
export async function getAfterSales() {
  const res = await fetch(`${BASE}/after-sales`, { headers: headers() });
  return handleResponse(res);
}

// ══════════════════════════════════════════════════
// 对话
// ══════════════════════════════════════════════════

/** GET /api/chat/sessions — 用户的所有对话会话 */
export async function getConversations() {
  const res = await fetch(`${BASE}/chat/sessions`, { headers: headers() });
  return handleResponse(res);
}

/** POST /api/chat/session — 创建新对话 */
export async function createChatSession() {
  const res = await fetch(`${BASE}/chat/session`, {
    method: 'POST', headers: headers(),
  });
  return handleResponse(res);
}

/** GET /api/chat/history/{conversationId} — 对话历史 */
export async function getChatHistory(conversationId) {
  const res = await fetch(`${BASE}/chat/history/${conversationId}`, { headers: headers() });
  return handleResponse(res);
}

/** POST /api/chat/message — 发送消息，获取 Agent 回复 */
export async function sendMessage(conversationId, content) {
  const res = await fetch(`${BASE}/chat/message`, {
    method: 'POST', headers: headers(),
    body: JSON.stringify({ conversation_id: conversationId, content }),
  });
  return handleResponse(res);
}
