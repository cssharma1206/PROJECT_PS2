/**
 * QueryChart.jsx
 * ───────────────
 * Renders a chart for a query result.
 * Receives the output of detectChart() plus the raw data.
 *
 * Supported types:
 *   - kpi          → big number card
 *   - bar          → vertical bar chart
 *   - pie          → pie chart with labels
 *   - line         → line chart (one or more series)
 *   - groupedBar   → grouped bar (e.g. AppName × ServiceType × Count)
 *
 * Props:
 *   type   - one of the above
 *   config - shape depends on type (see chartDetector.js)
 *   data   - array of row objects from the query result
 */

import {
  BarChart, Bar,
  LineChart, Line,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

// Palette matches Dashboard for visual consistency
const COLORS = ['#1A6DDB', '#0D7C4A', '#C93B3B', '#D4A017', '#6B3FA0', '#0E7C86', '#C2185B', '#5E9C3F'];

export default function QueryChart({ type, config, data }) {
  if (!type || !config || !data || data.length === 0) return null;

  switch (type) {
    case 'kpi':
      return <KpiCard config={config} data={data} />;
    case 'bar':
      return <BarView config={config} data={data} />;
    case 'pie':
      return <PieView config={config} data={data} />;
    case 'line':
      return <LineView config={config} data={data} />;
    case 'groupedBar':
      return <GroupedBarView config={config} data={data} />;
    default:
      return null;
  }
}

// ─── KPI CARD ────────────────────────────────────────────────────────────

function KpiCard({ config, data }) {
  const value = data[0][config.valueKey];
  return (
    <div style={s.kpiWrap}>
      <div style={s.kpiValue}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      <div style={s.kpiLabel}>{config.label}</div>
    </div>
  );
}

// ─── BAR ─────────────────────────────────────────────────────────────────

function BarView({ config, data }) {
  return (
    <div style={s.chartWrap}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
          <XAxis
            dataKey={config.labelKey}
            tick={{ fontSize: 11 }}
            angle={-25}
            textAnchor="end"
            interval={0}
          />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey={config.valueKey} fill={COLORS[0]} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── PIE ─────────────────────────────────────────────────────────────────

function PieView({ config, data }) {
  return (
    <div style={s.chartWrap}>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            dataKey={config.valueKey}
            nameKey={config.labelKey}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={90}
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
            labelLine={false}
            style={{ fontSize: 11 }}
          >
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── LINE ────────────────────────────────────────────────────────────────

function LineView({ config, data }) {
  return (
    <div style={s.chartWrap}>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
          <XAxis dataKey={config.xKey} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {config.yKeys.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── GROUPED BAR ─────────────────────────────────────────────────────────
// Pivots [{group, series, value}, ...] into [{group, series1: v, series2: v}, ...]
// then renders one Bar per unique series value.

function GroupedBarView({ config, data }) {
  const { groupKey, seriesKey, valueKey } = config;

  // Pivot: collect unique series values
  const seriesValues = [...new Set(data.map((r) => r[seriesKey]))];

  // Build pivoted rows: one per unique group value
  const groupValues = [...new Set(data.map((r) => r[groupKey]))];
  const pivoted = groupValues.map((g) => {
    const row = { [groupKey]: g };
    seriesValues.forEach((s) => {
      const match = data.find((r) => r[groupKey] === g && r[seriesKey] === s);
      row[s] = match ? match[valueKey] : 0;
    });
    return row;
  });

  return (
    <div style={s.chartWrap}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={pivoted} margin={{ top: 10, right: 20, left: 0, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
          <XAxis
            dataKey={groupKey}
            tick={{ fontSize: 11 }}
            angle={-25}
            textAnchor="end"
            interval={0}
          />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {seriesValues.map((sv, i) => (
            <Bar key={sv} dataKey={sv} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── STYLES ──────────────────────────────────────────────────────────────

const s = {
  chartWrap: {
    background: '#FFF',
    border: '1px solid #E8ECF0',
    borderRadius: 8,
    padding: '12px 14px',
    marginTop: 10,
    marginBottom: 6,
  },
  kpiWrap: {
    background: '#E1F0FF',
    border: '1px solid #1A6DDB',
    borderRadius: 8,
    padding: '20px 24px',
    marginTop: 10,
    marginBottom: 6,
    textAlign: 'center',
  },
  kpiValue: {
    fontSize: 32,
    fontWeight: 700,
    color: '#0F2744',
    lineHeight: 1.2,
  },
  kpiLabel: {
    fontSize: 12,
    color: '#5A6577',
    marginTop: 6,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
};