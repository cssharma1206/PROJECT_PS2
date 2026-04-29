import { useState, useEffect } from 'react';
import { dashboardAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, Tooltip,
  BarChart, Bar, CartesianGrid,
} from 'recharts';
import {
  TrendingUp, TrendingDown, Mail, AlertTriangle, Clock, CheckCircle,
  BarChart3, IndianRupee, Activity, ArrowUpDown,
} from 'lucide-react';

const COLORS = ['#0D7C4A', '#C93B3B', '#D4A017', '#1A6DDB', '#6B3FA0', '#0E7C86'];

export default function DashboardPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('communications');  // NEW

  return (
    <div>
      <div style={s.header}>
        <h1 style={s.title}>Dashboard</h1>
        <div style={s.badge}>
          {user?.role_name === 'Admin' ? 'All data' : `Team ${user?.application_id || ''}`}
        </div>
      </div>

      {/* ─── TAB SWITCHER ─── */}
      <div style={s.tabRow}>
        <button
          style={activeTab === 'communications' ? s.tabActive : s.tab}
          onClick={() => setActiveTab('communications')}
        >
          Communications
        </button>
        <button
          style={activeTab === 'trading' ? s.tabActive : s.tab}
          onClick={() => setActiveTab('trading')}
        >
          Trading
        </button>
      </div>

      {/* ─── TAB CONTENT ─── */}
      {activeTab === 'communications' ? <CommunicationsPanel /> : <TradingPanel />}
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════
// COMMUNICATIONS PANEL — unchanged behaviour, just extracted
// ══════════════════════════════════════════════════════════════════

function CommunicationsPanel() {
  const [stats, setStats] = useState(null);
  const [statusData, setStatusData] = useState([]);
  const [trendData, setTrendData] = useState([]);
  const [vendorData, setVendorData] = useState([]);
  const [topClients, setTopClients] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [statsRes, statusRes, trendRes, vendorRes, clientsRes] = await Promise.all([
          dashboardAPI.stats(),
          dashboardAPI.statusChart(),
          dashboardAPI.trendChart(30),
          dashboardAPI.vendorChart(),
          dashboardAPI.topClients(5),
        ]);
        setStats(statsRes.data);
        setStatusData(statusRes.data.data || []);
        setTrendData(trendRes.data.data || []);
        setVendorData(vendorRes.data.data || []);
        setTopClients(clientsRes.data.data || []);
      } catch (err) {
        console.error('Dashboard load error:', err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div style={s.loading}>Loading dashboard...</div>;

  const kpis = [
    { label: 'Sent', value: stats?.sent || 0, icon: CheckCircle, color: '#0D7C4A', bg: '#E3F5EC' },
    { label: 'Failed', value: stats?.failed || 0, icon: AlertTriangle, color: '#C93B3B', bg: '#FDECEC' },
    { label: 'Pending', value: stats?.pending || 0, icon: Clock, color: '#D4A017', bg: '#FFF8E7' },
    { label: 'Total', value: stats?.total || 0, icon: Mail, color: '#1A6DDB', bg: '#E8F1FD' },
  ];

  return (
    <>
      <div style={s.kpiGrid}>
        {kpis.map((kpi) => (
          <div key={kpi.label} style={s.kpiCard}>
            <div style={{ ...s.kpiIcon, background: kpi.bg, color: kpi.color }}>
              <kpi.icon size={20} />
            </div>
            <div>
              <div style={s.kpiValue}>{kpi.value.toLocaleString()}</div>
              <div style={s.kpiLabel}>{kpi.label}</div>
            </div>
          </div>
        ))}
      </div>

      {stats && (
        <div style={s.rateBanner}>
          <span style={s.rateLabel}>Success Rate</span>
          <span style={{ ...s.rateValue, color: stats.success_rate >= 60 ? '#0D7C4A' : '#C93B3B' }}>
            {stats.success_rate >= 60 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
            {stats.success_rate}%
          </span>
        </div>
      )}

      <div style={s.chartRow}>
        <div style={s.chartCard}>
          <h3 style={s.chartTitle}>Status Distribution</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={statusData.map(d => ({ name: d.label, value: d.value }))}
                cx="50%" cy="50%" innerRadius={55} outerRadius={90} dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                labelLine={false} style={{ fontSize: 11 }}
              >
                {statusData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={{ ...s.chartCard, flex: 2 }}>
          <h3 style={s.chartTitle}>Daily Trend (Last 30 Days)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="total" stroke="#1A6DDB" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="sent" stroke="#0D7C4A" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              <Line type="monotone" dataKey="failed" stroke="#C93B3B" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={s.chartRow}>
        <div style={s.chartCard}>
          <h3 style={s.chartTitle}>Vendor Performance</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={vendorData.slice(0, 8)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
              <XAxis dataKey="vendor_id" tick={{ fontSize: 11 }} label={{ value: 'Vendor ID', position: 'bottom', fontSize: 11, offset: -5 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="sent" fill="#0D7C4A" radius={[3, 3, 0, 0]} />
              <Bar dataKey="failed" fill="#C93B3B" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={s.chartCard}>
          <h3 style={s.chartTitle}>Top Clients</h3>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>Client</th>
                <th style={{ ...s.th, textAlign: 'right' }}>Total</th>
                <th style={{ ...s.th, textAlign: 'right' }}>Failed</th>
              </tr>
            </thead>
            <tbody>
              {topClients.map((c, i) => (
                <tr key={i}>
                  <td style={s.td}>{c.receiver}</td>
                  <td style={{ ...s.td, textAlign: 'right', fontWeight: 600 }}>{c.total}</td>
                  <td style={{ ...s.td, textAlign: 'right', color: c.failed > 0 ? '#C93B3B' : '#8B94A6' }}>{c.failed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}


// ══════════════════════════════════════════════════════════════════
// TRADING PANEL — new
// ══════════════════════════════════════════════════════════════════

function TradingPanel() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await dashboardAPI.tradingStats();
        setStats(res.data);
      } catch (err) {
        console.error('Trading stats load error:', err);
        setError(err.response?.data?.detail || 'Could not load trading data');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div style={s.loading}>Loading trading data...</div>;
  if (error) return <div style={s.error}>{error}</div>;
  if (!stats) return <div style={s.loading}>No trading data available</div>;

  // Format big numbers (₹1,23,45,678 → ₹1.23 Cr style if huge)
  const fmtCurrency = (n) => {
    if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)} Cr`;
    if (n >= 100000)   return `₹${(n / 100000).toFixed(2)} L`;
    return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  };

  const buyCount  = stats.by_type?.find(t => t.trade_type === 'BUY')?.count || 0;
  const sellCount = stats.by_type?.find(t => t.trade_type === 'SELL')?.count || 0;

  const kpis = [
    { label: 'Total Trades',    value: stats.total_trades.toLocaleString(),    icon: BarChart3,  color: '#1A6DDB', bg: '#E8F1FD' },
    { label: 'Total Value',     value: fmtCurrency(stats.total_value),         icon: IndianRupee, color: '#0D7C4A', bg: '#E3F5EC' },
    { label: 'Avg Trade Size',  value: fmtCurrency(stats.avg_trade_size),      icon: Activity,   color: '#D4A017', bg: '#FFF8E7' },
    { label: 'Buy / Sell',      value: `${buyCount} / ${sellCount}`,           icon: ArrowUpDown, color: '#6B3FA0', bg: '#F1ECF7' },
  ];

  return (
    <>
      {/* KPI Cards */}
      <div style={s.kpiGrid}>
        {kpis.map((kpi) => (
          <div key={kpi.label} style={s.kpiCard}>
            <div style={{ ...s.kpiIcon, background: kpi.bg, color: kpi.color }}>
              <kpi.icon size={20} />
            </div>
            <div>
              <div style={s.kpiValue}>{kpi.value}</div>
              <div style={s.kpiLabel}>{kpi.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={s.chartRow}>
        {/* Buy vs Sell pie */}
        <div style={s.chartCard}>
          <h3 style={s.chartTitle}>Buy vs Sell</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={stats.by_type.map(t => ({ name: t.trade_type, value: t.count }))}
                cx="50%" cy="50%" innerRadius={55} outerRadius={90} dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                labelLine={false} style={{ fontSize: 11 }}
              >
                <Cell fill="#0D7C4A" />
                <Cell fill="#C93B3B" />
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Top 5 symbols bar */}
        <div style={{ ...s.chartCard, flex: 2 }}>
          <h3 style={s.chartTitle}>Top 5 Symbols by Trade Count</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={stats.top_symbols.map(t => ({ symbol: t.symbol, count: t.count }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
              <XAxis dataKey="symbol" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#1A6DDB" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      
    </>
  );
}


// ══════════════════════════════════════════════════════════════════
// STYLES
// ══════════════════════════════════════════════════════════════════

const s = {
  loading: { padding: 40, textAlign: 'center', color: '#8B94A6', fontSize: 15 },
  error: { padding: 20, color: '#C93B3B', background: '#FDECEC', borderRadius: 8, fontSize: 14 },
  header: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 },
  title: { fontSize: 24, fontWeight: 700, color: '#0F2744', margin: 0 },
  badge: { fontSize: 12, fontWeight: 500, padding: '4px 12px', borderRadius: 20, background: '#EEF2F7', color: '#5A6577' },

  // Tabs
  tabRow: { display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #E8ECF0' },
  tab: {
    background: 'transparent', border: 'none', padding: '10px 18px',
    fontSize: 14, fontWeight: 500, color: '#8B94A6', cursor: 'pointer',
    borderBottom: '2px solid transparent', marginBottom: -1,
  },
  tabActive: {
    background: 'transparent', border: 'none', padding: '10px 18px',
    fontSize: 14, fontWeight: 600, color: '#1A6DDB', cursor: 'pointer',
    borderBottom: '2px solid #1A6DDB', marginBottom: -1,
  },

  kpiGrid: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 },
  kpiCard: { background: '#FFF', borderRadius: 12, padding: '20px 18px', border: '1px solid #E8ECF0', display: 'flex', alignItems: 'center', gap: 14 },
  kpiIcon: { width: 44, height: 44, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  kpiValue: { fontSize: 22, fontWeight: 700, color: '#0F2744', lineHeight: 1.2 },
  kpiLabel: { fontSize: 12, color: '#8B94A6', fontWeight: 400, marginTop: 2 },

  rateBanner: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#FFF', borderRadius: 10, padding: '12px 18px', border: '1px solid #E8ECF0', marginBottom: 20 },
  rateLabel: { fontSize: 13, fontWeight: 500, color: '#5A6577' },
  rateValue: { fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 },

  chartRow: { display: 'flex', gap: 16, marginBottom: 16 },
  chartCard: { flex: 1, background: '#FFF', borderRadius: 12, padding: '18px 20px', border: '1px solid #E8ECF0' },
  chartTitle: { fontSize: 14, fontWeight: 600, color: '#0F2744', margin: '0 0 14px' },

  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { padding: '8px 10px', textAlign: 'left', fontWeight: 500, color: '#8B94A6', borderBottom: '1px solid #F0F2F5', fontSize: 12 },
  td: { padding: '10px 10px', borderBottom: '1px solid #F8F9FA', color: '#2D3748' },

  notice: {
    fontSize: 12, color: '#8B94A6', fontStyle: 'italic',
    padding: '8px 12px', marginTop: 4,
  },
};