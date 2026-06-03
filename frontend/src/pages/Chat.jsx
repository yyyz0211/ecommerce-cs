import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { createChatSession, sendMessage, getChatHistory } from '../api';

function renderContent(text) {
  if (!text) return '';
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  if (html.includes('|')) {
    const lines = html.split('\n');
    let inTable = false;
    let tableHtml = '';
    const result = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.startsWith('|') && line.endsWith('|')) {
        if (lines[i + 1] && lines[i + 1].includes('---')) {
          inTable = true;
          const cells = line.split('|').filter(c => c.trim());
          tableHtml = '<table><thead><tr>' + cells.map(c => `<th>${c.trim()}</th>`).join('') + '</tr></thead><tbody>';
          i++;
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

  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
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

  useEffect(() => {
    if (!convId) return;
    getChatHistory(convId)
      .then(data => {
        setMessages(data && data.length
          ? data.map(m => ({ role: m.role, content: m.content, time: new Date(m.created_at).getTime() }))
          : [{ role: 'agent', content: '你好，我是智能客服。可以帮你查订单、物流，或者处理售后问题。', time: Date.now() }]
        );
        setLoading(false);
        inputRef.current?.focus();
      })
      .catch(() => {
        setMessages([{ role: 'agent', content: '你好，我是智能客服。可以帮你查订单、物流，或者处理售后问题。', time: Date.now() }]);
        setLoading(false);
      });
  }, [convId]);

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
      ? `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
      : `${d.getMonth() + 1}/${d.getDate()}`;
  }

  function handleLogout() {
    logoutUser();
    navigate('/login');
  }

  return (
    <div className="chatwoot-page">
      <div className="chatwoot-shell">
        <header className="chatwoot-hero">
          <div className="chatwoot-topbar">
            <div className="chatwoot-brand">
              <div className="chatwoot-logo">AI</div>
              <div>
                <h1>智能客服</h1>
                <p><span /> 在线 · 通常几分钟内回复</p>
              </div>
            </div>
            <button className="chatwoot-ghost-btn" onClick={handleLogout}>退出</button>
          </div>

        </header>

        <main className="chatwoot-body">
          {loading ? (
            <div className="chatwoot-loading">正在打开对话...</div>
          ) : (
            <>
              <div className="chatwoot-date">今天</div>
              {messages.map((msg, index) => {
                const isAgent = msg.role === 'agent';
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={`${msg.time}-${index}`}
                    className={`chatwoot-message ${isUser ? 'is-user' : ''} ${msg.role === 'system' ? 'is-system' : ''}`}
                  >
                    {isAgent && <div className="chatwoot-avatar">AI</div>}
                    <div className="chatwoot-message-content">
                      <div className={`chatwoot-bubble ${isUser ? 'user' : isAgent ? 'agent' : 'system'}`}>
                        {isAgent
                          ? <span dangerouslySetInnerHTML={{ __html: renderContent(msg.content) }} />
                          : msg.content
                        }
                      </div>
                      {msg.role !== 'system' && <span className="chatwoot-time">{formatTime(msg.time)}</span>}
                    </div>
                  </div>
                );
              })}

              {sending && (
                <div className="chatwoot-message">
                  <div className="chatwoot-avatar">AI</div>
                  <div className="chatwoot-typing"><span /><span /><span /></div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </main>

        <footer className="chatwoot-composer">
          <div className="chatwoot-input">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={e => {
                setInputValue(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
              }}
              onKeyDown={handleKeyDown}
              placeholder="输入消息..."
              disabled={sending}
              rows={1}
            />
            <button onClick={handleSend} disabled={sending || !inputValue.trim()} aria-label="发送消息">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 8L14 2L9 14L7.8 9.2L2 8Z" fill="currentColor" />
              </svg>
            </button>
          </div>

          <div className="chatwoot-module-row">
            <button onClick={() => navigate('/orders')}>我的订单</button>
            <button onClick={() => navigate('/after-sales')}>售后服务</button>
            <button onClick={() => navigate('/profile')}>个人信息</button>
          </div>
        </footer>
      </div>
    </div>
  );
}
