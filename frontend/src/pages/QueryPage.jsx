import { useState, useEffect, useRef } from 'react';
import { queryAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Send, Database, Clock, Download, AlertCircle, Loader, Trash2, ChevronDown, ChevronRight, Server } from 'lucide-react';

const STORAGE_KEY = 'query_chat_messages';
const DB_KEY = 'query_selected_db';
const CATEGORY_KEY = 'query_selected_category';

export default function QueryPage() {
  const { user } = useAuth();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedSql, setExpandedSql] = useState({});
  const [exporting, setExporting] = useState({}); // Track which message is exporting
  const chatEndRef = useRef(null);

  // Database & table state
  const [databases, setDatabases] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedDb, setSelectedDb] = useState(() => sessionStorage.getItem(DB_KEY) || '');
  const [selectedCategory, setSelectedCategory] = useState(() => sessionStorage.getItem(CATEGORY_KEY) || '');

  // Chat messages
  const [messages, setMessages] = useState(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });

  // Save messages
  useEffect(() => {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages)); } catch {}
  }, [messages]);

  // Fetch databases on mount
  useEffect(() => {
    queryAPI.databases().then((res) => {
      setDatabases(res.data.databases);
      if (!selectedDb) {
        setSelectedDb(res.data.default);
        sessionStorage.setItem(DB_KEY, res.data.default);
      }
    }).catch(() => {
      setDatabases([{ database: 'anandrathi', label: 'Communications', description: '' }]);
      if (!selectedDb) setSelectedDb('anandrathi');
    });
  }, []);

  // Fetch categories when database changes
  useEffect(() => {
    if (!selectedDb) return;
    queryAPI.categories(selectedDb).then((res) => {
      setCategories(res.data.categories);
      const currentExists = res.data.categories.some(c => c.category === selectedCategory);
      if (!currentExists && res.data.default) {
        setSelectedCategory(res.data.default);
        sessionStorage.setItem(CATEGORY_KEY, res.data.default);
      }
    }).catch(() => setCategories([]));
  }, [selectedDb]);

  // Auto-scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Dynamic suggestions based on selected database
  const getSuggestions = () => {
    if (selectedDb === 'anandrathi_trading') {
      return [
        'Which stock was traded most?',
        'Show cancelled trades',
        'Top clients by trade value',
        'How many trades on NSE vs BSE?',
        'Total buy value this month',
        'Show trades above 1 lakh',
        'Which broker handles most trades?',
        'Show pending trades',
      ];
    }
    return [
      'How many communications were sent',
      'Show status distribution',
      'How many errors per application',
      'Which application has the most failures',
      'Top 10 recipients by message volume',
      'How many SMS vs EMAIL were sent',
      'Show recent errors',
      'How many communications failed this week',
    ];
  };

  const handleDbChange = (e) => {
    const newDb = e.target.value;
    setSelectedDb(newDb);
    sessionStorage.setItem(DB_KEY, newDb);
    setMessages([]);
    sessionStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(CATEGORY_KEY);  // was TABLE_KEY
  };

  const handleCategoryChange = (e) => {
    const newCat = e.target.value;
    setSelectedCategory(newCat);
    sessionStorage.setItem(CATEGORY_KEY, newCat);
    setMessages([]);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  const handleSend = async (question) => {
    const q = question || input.trim();
    if (!q) return;

    const userMsg = { role: 'user', content: q, timestamp: new Date().toLocaleTimeString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await queryAPI.ask(q, selectedDb, selectedCategory);
      const data = res.data;
      setMessages((prev) => [...prev, { role: 'assistant', content: data, timestamp: new Date().toLocaleTimeString() }]);
    } catch (err) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: { error: err.response?.data?.detail || 'Query failed. Check if backend and Ollama are running.' },
        timestamp: new Date().toLocaleTimeString(),
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const clearChat = () => { setMessages([]); sessionStorage.removeItem(STORAGE_KEY); };

  const exportCSV = async (msgIdx, sql, database) => {
    if (!sql) return;
    setExporting((prev) => ({ ...prev, [msgIdx]: true }));
    try {
      const res = await queryAPI.exportCSV(sql, database);
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'query_results.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Export failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setExporting((prev) => ({ ...prev, [msgIdx]: false }));
    }
  };

  const currentDbLabel = databases.find(d => d.database === selectedDb)?.label || selectedDb; 

  return (
    <div style={s.container}>
      {/* Header */}
      <div style={s.header}>
        <h1 style={s.title}>Query Engine</h1>
        <div style={s.badge}>
          {user?.role_name === 'Admin' ? 'Full access' : 'Filtered by role'}
        </div>

        {/* Database Selector */}
        {databases.length > 1 && (
          <div style={s.selector}>
            <Server size={14} color="#5A6577" />
            <select style={s.dropdown} value={selectedDb} onChange={handleDbChange}>
              {databases.map((d) => (
                <option key={d.database} value={d.database}>{d.label}</option>
              ))}
            </select>
            <ChevronDown size={14} color="#5A6577" style={{ pointerEvents: 'none', marginLeft: -24 }} />
          </div>
        )}

        {/* Category Selector */}
        {categories.length > 0 && (
          <div style={s.selector}>
            <Database size={14} color="#5A6577" />
            <select style={s.dropdown} value={selectedCategory} onChange={handleCategoryChange}>
              {categories.map((c) => (
                <option key={c.category} value={c.category}>{c.category}</option>
              ))}
            </select>
            <ChevronDown size={14} color="#5A6577" style={{ pointerEvents: 'none', marginLeft: -24 }} />
          </div>
        )}

        {messages.length > 0 && (
          <button style={s.clearBtn} onClick={clearChat} title="Clear chat">
            <Trash2 size={14} /><span>Clear</span>
          </button>
        )}
      </div>

      {/* Context banner */}
{selectedCategory && (
  <div style={s.contextBanner}>
    <Server size={14} />
    <span>
      Querying: <strong>{currentDbLabel}</strong> → <strong>{selectedCategory}</strong>
    </span>
  </div>
)}

      {/* Chat Area */}
      <div style={s.chatArea}>
        {messages.length === 0 && (
          <div style={s.emptyState}>
            <Database size={40} color="#D0D5DD" />
            <h3 style={s.emptyTitle}>Ask your data anything</h3>
            <p style={s.emptyText}>
              Type a question in natural language and the AI will generate SQL and fetch results.
            </p>
            <div style={s.suggestGrid}>
              {getSuggestions().map((sg) => (
                <button key={sg} style={s.suggestBtn} onClick={() => handleSend(sg)}>{sg}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} style={{ ...s.msgRow, justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={msg.role === 'user' ? s.userBubble : s.aiBubble}>
              {msg.role === 'user' ? (
                <p style={s.msgText}>{msg.content}</p>
              ) : msg.content.error ? (
                <div style={s.errorBox}><AlertCircle size={16} /><span>{msg.content.error}</span></div>
              ) : (
                <div>
                  {msg.content.generated_sql && user?.role_name === 'Admin' && (
                    <div style={s.sqlBox}>
                      <button
                        style={s.sqlToggle}
                        onClick={() => setExpandedSql((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                      >
                        {expandedSql[idx] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        <Database size={14} />
                        <span>Generated SQL</span>
                        <span style={s.methodBadge}>{msg.content.method}</span>
                      </button>
                      {expandedSql[idx] && (
                        <pre style={s.sqlCode}>{msg.content.generated_sql}</pre>
                      )}
                    </div>
                  )}
                  <div style={s.resultInfo}>
                    <span>
                      {msg.content.truncated
                        ? `Showing ${msg.content.row_count} of ${msg.content.total_rows} rows`
                        : `${msg.content.row_count} rows returned`}
                    </span>
                    {msg.content.execution_time_ms && (
                      <span style={s.timeInfo}><Clock size={12} /> {msg.content.execution_time_ms}ms</span>
                    )}
                  </div>
                  {msg.content.truncated && (
                    <div style={s.truncateBanner}>
                      Table preview is limited to {msg.content.row_count} rows. Click <strong>Export CSV</strong> to download all {msg.content.total_rows} rows.
                    </div>
                  )}
                  {msg.content.data && msg.content.data.length > 0 && (
                    <div style={s.tableWrap}>
                      <table style={s.table}>
                        <thead><tr>
                          {msg.content.columns.map((col) => <th key={col} style={s.th}>{col}</th>)}
                        </tr></thead>
                        <tbody>
                          {msg.content.data.map((row, ri) => (
                            <tr key={ri}>
                              {msg.content.columns.map((col) => <td key={col} style={s.td}>{row[col] ?? '-'}</td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {msg.content.generated_sql && msg.content.data && msg.content.data.length > 0 && (
                    <button
                      style={s.exportBtn}
                      onClick={() => exportCSV(idx, msg.content.generated_sql, selectedDb)}
                      disabled={exporting[idx]}
                    >
                      {exporting[idx] ? (
                        <><Loader size={14} className="spin" /> Exporting...</>
                      ) : (
                        <><Download size={14} /> Export CSV{msg.content.truncated ? ` (all ${msg.content.total_rows} rows)` : ''}</>
                      )}
                    </button>
                  )}
                </div>
              )}
              <span style={s.timestamp}>{msg.timestamp}</span>
            </div>
          </div>
        ))}

        {loading && (
          <div style={s.msgRow}>
            <div style={s.aiBubble}>
              <div style={s.loadingDots}><Loader size={16} className="spin" /> Generating query...</div>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <div style={s.inputBar}>
        <input
          style={s.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`Ask about ${currentDbLabel}${selectedCategory ? ' → ' + selectedCategory : ''}...`}
          disabled={loading}
        />
        <button style={s.sendBtn} onClick={() => handleSend()} disabled={loading || !input.trim()}>
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}

const s = {
  container: { display: 'flex', flexDirection: 'column', height: 'calc(100vh - 56px)' },
  header: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' },
  title: { fontSize: 24, fontWeight: 700, color: '#0F2744', margin: 0 },
  badge: { fontSize: 12, fontWeight: 500, padding: '4px 12px', borderRadius: 20, background: '#EEF2F7', color: '#5A6577' },
  selector: { display: 'flex', alignItems: 'center', gap: 6, padding: '4px 12px', borderRadius: 8, border: '1px solid #E8ECF0', background: '#FFF', position: 'relative' },
  dropdown: { appearance: 'none', border: 'none', background: 'transparent', fontSize: 13, fontWeight: 500, color: '#0F2744', cursor: 'pointer', paddingRight: 20, outline: 'none', fontFamily: 'inherit' },
  clearBtn: { marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8, border: '1px solid #E8ECF0', background: '#FFF', fontSize: 12, fontWeight: 500, color: '#8B94A6', cursor: 'pointer', fontFamily: 'inherit' },
  contextBanner: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#5A6577', background: '#F0F7FF', border: '1px solid #D0E2F4', padding: '8px 14px', borderRadius: 8, marginBottom: 10 },
  chatArea: { flex: 1, overflowY: 'auto', paddingBottom: 16 },
  emptyState: { textAlign: 'center', padding: '60px 20px' },
  emptyTitle: { fontSize: 18, fontWeight: 600, color: '#0F2744', margin: '16px 0 6px' },
  emptyText: { fontSize: 14, color: '#8B94A6', margin: '0 0 24px', maxWidth: 400, marginInline: 'auto' },
  suggestGrid: { display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 600, margin: '0 auto' },
  suggestBtn: { padding: '8px 16px', borderRadius: 20, border: '1px solid #E8ECF0', background: '#FFF', fontSize: 13, color: '#4A5568', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' },
  msgRow: { display: 'flex', marginBottom: 12 },
  userBubble: { maxWidth: '70%', background: '#0F2744', color: '#FFF', padding: '12px 16px', borderRadius: '16px 16px 4px 16px' },
  aiBubble: { maxWidth: '85%', background: '#FFF', border: '1px solid #E8ECF0', padding: '14px 18px', borderRadius: '16px 16px 16px 4px' },
  msgText: { margin: 0, fontSize: 14, lineHeight: 1.6 },
  errorBox: { display: 'flex', alignItems: 'flex-start', gap: 8, color: '#D4620A', background: '#FEF0E4', padding: '10px 14px', borderRadius: 8, fontSize: 13 },
  sqlBox: { background: '#1E1E2E', borderRadius: 8, overflow: 'hidden', marginBottom: 10 },
  sqlHeader: { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', background: '#2A2A3E', color: '#8B94A6', fontSize: 11, fontWeight: 500 },
  sqlToggle: { display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '8px 12px', background: '#2A2A3E', color: '#8B94A6', fontSize: 11, fontWeight: 500, border: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' },
  methodBadge: { marginLeft: 'auto', padding: '2px 8px', borderRadius: 4, background: '#0D7C4A33', color: '#0D7C4A', fontSize: 10, fontWeight: 600 },
  sqlCode: { padding: '10px 14px', margin: 0, color: '#CDD6F4', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", whiteSpace: 'pre-wrap', wordBreak: 'break-all' },
  resultInfo: { display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#8B94A6', marginBottom: 10 },
  timeInfo: { display: 'flex', alignItems: 'center', gap: 4 },
  tableWrap: { maxHeight: 360, overflowY: 'auto', borderRadius: 8, border: '1px solid #E8ECF0', marginBottom: 10 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: { padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#5A6577', background: '#F8FAFB', borderBottom: '1px solid #E8ECF0', position: 'sticky', top: 0, fontSize: 11 },
  td: { padding: '7px 10px', borderBottom: '1px solid #F0F2F5', color: '#2D3748' },
  moreRows: { textAlign: 'center', fontSize: 12, color: '#8B94A6', padding: 8, margin: 0 },
  truncateBanner: { fontSize: 12, color: '#2D5A87', background: '#EAF2FA', border: '1px solid #B8D4EC', padding: '8px 12px', borderRadius: 6, marginBottom: 10 },
  exportBtn: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 6, border: '1px solid #E8ECF0', background: '#FFF', fontSize: 12, fontWeight: 500, color: '#4A5568', cursor: 'pointer', fontFamily: 'inherit' },
  timestamp: { display: 'block', fontSize: 10, color: '#A0A8B6', marginTop: 6 },
  loadingDots: { display: 'flex', alignItems: 'center', gap: 8, color: '#8B94A6', fontSize: 13 },
  inputBar: { display: 'flex', gap: 10, padding: '16px 0 0', borderTop: '1px solid #E8ECF0' },
  input: { flex: 1, padding: '12px 16px', borderRadius: 10, border: '1px solid #DDE2E8', fontSize: 14, outline: 'none', fontFamily: 'inherit', transition: 'border-color 0.2s' },
  sendBtn: { width: 44, height: 44, borderRadius: 10, border: 'none', background: '#0F2744', color: '#FFF', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0, transition: 'opacity 0.15s' },
};