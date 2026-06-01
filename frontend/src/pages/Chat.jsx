import { useState, useEffect, useRef } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { createChatSession } from '../api';

/*
 * Chat 页面 — Intercom Messenger 风格对话
 *
 * 【消息分组】
 * 同一角色连续发送的消息在视觉上"无缝连接"，只在第一条显示头像
 */

export default function Chat() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();

  // 每条消息格式: { role: 'user'|'agent'|'system', content: '...', time: Date }
  const [messages, setMessages] = useState([
    { role: 'agent', content: '你好！欢迎使用电商智能客服。我可以帮您查询订单、申请售后、跟踪物流。请问有什么可以帮您的？', time: Date.now() },
  ]);
  const [conversationId, setConversationId] = useState(null);
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  /* 自动滚动 */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  /* 格式化时间 */
  function formatTime(ts) {
    const d = new Date(ts);
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  }

  /* 发送消息 */
  async function handleSend() {
    const text = inputValue.trim();
    if (!text || sending) return;

    setInputValue('');
    setSending(true);
    setMessages((prev) => [...prev, { role: 'user', content: text, time: Date.now() }]);

    try {
      let convId = conversationId;
      if (!convId) {
        const session = await createChatSession();
        convId = session.conversation_id;
        setConversationId(convId);
      }

      // TODO(Phase 3): 接入 POST /api/chat/message
      await new Promise((r) => setTimeout(r, 800));
      setMessages((prev) => [
        ...prev,
        { role: 'agent', content: '已收到您的消息："' + text + '"（模拟回复，Phase 3 后将接入 Agent）', time: Date.now() },
      ]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'system', content: '发送失败：' + err.message, time: Date.now() }]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function handleLogout() { logoutUser(); navigate('/login'); }

  /* 是否需要显示 Agent 头像：当前消息是 agent，且前一条不是 agent */
  function showAvatar(messages, index) {
    if (messages[index].role !== 'agent') return false;
    if (index === 0) return true;
    return messages[index - 1].role !== 'agent';
  }

  return (
    <div>
      <nav className="navbar">
        <div className="navbar-left">
          <span className="navbar-logo">客服系统</span>
          <NavLink to="/chat" className={({ isActive }) => isActive ? 'active' : ''}>对话</NavLink>
          <NavLink to="/orders">订单</NavLink>
          <NavLink to="/after-sales">售后</NavLink>
          <NavLink to="/profile">我的</NavLink>
        </div>
        <div className="navbar-right">
          <span>{user?.username}</span>
          <button className="btn-logout" onClick={handleLogout}>退出</button>
        </div>
      </nav>

      <div className="chat-container">
        {/* Intercom 标志性深色头部 */}
        <div className="chat-header">
          <div className="chat-header-avatar">AI</div>
          <div className="chat-header-text">
            <h3>智能客服团队</h3>
            <span>我们通常在几分钟内回复</span>
          </div>
        </div>

        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div key={i}>
              {/* Agent 头像行 */}
              {showAvatar(messages, i) && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4, paddingLeft: 4 }}>
                  <div className="chat-header-avatar" style={{ width: 26, height: 26, fontSize: 11 }}>AI</div>
                  <span style={{ fontSize: 12, color: '#6e6e6e', fontWeight: 600 }}>智能客服团队</span>
                  <span style={{ fontSize: 11, color: '#999' }}>{formatTime(msg.time)}</span>
                </div>
              )}

              {/* 消息气泡 */}
              <div className={`msg msg-${msg.role}`} style={{
                /* 连续 agent 消息首条不缩进，后续的缩进 */
                marginLeft: (msg.role === 'agent' && !showAvatar(messages, i)) ? 36 : (msg.role === 'agent' ? 36 : undefined),
                /* 连续同角色消息缩小间距 */
                marginTop: (i > 0 && messages[i - 1].role === msg.role) ? 2 : undefined,
                /* 连续同角色消息圆角处理 */
                borderTopLeftRadius: (msg.role === 'agent' && !showAvatar(messages, i)) ? 6 : undefined,
                borderTopRightRadius: (msg.role === 'user' && i > 0 && messages[i - 1].role === 'user') ? 6 : undefined,
              }}>
                {msg.content}
              </div>

              {/* 用户消息时间戳 */}
              {msg.role === 'user' && (
                <div style={{ textAlign: 'right', fontSize: 11, color: '#999', paddingRight: 4 }}>
                  {formatTime(msg.time)}
                </div>
              )}
            </div>
          ))}

          {/* Intercom 三点跳动输入指示器 */}
          {sending && (
            <div className="typing-indicator">
              <span /><span /><span />
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="chat-input-wrapper">
          <div className="chat-input-area">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="发送消息..."
              disabled={sending}
            />
            <button className="btn-send" onClick={handleSend} disabled={sending || !inputValue.trim()}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M1 8L15 1L8 15L7 9L1 8Z" fill="white" stroke="white" strokeWidth="1.5" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
