import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement,
  LineElement, PointElement, Title, Tooltip, Legend, ArcElement, Filler
} from 'chart.js';
import { Bar, Line, Doughnut } from 'react-chartjs-2';
import { formatDistanceToNow } from 'date-fns';

ChartJS.register(
  CategoryScale, LinearScale, BarElement, LineElement, PointElement,
  Title, Tooltip, Legend, ArcElement, Filler
);

const CHART_OPTS = {
  responsive: true,
  plugins: { legend: { labels: { color: '#94a3b8', font: { size: 12 } } } },
  scales: {
    x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(45,49,72,0.5)' } },
    y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(45,49,72,0.5)' } },
  },
};

export default function Dashboard({ liveStats, recentEvents }) {
  const [stats, setStats] = useState(null);
  const [hourly, setHourly] = useState([]);
  const [faces, setFaces] = useState([]);

  const fetchAll = async () => {
    try {
      const [sRes, hRes, fRes] = await Promise.all([
        axios.get('/api/stats'),
        axios.get('/api/hourly?hours=12'),
        axios.get('/api/faces'),
      ]);
      setStats(sRes.data);
      setHourly(hRes.data);
      setFaces(fRes.data);
    } catch (e) { /* API might not be up yet */ }
  };

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 10000);
    return () => clearInterval(t);
  }, []);

  // --- Chart data ---
  const hourLabels = hourly.map(h => {
    const d = new Date(h.hour);
    return `${d.getHours()}:00`;
  });

  const visitorChart = {
    labels: hourLabels,
    datasets: [
      {
        label: 'Entries',
        data: hourly.map(h => h.total_entries),
        backgroundColor: 'rgba(34,197,94,0.7)',
        borderRadius: 4,
      },
      {
        label: 'Exits',
        data: hourly.map(h => h.total_exits),
        backgroundColor: 'rgba(239,68,68,0.7)',
        borderRadius: 4,
      },
    ],
  };

  // Gender/age distribution from faces metadata
  const genderCounts = { M: 0, F: 0, Unknown: 0 };
  faces.forEach(f => {
    const g = f.metadata?.gender;
    if (g === 'M') genderCounts.M++;
    else if (g === 'F') genderCounts.F++;
    else genderCounts.Unknown++;
  });

  const genderChart = {
    labels: ['Male', 'Female', 'Unknown'],
    datasets: [{
      data: [genderCounts.M, genderCounts.F, genderCounts.Unknown],
      backgroundColor: ['rgba(59,130,246,0.8)', 'rgba(168,85,247,0.8)', 'rgba(148,163,184,0.5)'],
      borderWidth: 0,
    }],
  };

  const dwell = stats?.dwell || {};
  const unique = liveStats?.unique_visitors ?? stats?.unique_visitors ?? 0;
  const occupancy = liveStats?.current_occupancy ?? stats?.current_occupancy ?? 0;

  return (
    <div>
      <h1 className="page-title">📊 Dashboard</h1>

      {/* KPI cards */}
      <div className="grid-4">
        <KpiCard title="Unique Visitors" value={unique} color="#22c55e" icon="👤" />
        <KpiCard title="In Frame Now" value={occupancy} color="#3b82f6" icon="📹" />
        <KpiCard title="Avg Dwell" value={dwell.avg ? `${dwell.avg.toFixed(0)}s` : '—'} color="#f97316" icon="⏱️" />
        <KpiCard title="Total Sessions" value={dwell.count ?? '—'} color="#a855f7" icon="🔄" />
      </div>

      {/* Charts row */}
      <div className="grid-2">
        <div className="card">
          <div className="card-title">Hourly Traffic (last 12h)</div>
          <Bar data={visitorChart} options={CHART_OPTS} height={120} />
        </div>
        <div className="card">
          <div className="card-title">Demographics (InsightFace Estimates)</div>
          <div style={{ maxWidth: 200, margin: '0 auto' }}>
            <Doughnut
              data={genderChart}
              options={{
                responsive: true,
                plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8' } } },
                cutout: '65%',
              }}
            />
          </div>
        </div>
      </div>

      {/* Live event feed */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 16 }}>
          Live Event Feed
          <span className="pulse-dot" style={{ marginLeft: 8 }} />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Face ID</th>
                <th>Time</th>
                <th>Dwell</th>
              </tr>
            </thead>
            <tbody>
              {recentEvents.slice(0, 10).map(ev => (
                <tr key={ev.id}>
                  <td><span className={`badge badge-${ev.event_type}`}>{ev.event_type}</span></td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>...{ev.face_uuid?.slice(-8)}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{formatDistanceToNow(new Date(ev.timestamp), { addSuffix: true })}</td>
                  <td style={{ color: 'var(--text-muted)' }}>
                    {ev.extra?.dwell ? `${parseFloat(ev.extra.dwell).toFixed(1)}s` : '—'}
                  </td>
                </tr>
              ))}
              {recentEvents.length === 0 && (
                <tr><td colSpan={4} style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
                  Waiting for events…
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ title, value, color, icon }) {
  return (
    <div className="card" style={{ borderTop: `3px solid ${color}` }}>
      <div className="card-title">{icon} {title}</div>
      <div className="card-value" style={{ color }}>{value}</div>
    </div>
  );
}
