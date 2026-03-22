import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement,
  LineElement, PointElement, Title, Tooltip, Legend, ArcElement, Filler
} from 'chart.js';
import { Bar, Doughnut } from 'react-chartjs-2';
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
    y: {
      ticks: { color: '#94a3b8', stepSize: 1 },
      grid: { color: 'rgba(45,49,72,0.5)' },
      beginAtZero: true,
    },
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
        axios.get('/api/hourly?hours=24'),
        axios.get('/api/faces'),
      ]);
      setStats(sRes.data);
      setHourly(hRes.data);
      setFaces(fRes.data);
    } catch (e) {}
  };

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 10000);
    return () => clearInterval(t);
  }, []);

  // --- Bar chart: pad to last 12 hours so X-axis always has context ---
  const now = new Date();
  const last12Hours = Array.from({ length: 12 }, (_, i) => {
    const d = new Date(now);
    d.setHours(d.getHours() - (11 - i), 0, 0, 0);
    return d;
  });

  const hourMap = {};
  hourly.forEach(h => {
    const key = new Date(h.hour).getHours();
    hourMap[key] = h;
  });

  const hourLabels = last12Hours.map(d => `${d.getHours()}:00`);
  const entriesData = last12Hours.map(d => hourMap[d.getHours()]?.total_entries || 0);
  const exitsData = last12Hours.map(d => hourMap[d.getHours()]?.total_exits || 0);

  const visitorChart = {
    labels: hourLabels,
    datasets: [
      { label: 'Entries', data: entriesData,
        backgroundColor: 'rgba(34,197,94,0.7)', borderRadius: 4 },
      { label: 'Exits', data: exitsData,
        backgroundColor: 'rgba(239,68,68,0.7)', borderRadius: 4 },
    ],
  };

  // --- Demographics: count from faces ---
  const genderCounts = { M: 0, F: 0, Unknown: 0 };
  faces.forEach(f => {
    const g = f.metadata?.gender;
    if (g === 'M' || g === 1 || g === '1') genderCounts.M++;
    else if (g === 'F' || g === 0 || g === '0') genderCounts.F++;
    else genderCounts.Unknown++;
  });

  // Only show segments with data
  const genderLabels = [];
  const genderData = [];
  const genderColors = [];
  if (genderCounts.M > 0) { genderLabels.push('Male'); genderData.push(genderCounts.M); genderColors.push('rgba(59,130,246,0.85)'); }
  if (genderCounts.F > 0) { genderLabels.push('Female'); genderData.push(genderCounts.F); genderColors.push('rgba(168,85,247,0.85)'); }
  if (genderCounts.Unknown > 0) { genderLabels.push('Unknown'); genderData.push(genderCounts.Unknown); genderColors.push('rgba(148,163,184,0.4)'); }

  const hasDemographics = genderData.length > 0 && genderData.some(v => v > 0);

  const genderChart = {
    labels: genderLabels.length ? genderLabels : ['No data'],
    datasets: [{
      data: genderData.length ? genderData : [1],
      backgroundColor: genderColors.length ? genderColors : ['rgba(148,163,184,0.2)'],
      borderWidth: 0,
    }],
  };

  const dwell = stats?.dwell || {};
  const unique = liveStats?.unique_visitors ?? stats?.unique_visitors ?? 0;
  const occupancy = liveStats?.current_occupancy ?? stats?.current_occupancy ?? 0;

  return (
    <div>
      <h1 className="page-title">📊 Dashboard</h1>

      <div className="grid-4">
        <KpiCard title="Unique Visitors" value={unique} color="#22c55e" icon="👤" />
        <KpiCard title="In Frame Now" value={occupancy} color="#3b82f6" icon="📹" />
        <KpiCard title="Avg Dwell" value={dwell.avg ? `${dwell.avg.toFixed(0)}s` : '—'} color="#f97316" icon="⏱️" />
        <KpiCard title="Total Sessions" value={dwell.count ?? '—'} color="#a855f7" icon="🔄" />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">Hourly Traffic (last 24h)</div>
          <Bar data={visitorChart} options={CHART_OPTS} height={120} />
        </div>

        <div className="card">
          <div className="card-title">Demographics (InsightFace Estimates)</div>
          {hasDemographics ? (
            <>
              <div style={{ maxWidth: 180, margin: '0 auto' }}>
                <Doughnut data={genderChart} options={{
                  responsive: true, cutout: '65%',
                  plugins: { legend: { position: 'bottom',
                    labels: { color: '#94a3b8', padding: 12 } } },
                }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: 16,
                marginTop: 8, flexWrap: 'wrap' }}>
                {genderCounts.M > 0 && <StatTag label="Male" value={genderCounts.M} color="#3b82f6" />}
                {genderCounts.F > 0 && <StatTag label="Female" value={genderCounts.F} color="#a855f7" />}
                {genderCounts.Unknown > 0 && <StatTag label="Unknown" value={genderCounts.Unknown} color="#64748b" />}
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)',
              padding: '40px 0', fontSize: 13 }}>
              No demographic data yet.<br />
              <span style={{ fontSize: 11 }}>InsightFace estimates age/gender on registration.</span>
            </div>
          )}
        </div>
      </div>

      {/* Live event feed */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 16 }}>
          Live Event Feed <span className="pulse-dot" style={{ marginLeft: 8 }} />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Type</th><th>Face ID</th><th>Time</th><th>Dwell</th>
              </tr>
            </thead>
            <tbody>
              {recentEvents.slice(0, 10).map(ev => (
                <tr key={ev.id}>
                  <td><span className={`badge badge-${ev.event_type}`}>{ev.event_type}</span></td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                    ...{ev.face_uuid?.slice(-8)}
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>
                    {formatDistanceToNow(new Date(ev.timestamp), { addSuffix: true })}
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>
                    {ev.extra?.dwell ? `${parseFloat(ev.extra.dwell).toFixed(1)}s` : '—'}
                  </td>
                </tr>
              ))}
              {recentEvents.length === 0 && (
                <tr><td colSpan={4} style={{ color: 'var(--text-muted)',
                  textAlign: 'center', padding: 20 }}>
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

function StatTag({ label, value, color }) {
  return (
    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
      <span style={{ display: 'inline-block', width: 10, height: 10,
        borderRadius: 2, background: color, marginRight: 4 }} />
      {label}: <strong style={{ color: 'var(--text-primary)' }}>{value}</strong>
    </div>
  );
}