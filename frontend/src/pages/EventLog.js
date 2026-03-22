import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { format } from 'date-fns';

export default function EventLog({ recentEvents }) {
  const [dbEvents, setDbEvents] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  const fetchEvents = async () => {
    try {
      const res = await axios.get('/api/events?limit=200');
      setDbEvents(res.data);  // always overwrite with fresh DB data
    } catch (e) {}
    setLoading(false);
  };

  useEffect(() => {
    fetchEvents();
    const t = setInterval(fetchEvents, 10000);
    return () => clearInterval(t);
  }, []);

  // DB is source of truth — live events are only shown if not yet in DB
  const allEvents = [...dbEvents];
  recentEvents.forEach(live => {
    const alreadyInDb = allEvents.find(e =>
      e.face_uuid === live.face_uuid &&
      Math.abs(new Date(e.timestamp) - new Date(live.timestamp)) < 3000
    );
    if (!alreadyInDb) {
      allEvents.unshift({ ...live, source: 'live' });
    }
  });

  const filtered = filter === 'all' ? allEvents : allEvents.filter(e => e.event_type === filter);

  const entries = allEvents.filter(e => e.event_type === 'entry').length;
  const exits = allEvents.filter(e => e.event_type === 'exit').length;

  return (
    <div>
      <h1 className="page-title">📋 Event Log</h1>

      {/* Summary */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-title">Total Events</div>
          <div className="card-value" style={{ color: 'var(--accent-blue)' }}>{allEvents.length}</div>
        </div>
        <div className="card">
          <div className="card-title">Entries</div>
          <div className="card-value" style={{ color: 'var(--accent-green)' }}>{entries}</div>
        </div>
        <div className="card">
          <div className="card-title">Exits</div>
          <div className="card-value" style={{ color: 'var(--accent-red)' }}>{exits}</div>
        </div>
        <div className="card">
          <div className="card-title">Balance</div>
          <div className="card-value" style={{ color: 'var(--accent-orange)' }}>{entries - exits}</div>
        </div>
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['all', 'entry', 'exit'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '6px 16px', borderRadius: 6, border: '1px solid var(--border)',
              background: filter === f ? 'var(--accent-blue)' : 'var(--bg-card)',
              color: filter === f ? '#fff' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: 13, fontWeight: 500, textTransform: 'capitalize',
            }}
          >{f}</button>
        ))}
      </div>

      <div className="card">
        <div className="table-wrap">
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Loading events…</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Type</th>
                  <th>Face UUID</th>
                  <th>Timestamp</th>
                  <th>Frame</th>
                  <th>Confidence</th>
                  <th>Image</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 100).map((ev, i) => (
                  <tr key={ev.id || i}>
                    <td style={{ color: 'var(--text-muted)', fontSize: 11 }}>{ev.id || '—'}</td>
                    <td><span className={`badge badge-${ev.event_type}`}>{ev.event_type}</span></td>
                    <td style={{ fontFamily: 'monospace', fontSize: 11 }}>
                      {ev.face_uuid?.slice(0, 8)}…{ev.face_uuid?.slice(-4)}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {ev.timestamp ? format(new Date(ev.timestamp), 'MMM d, HH:mm:ss') : '—'}
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{ev.frame_number || '—'}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                      {ev.confidence != null ? `${(ev.confidence * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td>
                      {ev.image_path ? (
                        <img
                          src={`/logs/${ev.image_path.replace(/\\/g, '/').replace(/.*logs\//, '')}`}
                          alt="crop"
                          style={{ width: 40, height: 40, borderRadius: 6, objectFit: 'cover',
                            border: '1px solid var(--border)', cursor: 'pointer' }}
                          onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'inline'; }}
                          title={ev.image_path}
                        />
                      ) : null}
                      <span style={{ color: 'var(--text-muted)', fontSize: 11,
                        display: ev.image_path ? 'none' : 'inline' }}>—</span>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>
                      No events yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}