import { useState } from 'react';
import { queryAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Send, Database, Clock, Download, AlertCircle, Loader } from 'lucide-react';

export default function QueryPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const suggestions = [
    'Show status summary',
    'How many emails failed this week?',
    'Show vendor ranking by failures',
    'Show emails sent by portfolio@anandrathi.com',
    'Show daily trend for last 7 days',
    'Top 10 clients by email volume',
  ];

  const handleSend = async (question) => {
    const q = question || input.trim();
    if (!q) return;

    const userMsg = { role: 'user', content: q, timestamp: new Date().toLocaleTimeString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await queryAPI.ask(q);
      const data = res.data;
      const aiMsg = {
        role: 'assistant',
        content: data,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      const errMsg = {
        role: 'assistant',
        content: { error: err.response?.data?.detail || 'Query failed. The Query API will be fully connected when MCP is built on Day 9-14. For now, Dashboard APIs are working!' },
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const exportCSV = (data, columns) => {
    if (!data || !columns) return;
    const header = columns.join(',');
    const rows = data.map((row) => columns.map((c) => `"${row[c] ?? ''}"`).join(','));
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'query_results.csv';
    a.click();
  };

  return (
    <div style={s.container}>
      <div style={s.header}>
        <h1 style={s.title}>Query Engine</h1>
        <div style={s.badge}>
          {user?.role_name === 'Admin' ? 'Full access' : `Filtered by role`}
        </div>
      </div>

      {/* Chat Messages */}
      <div style={s.chatArea}>
        {messages.length === 0 && (
          <div style={s.emptyState}>
            <Database size={40} color="#D0D5DD" />
            <h3 style={s.emptyTitle}>Ask your data anything</h3>
            <p style={s.emptyText}>Type a question in natural language and the AI will generate SQL and fetch results.</p>
            <div style={s.suggestGrid}>
              {suggestions.map((sg) => (
                <button key={sg} style={s.suggestBtn} onClick={() => handleSend(sg)}>
                  {sg}
                </button>
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
                <div style={s.errorBox}>
                  <AlertCircle size={16} />
                  <span>{msg.content.error}</span>
                </div>
              ) : (
                <div>
                  {/* SQL Preview */}
                  {msg.content.generated_sql && (
                    <div style={s.sqlBox}>
                      <div style={s.sqlHeader}>
                        <Database size={14} />
                        <span>Generated SQL</span>
                        <span style={s.methodBadge}>{msg.content.method}</span>
                      </div>
                      <pre style={s.sqlCode}>{msg.content.generated_sql}</pre>
                    </div>
                  )}

                  {/* Result Info */}
                  <div style={s.resultInfo}>
                    <span>{msg.content.row_count} rows returned</span>
                    {msg.content.execution_time_ms && (
                      <span style={s.timeInfo}><Clock size={12} /> {msg.content.execution_time_ms}ms</span>
                    )}
                  </div>

                  {/* Data Table */}
                  {msg.content.data && msg.content.data.length > 0 && (
                    <div style={s.tableWrap}>
                      <table style={s.table}>
                        <thead>
                          <tr>
                            {msg.content.columns.map((col) => (
                              <th key={col} style={s.th}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {msg.content.data.slice(0, 20).map((row, ri) => (
                            <tr key={ri}>
                              {msg.content.columns.map((col) => (
                                <td key={col} style={s.td}>{row[col] ?? '-'}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {msg.content.data.length > 20 && (
                        <p style={s.moreRows}>...and {msg.content.data.length - 20} more rows</p>
                      )}
                    </div>
                  )}

                  {/* Export Button */}
                  {msg.content.data && msg.content.data.length > 0 && (
                    <button style={s.exportBtn} onClick={() => exportCSV(msg.content.data, msg.content.columns)}>
                      <Download size={14} /> Export CSV
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
      </div>

      {/* Input Bar */}
      <div style={s.inputBar}>
        <input
          style={s.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your data..."
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
  header: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 },
  title: { fontSize: 24, fontWeight: 700, color: '#0F2744', margin: 0 },
  badge: { fontSize: 12, fontWeight: 500, padding: '4px 12px', borderRadius: 20, background: '#EEF2F7', color: '#5A6577' },
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
  methodBadge: { marginLeft: 'auto', padding: '2px 8px', borderRadius: 4, background: '#0D7C4A33', color: '#0D7C4A', fontSize: 10, fontWeight: 600 },
  sqlCode: { padding: '10px 14px', margin: 0, color: '#CDD6F4', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", whiteSpace: 'pre-wrap', wordBreak: 'break-all' },
  resultInfo: { display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#8B94A6', marginBottom: 10 },
  timeInfo: { display: 'flex', alignItems: 'center', gap: 4 },
  tableWrap: { maxHeight: 360, overflowY: 'auto', borderRadius: 8, border: '1px solid #E8ECF0', marginBottom: 10 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: { padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#5A6577', background: '#F8FAFB', borderBottom: '1px solid #E8ECF0', position: 'sticky', top: 0, fontSize: 11 },
  td: { padding: '7px 10px', borderBottom: '1px solid #F0F2F5', color: '#2D3748' },
  moreRows: { textAlign: 'center', fontSize: 12, color: '#8B94A6', padding: 8, margin: 0 },
  exportBtn: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 6, border: '1px solid #E8ECF0', background: '#FFF', fontSize: 12, fontWeight: 500, color: '#4A5568', cursor: 'pointer', fontFamily: 'inherit' },
  timestamp: { display: 'block', fontSize: 10, color: '#A0A8B6', marginTop: 6 },
  loadingDots: { display: 'flex', alignItems: 'center', gap: 8, color: '#8B94A6', fontSize: 13 },
  inputBar: { display: 'flex', gap: 10, padding: '16px 0 0', borderTop: '1px solid #E8ECF0' },
  input: { flex: 1, padding: '12px 16px', borderRadius: 10, border: '1px solid #DDE2E8', fontSize: 14, outline: 'none', fontFamily: 'inherit', transition: 'border-color 0.2s' },
  sendBtn: { width: 44, height: 44, borderRadius: 10, border: 'none', background: '#0F2744', color: '#FFF', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0, transition: 'opacity 0.15s' },
};
