import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { createChatSession, sendMessage, getChatHistory, getConversations } from '../api';

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

  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  async function loadConversations() {
    try { setConversations(await getConversations()); } catch {}
  }

  useEffect(() => { loadConversations(); }, []);

  useEffect(() => {
    if (!activeConvId) return;
    getChatHistory(activeConvId)
      .then(data => setMessages(data && data.length
        ? data.map(m => ({ role: m.role, content: m.content, time: new Date(m.created_at).getTime() }))
        : [{ role: 'agent', content: '你好！有什么可以帮您的？', time: Date.now() }]
      ))
      .catch(() => setMessages([{ role: 'agent', content: '你好！有什么可以帮您的？', time: Date.now() }]));
    inputRef.current?.focus();
  }, [activeConvId]);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, sending]);

  async function startNewChat() {
    try {
      const s = await createChatSession();
      setConversations(prev => [{ id: s.conversation_id, status: 'active', updated_at: new Date().toISOString() }, ...prev]);
      setActiveConvId(s.conversation_id);
    } catch {}
  }

  async function handleSend() {
    const text = inputValue.trim();
    if (!text || sending || !activeConvId) return;
    setInputValue('');
    setSending(true);
    setMessages(prev => [...prev, { role: 'user', content: text, time: Date.now() }]);
    try {
      const reply = await sendMessage(activeConvId, text);
      setMessages(prev => [...prev, { role: 'agent', content: reply.reply, time: Date.now() }]);
      loadConversations();
    } catch (err) {
      setMessages(prev => [...prev, { role: 'system', content: err.message, time: Date.now() }]);
    } finally { setSending(false); }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function formatTime(ts) {
    const d = new Date(ts || Date.now());
    const now = new Date();
    return d.toDateString() === now.toDateString()
      ? d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0')
      : (d.getMonth()+1) + '/' + d.getDate();
  }

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#f8f9fb' }}>
      {/* ═══ 左侧边栏 — 浅色 ═══ */}
      <div style={{ width: 280, background: '#fff', borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '18px 20px', borderBottom: '1px solid #f0f0f0' }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: '#111' }}>对话记录</span>
        </div>

        <div style={{ padding: '12px 16px' }}>
          <button onClick={startNewChat} style={{ width: '100%', padding: '9px 0', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', color: '#1f93ff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            + 新建对话
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {conversations.map(conv => (
            <div key={conv.id} onClick={() => setActiveConvId(conv.id)}
              style={{
                padding: '12px 20px', cursor: 'pointer',
                background: activeConvId === conv.id ? '#f0f5ff' : 'transparent',
                borderLeft: activeConvId === conv.id ? '3px solid #1f93ff' : '3px solid transparent',
                borderBottom: '1px solid #f5f5f5',
              }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#333', marginBottom: 2 }}>客服对话 #{conv.id}</div>
              <div style={{ fontSize: 11, color: '#999' }}>{formatTime(conv.updated_at)}</div>
            </div>
          ))}
          {conversations.length === 0 && (
            <div style={{ padding: 30, textAlign: 'center', color: '#bbb', fontSize: 13 }}>暂无对话</div>
          )}
        </div>

        <div style={{ padding: '12px 20px', borderTop: '1px solid #f0f0f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, color: '#666' }}>{user?.username}</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <span onClick={() => navigate('/orders')} style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>订单</span>
            <span onClick={() => navigate('/after-sales')} style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>售后</span>
            <span onClick={() => navigate('/profile')} style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>我的</span>
          </div>
        </div>
      </div>

      {/* ═══ 右侧聊天区 ═══ */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {!activeConvId ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', color: '#bbb' }}>
            <div style={{ fontSize: 56, marginBottom: 12, opacity: 0.2 }}>&#9993;</div>
            <p style={{ marginBottom: 16, fontSize: 15 }}>选择对话或开始新对话</p>
            <button className="btn btn-primary btn-sm" onClick={startNewChat}>开始新对话</button>
          </div>
        ) : (
          <>
            <div style={{ background: '#fff', borderBottom: '1px solid #eee', padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: '50%', background: '#1f93ff', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 700 }}>AI</div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#111' }}>智能客服</div>
                <div style={{ fontSize: 11, color: '#00c48c' }}>在线</div>
              </div>
            </div>

            <div className="chat-messages">
              {messages.map((msg, i) => (
                <div key={i}>
                  {msg.role === 'agent' && (i === 0 || messages[i-1].role !== 'agent') && (
                    <div style={{ fontSize: 11, color: '#999', fontWeight: 600, marginBottom: 4, paddingLeft: 4 }}>智能客服</div>
                  )}
                  <div className={`msg msg-${msg.role}`} style={{
                    marginLeft: msg.role === 'agent' ? 36 : undefined,
                    marginTop: i > 0 && messages[i-1].role === msg.role ? 2 : undefined,
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

            <div className="chat-input-wrap">
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
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1 8L15 1L8 15L7 9L1 8Z" fill="white" stroke="white" strokeWidth="1.5" strokeLinejoin="round"/></svg>
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
