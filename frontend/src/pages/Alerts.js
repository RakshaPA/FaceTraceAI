import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { format } from 'date-fns';

const SEVERITY_COLOURS = {
  info: 'var(--accent-blue)',
  warning: 'var(--accent-orange)',
  critical: 'var(--accent-red)',
};

const TYPE_ICONS = {
  crowd_threshold: '👥',
  loitering: '⏳',
  watchlist: '⚠️',
  default: '🔔',
};

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAlerts = async () => {
    try {
      const res = await axios.get('/api/alerts?limit=100');
      setAlerts(res.data);
    } catch (e) {}
    setLoading(false);
  };

  useEffect(() => {
    fetchAlerts();
    const t = setInterval(fetchAlerts, 8000);
    return () => clearInterval(t);
  }, []);

  const byCounts = alerts.reduce((acc, a) => {
    acc[a.alert_type] = (acc[a.alert_type] || 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <h1 className="page-title">🔔 System Alerts</h1>

      {/* Summary Cards */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <div className="card">
          <div className="card-title">Total Alerts</div>
          <div className="card-value" style={{ color: 'var(--accent-orange)' }}>{alerts.length}</div>
        </div>
        <div className="card">
          <div className="card-title">👥 Crowd</div>
          <div className="card-value" style={{ color: 'var(--accent-blue)' }}>{byCounts.crowd_threshold || 0}</div>
        </div>
        <div className="card">
          <div className="card-title">⏳ Loitering</div>
          <div className="card-value" style={{ color: 'var(--accent-purple)' }}>{byCounts.loitering || 0}</div>
        </div>
        <div className="card">
          <div className="card-title">⚠️ Watchlist</div>
          <div className="card-value" style={{ color: 'var(--accent-red)' }}>{byCounts.watchlist || 0}</div>
        </div>
      </div>

      {/* Alert list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {loading && (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>Loading alerts…</div>
        )}
        {!loading && alerts.length === 0 && (
          <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
            No alerts generated yet.
          </div>
        )}
        {alerts.map(alert => (
          <div
            key={alert.id}
            className="card"
            style={{
              borderLeft: `4px solid ${SEVERITY_COLOURS[alert.severity] || SEVERITY_COLOURS.info}`,
              display: 'flex', gap: 16, alignItems: 'flex-start',
            }}
          >
            <div style={{ fontSize: 24, flexShrink: 0 }}>
              {TYPE_ICONS[alert.alert_type] || TYPE_ICONS.default}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{
                  fontSize: 12, fontWeight: 700, textTransform: 'uppercase',
                  color: SEVERITY_COLOURS[alert.severity] || SEVERITY_COLOURS.info,
                }}>
                  {alert.alert_type.replace(/_/g, ' ')}
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {alert.timestamp ? format(new Date(alert.timestamp), 'MMM d, HH:mm:ss') : '—'}
                </span>
              </div>
              <div style={{ fontSize: 14, color: 'var(--text-primary)', marginBottom: 4 }}>{alert.message}</div>
              {alert.face_uuid && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                  Face: {alert.face_uuid}
                </div>
              )}
              {alert.extra && Object.keys(alert.extra).length > 0 && (
                <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {Object.entries(alert.extra).map(([k, v]) => (
                    <span key={k} style={{
                      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                      borderRadius: 4, padding: '2px 8px', fontSize: 11, color: 'var(--text-muted)',
                    }}>
                      {k}: {typeof v === 'number' ? v.toFixed(1) : String(v)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}