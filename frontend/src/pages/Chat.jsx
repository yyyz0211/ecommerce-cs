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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#f0f2f5' }}>
      {/* ── Chatwoot 风格对话框 ── */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        maxWidth: 480, width: '100%', margin: '0 auto',
        overflow: 'hidden',
        background: '#fff',
      }}>
        {/* 头部 — Chatwoot 标志性的深色 header */}
        <div style={{
          padding: '14px 20px',
          background: 'linear-gradient(135deg, #1f93ff 0%, #1665c0 100%)',
          display: 'flex', alignItems: 'center', gap: 12,
          flexShrink: 0,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: '50%',
            background: 'rgba(255,255,255,0.2)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 15, fontWeight: 700,
          }}>AI</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>智能客服</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.75)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4cff8d', display: 'inline-block' }} />
              在线 · 通常几分钟内回复
            </div>
          </div>
          {/* 快捷导航 */}
          <span onClick={() => navigate('/orders')} style={{ cursor: 'pointer', fontSize: 12, color: 'rgba(255,255,255,0.8)' }}>订单</span>
          <span onClick={() => navigate('/after-sales')} style={{ cursor: 'pointer', fontSize: 12, color: 'rgba(255,255,255,0.8)' }}>售后</span>
        </div>

        {loading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#bbb', fontSize: 14 }}>
            加载中...
          </div>
        ) : (
          <>
            {/* 消息区 */}
            <div style={{
              flex: 1, overflowY: 'auto',
              padding: '16px 16px 8px',
              display: 'flex', flexDirection: 'column', gap: 8,
              background: '#fff',
            }}>
              {messages.map((msg, i) => (
                <div key={i} style={{
                  display: 'flex', flexDirection: 'column',
                  alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}>
                  {/* 同角色连续消息不重复显示头像 */}
                  {(i === 0 || messages[i - 1].role !== msg.role) && msg.role === 'agent' && (
                    <div style={{
                      width: 26, height: 26, borderRadius: '50%',
                      background: '#1f93ff', color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, fontWeight: 700,
                      marginBottom: 3, marginLeft: 2,
                    }}>AI</div>
                  )}
                  <div style={{
                    maxWidth: '80%',
                    padding: '10px 14px',
                    fontSize: 14, lineHeight: 1.5,
                    borderRadius: msg.role === 'user' ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
                    background: msg.role === 'user' ? '#1f93ff' : '#f1f3f5',
                    color: msg.role === 'user' ? '#fff' : '#1a1a1a',
                    wordBreak: 'break-word',
                  }}>
                    {msg.role === 'agent'
                      ? <span dangerouslySetInnerHTML={{ __html: renderContent(msg.content) }} />
                      : msg.content
                    }
                  </div>
                  <div style={{
                    fontSize: 10, color: '#b0b0b0',
                    marginTop: 2,
                    paddingLeft: msg.role === 'agent' ? 28 : 0,
                    paddingRight: msg.role === 'agent' ? 0 : 8,
                  }}>
                    {formatTime(msg.time)}
                  </div>
                </div>
              ))}
              {sending && (
                <div style={{ display: 'flex', gap: 4, padding: '8px 0', alignSelf: 'flex-start' }}>
                  <span style={{ width: 6, height: 6, background: '#c4c4c4', borderRadius: '50%', animation: 'typingBounce 1.4s infinite' }} />
                  <span style={{ width: 6, height: 6, background: '#c4c4c4', borderRadius: '50%', animation: 'typingBounce 1.4s infinite 0.16s' }} />
                  <span style={{ width: 6, height: 6, background: '#c4c4c4', borderRadius: '50%', animation: 'typingBounce 1.4s infinite 0.32s' }} />
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* 输入区 */}
            <div style={{
              padding: '8px 16px 16px',
              borderTop: '1px solid #f0f0f0',
              flexShrink: 0,
              background: '#fff',
            }}>
              <div style={{
                display: 'flex', gap: 8, alignItems: 'flex-end',
                background: '#f5f7fa', borderRadius: 12,
                padding: '6px 8px 6px 16px',
                border: '1px solid #e8eaed',
              }}>
                <textarea
                  ref={inputRef}
                  value={inputValue}
                  onChange={e => { setInputValue(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'; }}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息..."
                  disabled={sending}
                  rows={1}
                  style={{
                    flex: 1, border: 'none', outline: 'none',
                    fontSize: 14, fontFamily: 'inherit',
                    background: 'transparent', color: '#1a1a1a',
                    resize: 'none', minHeight: 22, maxHeight: 100,
                    lineHeight: 1.5, padding: 0,
                  }}
                />
                <button
                  onClick={handleSend}
                  disabled={sending || !inputValue.trim()}
                  style={{
                    width: 34, height: 34, minWidth: 34, borderRadius: '50%',
                    background: sending || !inputValue.trim() ? '#d4d8dd' : '#1f93ff',
                    border: 'none', cursor: sending || !inputValue.trim() ? 'not-allowed' : 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'background 0.15s',
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M1 8L15 1L8 15L7 9L1 8Z" fill="white" stroke="white" strokeWidth="1.5" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
              {/* 底部导航 */}
              <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginTop: 10 }}>
                <span style={{ fontSize: 11, color: '#bbb', cursor: 'pointer' }} onClick={() => navigate('/orders')}>我的订单</span>
                <span style={{ fontSize: 11, color: '#bbb', cursor: 'pointer' }} onClick={() => navigate('/after-sales')}>售后记录</span>
                <span style={{ fontSize: 11, color: '#bbb', cursor: 'pointer' }} onClick={() => navigate('/profile')}>{user?.username}</span>
                <span style={{ fontSize: 11, color: '#bbb', cursor: 'pointer' }} onClick={() => { logoutUser(); navigate('/login'); }}>退出</span>
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
        @keyframes typingBounce {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
