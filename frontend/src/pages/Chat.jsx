import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { createChatSession, sendMessage, getChatHistory } from '../api';

/* 简单的 Markdown → HTML 渲染（表格 + 粗体 + 换行）*/
function renderContent(text) {
  if (!text) return '';
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // 表格：按行处理 | col | col |
  if (html.includes('|')) {
    const lines = html.split('\n');
    let inTable = false;
    let tableHtml = '';
    let result = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.startsWith('|') && line.endsWith('|')) {
        if (lines[i + 1] && lines[i + 1].includes('---')) {
          // 表头行
          inTable = true;
          const cells = line.split('|').filter(c => c.trim());
          tableHtml = '<table><thead><tr>' + cells.map(c => `<th>${c.trim()}</th>`).join('') + '</tr></thead><tbody>';
          i++; // 跳过分隔行
        } else if (inTable) {
          const cells = line.split('|').filter(c => c.trim());
          tableHtml += '<tr>' + cells.map(c => `<td>${c.trim()}</td>`).join('') + '</tr>';
        }
        continue;
      }
      if (inTable) {
        tableHtml += '</tbody></table>';
        result.push(tableHtml);
        inTable = false;
      }
      if (line) result.push(line);
    }
    if (inTable) result.push(tableHtml + '</tbody></table>');
    html = result.join('\n');
  }

  // 粗体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // 换行
  html = html.replace(/\n/g, '<br/>');

  return html;
}

export default function Chat() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();

  const [convId, setConvId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // 挂载时自动获取或创建唯一的对话会话
  useEffect(() => {
    async function init() {
      try {
        const s = await createChatSession();
        setConvId(s.conversation_id);
      } catch {
        setLoading(false);
      }
    }
    init();
  }, []);

  // 会话 ID 确定后加载历史消息
  useEffect(() => {
    if (!convId) return;
    getChatHistory(convId)
      .then(data => {
        setMessages(data && data.length
          ? data.map(m => ({ role: m.role, content: m.content, time: new Date(m.created_at).getTime() }))
          : [{ role: 'agent', content: '你好！有什么可以帮您的？', time: Date.now() }]
        );
        setLoading(false);
        inputRef.current?.focus();
      })
      .catch(() => {
        setMessages([{ role: 'agent', content: '你好！有什么可以帮您的？', time: Date.now() }]);
        setLoading(false);
      });
  }, [convId]);

  // 消息更新后自动滚到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  async function handleSend() {
    const text = inputValue.trim();
    if (!text || sending || !convId) return;
    setInputValue('');
    setSending(true);
    setMessages(prev => [...prev, { role: 'user', content: text, time: Date.now() }]);
    try {
      const reply = await sendMessage(convId, text);
      setMessages(prev => [...prev, { role: 'agent', content: reply.reply, time: Date.now() }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'system', content: err.message, time: Date.now() }]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function formatTime(ts) {
    const d = new Date(ts || Date.now());
    const now = new Date();
    return d.toDateString() === now.toDateString()
      ? d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
      : (d.getMonth() + 1) + '/' + d.getDate();
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#f8f9fb' }}>
      {/* ── 顶部导航栏 ── */}
      <div style={{
        background: '#fff', borderBottom: '1px solid #e5e7eb',
        padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        height: 48, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: '#111' }}>智能客服</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: 13, color: '#666' }}>{user?.username}</span>
          <span onClick={() => navigate('/orders')} style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>订单</span>
          <span onClick={() => navigate('/after-sales')} style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>售后</span>
          <span onClick={() => navigate('/profile')} style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>我的</span>
          <span onClick={() => { logoutUser(); navigate('/login'); }} style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>退出</span>
        </div>
      </div>

      {/* ── 聊天内容区 ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', maxWidth: 900, width: '100%', margin: '0 auto' }}>
        {loading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#bbb', fontSize: 14 }}>
            加载中...
          </div>
        ) : (
          <>
            <div className="chat-messages">
              {messages.map((msg, i) => (
                <div key={i}>
                  {msg.role === 'agent' && (i === 0 || messages[i - 1].role !== 'agent') && (
                    <div style={{ fontSize: 11, color: '#999', fontWeight: 600, marginBottom: 4, paddingLeft: 4 }}>智能客服</div>
                  )}
                  <div className={`msg msg-${msg.role}`} style={{
                    marginLeft: msg.role === 'agent' ? 36 : undefined,
                    marginTop: i > 0 && messages[i - 1].role === msg.role ? 2 : undefined,
                  }}>
                    {msg.role === 'agent'
                      ? <span dangerouslySetInnerHTML={{ __html: renderContent(msg.content) }} />
                      : msg.content
                    }
                  </div>
                  {msg.role === 'user' && <div style={{ textAlign: 'right', fontSize: 11, color: '#999', paddingRight: 4 }}>{formatTime(msg.time)}</div>}
                </div>
              ))}
              {sending && (
                <div style={{ display: 'flex', gap: 4, padding: '8px 0', alignSelf: 'flex-start', marginLeft: 36 }}>
                  <span style={{ width: 6, height: 6, background: '#c4c4c4', borderRadius: '50%', animation: 'typingBounce 1.4s infinite' }} />
                  <span style={{ width: 6, height: 6, background: '#c4c4c4', borderRadius: '50%', animation: 'typingBounce 1.4s infinite 0.16s' }} />
                  <span style={{ width: 6, height: 6, background: '#c4c4c4', borderRadius: '50%', animation: 'typingBounce 1.4s infinite 0.32s' }} />
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-wrapper" style={{ padding: '12px 32px 28px' }}>
              <div className="chat-input-area">
                <textarea
                  ref={inputRef}
                  value={inputValue}
                  onChange={e => { setInputValue(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'; }}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息...（Enter 发送，Shift+Enter 换行）"
                  disabled={sending}
                  rows={1}
                />
                <button className="btn-send" onClick={handleSend} disabled={sending || !inputValue.trim()}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1 8L15 1L8 15L7 9L1 8Z" fill="white" stroke="white" strokeWidth="1.5" strokeLinejoin="round" /></svg>
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <style>{`
        table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
        th, td { border: 1px solid #e5e7eb; padding: 6px 10px; text-align: left; }
        th { background: #f5f7fa; font-weight: 600; color: #555; }
        td { color: #333; }
        strong { color: #222; }
      `}</style>
    </div>
  );
}
