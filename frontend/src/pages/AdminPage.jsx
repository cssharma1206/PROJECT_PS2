import { useState, useEffect } from 'react';
import { adminAPI } from '../services/api';
import { Users, Search, AlertTriangle, RefreshCw } from 'lucide-react';

export default function AdminPage() {
  const [tab, setTab] = useState('users');
  const [users, setUsers] = useState([]);
  const [queryLogs, setQueryLogs] = useState([]);
  const [errorLogs, setErrorLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [totals, setTotals] = useState({ users: 0, queries: 0, errors: 0 });

  useEffect(() => { loadData(); }, [tab]);

  const loadData = async () => {
    setLoading(true);
    try {
      if (tab === 'users') {
        const res = await adminAPI.users();
        setUsers(res.data.users || []);
        setTotals((p) => ({ ...p, users: res.data.total }));
      } else if (tab === 'queries') {
        const res = await adminAPI.queryLogs(1, 50);
        setQueryLogs(res.data.queries || []);
        setTotals((p) => ({ ...p, queries: res.data.total }));
      } else if (tab === 'errors') {
        const res = await adminAPI.errorLogs(1, 50);
        setErrorLogs(res.data.errors || []);
        setTotals((p) => ({ ...p, errors: res.data.total }));
      }
    } catch (err) {
      console.error('Admin load error:', err);
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: 'users', label: 'Users', icon: Users },
    { id: 'queries', label: 'Query Logs', icon: Search },
    { id: 'errors', label: 'Error Logs', icon: AlertTriangle },
  ];

  return (
    <div>
      <div style={s.header}>
        <h1 style={s.title}>Admin Panel</h1>
        <button style={s.refreshBtn} onClick={loadData}><RefreshCw size={14} /> Refresh</button>
      </div>

      {/* Tabs */}
      <div style={s.tabBar}>
        {tabs.map((t) => (
          <button key={t.id} style={{ ...s.tab, ...(tab === t.id ? s.tabActive : {}) }} onClick={() => setTab(t.id)}>
            <t.icon size={15} />
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div style={s.loading}>Loading...</div>
      ) : (
        <div style={s.card}>
          {/* Users Tab */}
          {tab === 'users' && (
            <>
              <div style={s.cardHeader}>
                <span style={s.cardTitle}>All Users ({totals.users})</span>
              </div>
              <table style={s.table}>
                <thead>
                  <tr>
                    {['ID', 'Username', 'Full Name', 'Email', 'Role', 'Active', 'Last Login'].map((h) => (
                      <th key={h} style={s.th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.user_id}>
                      <td style={s.td}>{u.user_id}</td>
                      <td style={{ ...s.td, fontWeight: 600 }}>{u.username}</td>
                      <td style={s.td}>{u.full_name}</td>
                      <td style={{ ...s.td, color: '#1A6DDB' }}>{u.email}</td>
                      <td style={s.td}>
                        <span style={{ ...s.roleBadge, background: u.role_name === 'Admin' ? '#FDECEC' : u.role_name === 'Client' ? '#FFF8E7' : '#E3F5EC', color: u.role_name === 'Admin' ? '#C93B3B' : u.role_name === 'Client' ? '#D4A017' : '#0D7C4A' }}>
                          {u.role_name}
                        </span>
                      </td>
                      <td style={s.td}>{u.is_active ? 'Yes' : 'No'}</td>
                      <td style={{ ...s.td, color: '#8B94A6', fontSize: 12 }}>{u.last_login || 'Never'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {/* Query Logs Tab */}
          {tab === 'queries' && (
            <>
              <div style={s.cardHeader}>
                <span style={s.cardTitle}>Query Execution Logs ({totals.queries})</span>
              </div>
              {queryLogs.length === 0 ? (
                <div style={s.emptyMsg}>No query logs yet. Logs will appear once the MCP Query engine is connected (Day 9-14).</div>
              ) : (
                <table style={s.table}>
                  <thead>
                    <tr>
                      {['ID', 'Question', 'Method', 'Results', 'Success', 'Time'].map((h) => (
                        <th key={h} style={s.th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {queryLogs.map((q) => (
                      <tr key={q.log_id}>
                        <td style={s.td}>{q.log_id}</td>
                        <td style={{ ...s.td, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.query_text}</td>
                        <td style={s.td}><span style={s.methodBadge}>{q.method || '-'}</span></td>
                        <td style={s.td}>{q.result_count}</td>
                        <td style={s.td}>{q.was_successful ? 'Yes' : 'No'}</td>
                        <td style={{ ...s.td, color: '#8B94A6', fontSize: 12 }}>{q.created_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}

          {/* Error Logs Tab */}
          {tab === 'errors' && (
            <>
              <div style={s.cardHeader}>
                <span style={s.cardTitle}>Application Errors ({totals.errors})</span>
              </div>
              {errorLogs.length === 0 ? (
                <div style={s.emptyMsg}>No errors logged. This is good!</div>
              ) : (
                <table style={s.table}>
                  <thead>
                    <tr>
                      {['ID', 'Type', 'Message', 'Endpoint', 'Time'].map((h) => (
                        <th key={h} style={s.th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {errorLogs.map((e) => (
                      <tr key={e.error_id}>
                        <td style={s.td}>{e.error_id}</td>
                        <td style={s.td}><span style={{ ...s.methodBadge, background: '#FDECEC', color: '#C93B3B' }}>{e.error_type}</span></td>
                        <td style={{ ...s.td, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.error_message}</td>
                        <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 12 }}>{e.endpoint || '-'}</td>
                        <td style={{ ...s.td, color: '#8B94A6', fontSize: 12 }}>{e.created_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

const s = {
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 },
  title: { fontSize: 24, fontWeight: 700, color: '#0F2744', margin: 0 },
  refreshBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, border: '1px solid #E8ECF0', background: '#FFF', fontSize: 13, fontWeight: 500, color: '#5A6577', cursor: 'pointer', fontFamily: 'inherit' },
  tabBar: { display: 'flex', gap: 4, marginBottom: 16, background: '#FFF', borderRadius: 10, padding: 4, border: '1px solid #E8ECF0' },
  tab: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '10px 16px', borderRadius: 8, border: 'none', background: 'transparent', fontSize: 13, fontWeight: 500, color: '#8B94A6', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' },
  tabActive: { background: '#0F2744', color: '#FFF' },
  loading: { textAlign: 'center', padding: 40, color: '#8B94A6', fontSize: 14 },
  card: { background: '#FFF', borderRadius: 12, border: '1px solid #E8ECF0', overflow: 'hidden' },
  cardHeader: { padding: '14px 18px', borderBottom: '1px solid #F0F2F5' },
  cardTitle: { fontSize: 14, fontWeight: 600, color: '#0F2744' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { padding: '10px 14px', textAlign: 'left', fontWeight: 500, color: '#8B94A6', borderBottom: '1px solid #F0F2F5', fontSize: 11, background: '#FAFBFC' },
  td: { padding: '10px 14px', borderBottom: '1px solid #F8F9FA', color: '#2D3748' },
  roleBadge: { padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600 },
  methodBadge: { padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: '#E3F5EC', color: '#0D7C4A' },
  emptyMsg: { padding: '40px 20px', textAlign: 'center', color: '#8B94A6', fontSize: 14 },
};
