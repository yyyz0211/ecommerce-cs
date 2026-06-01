import { useState, useEffect, useRef } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  createChatSession,
  getChatHistory,
} from '../api';

/*
 * Chat 页面 — 客服对话（核心页面）
 *
 * 【核心概念】
 * 1. messages：消息列表 [{ role: "user"|"agent"|"system", content: "..." }]
 *    role 决定气泡颜色和对齐方向
 * 2. conversationId：当前会话 ID，null 表示还没创建会话
 * 3. inputValue：输入框的当前文字
 *
 * 【用户发送消息的流程】
 * 1. 用户输入 → 点发送 → 把消息加到 messages 列表（显示在界面上）
 * 2. 如果还没有 conversationId → 调用 createChatSession() 创建一个
 * 3. （Phase 3 完成后）调用 sendMessage(conversationId, content)
 * 4. 后端返回 Agent 回复 → 加到 messages 列表 → 界面更新
 *
 * 【useRef 是什么？】
 * 和 useState 类似，但 ref 变化不会触发重新渲染。
 * 这里用来：
 *   messagesEndRef — 指向消息列表底部的空 div，新消息到达时自动滚到那里
 *   inputRef — 指向输入框，页面加载后自动聚焦
 */

export default function Chat() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();

  // ── 状态 ──
  const [messages, setMessages] = useState([
    { role: 'system', content: '欢迎使用电商智能客服！您可以向我查询订单、申请售后。' },
  ]);
  const [conversationId, setConversationId] = useState(null);
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);

  // DOM 引用（不触发重新渲染）
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // 页面加载时自动聚焦输入框
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // 新消息到达时自动滚到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /* 发送消息 */
  async function handleSend() {
    const text = inputValue.trim();
    if (!text || sending) return;

    setInputValue('');  // 清空输入框
    setSending(true);

    // 1. 把用户消息加入列表
    setMessages((prev) => [...prev, { role: 'user', content: text }]);

    try {
      // 2. 如果没有会话，先创建
      let convId = conversationId;
      if (!convId) {
        const session = await createChatSession();
        convId = session.conversation_id;
        setConversationId(convId);
      }

      // TODO(Phase 3): 这里接入 POST /api/chat/message
      // const reply = await sendMessage(convId, text);
      // setMessages((prev) => [...prev, { role: 'agent', content: reply.reply }]);

      // Phase 3 之前用模拟回复
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          {
            role: 'agent',
            content: '客服系统已收到您的消息："' + text + '"（当前为模拟回复，Phase 3 接入 Agent 后将提供智能回复）',
          },
        ]);
        setSending(false);
      }, 600);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'system', content: '发送失败：' + err.message },
      ]);
      setSending(false);
    }
  }

  /* 按 Enter 发送（Shift+Enter 换行） */
  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  /* 退出登录 */
  function handleLogout() {
    logoutUser();
    navigate('/login');
  }

  return (
    <div>
      {/* 导航栏 */}
      <nav className="navbar">
        <div className="navbar-left">
          <span style={{ fontWeight: 700 }}>客服系统</span>
          <NavLink to="/chat" className={({ isActive }) => isActive ? 'active' : ''}>对话</NavLink>
          <NavLink to="/orders">订单</NavLink>
          <NavLink to="/profile">我的</NavLink>
        </div>
        <div className="navbar-right">
          <span>{user?.username}</span>
          <button className="btn btn-sm btn-secondary" onClick={handleLogout}>退出</button>
        </div>
      </nav>

      {/* 消息列表 */}
      <div className="chat-container">
        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`msg msg-${msg.role}`}>
              {msg.content}
            </div>
          ))}
          {/*
            * 这个空 div 是滚动锚点：每次 messages 变化，
            * useEffect 调用 scrollIntoView 滚动到这里
            */}
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="chat-input-area">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入您的问题...（Enter 发送）"
            disabled={sending}
          />
          <button className="btn btn-primary" onClick={handleSend} disabled={sending}>
            {sending ? '发送中...' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
