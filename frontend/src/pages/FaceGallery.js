import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { formatDistanceToNow } from 'date-fns';

export default function FaceGallery() {
  const [faces, setFaces] = useState([]);
  const [search, setSearch] = useState('');
  const [filterWatchlist, setFilterWatchlist] = useState(false);
  const [selectedFace, setSelectedFace] = useState(null);

  const fetchFaces = async () => {
    try {
      const res = await axios.get('/api/faces');
      setFaces(res.data);
    } catch (e) {}
  };

  useEffect(() => {
    fetchFaces();
    const t = setInterval(fetchFaces, 8000);
    return () => clearInterval(t);
  }, []);

  const toggleWatchlist = async (face) => {
    try {
      const removing = face.is_watchlist;
      await axios.post(`/api/watchlist/${face.face_uuid}`, {
        label: removing ? '' : (face.label || 'Watchlist'),
        remove: removing,
      });
      // Update selectedFace immediately so modal button toggles right away
      if (selectedFace && selectedFace.face_uuid === face.face_uuid) {
        setSelectedFace(prev => ({ ...prev, is_watchlist: !removing, label: removing ? '' : 'Watchlist' }));
      }
      fetchFaces();
    } catch (e) {}
  };

  const filtered = faces.filter(f => {
    const matchSearch = f.face_uuid.includes(search) || (f.label || '').toLowerCase().includes(search.toLowerCase());
    const matchWatchlist = filterWatchlist ? f.is_watchlist : true;
    return matchSearch && matchWatchlist;
  });

  return (
    <div>
      <h1 className="page-title">🖼️ Registered Faces</h1>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
        <input
          className="search-input"
          placeholder="Search by ID or label…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-primary)',
            padding: '8px 14px', borderRadius: 8, fontSize: 13, width: 260,
          }}
        />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer' }}>
          <input type="checkbox" checked={filterWatchlist} onChange={e => setFilterWatchlist(e.target.checked)} />
          Watchlist only
        </label>
        <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 13 }}>
          {filtered.length} / {faces.length} faces
        </span>
      </div>

      {/* Grid */}
      <div className="face-grid">
        {filtered.map(face => (
          <div
            key={face.face_uuid}
            className={`face-card ${face.is_watchlist ? 'watchlist' : ''}`}
            onClick={() => setSelectedFace(face)}
            style={{ cursor: 'pointer' }}
          >
            {face.thumbnail_path ? (
              <img
                className="face-avatar"
                src={`/logs/${face.thumbnail_path.replace(/\\/g, '/').replace(/.*logs\//, '')}`}
                alt="face"
                onError={e => { e.target.style.display = 'none'; }}
              />
            ) : (
              <div className="face-avatar" style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 28, background: 'var(--bg-secondary)',
              }}>👤</div>
            )}
            {face.is_watchlist && (
              <div style={{ marginBottom: 4 }}><span className="badge badge-watchlist">⚠ Watchlist</span></div>
            )}
            {face.label && (
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{face.label}</div>
            )}
            <div className="face-id">…{face.face_uuid.slice(-10)}</div>
            <div className="face-count">{face.visit_count}</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>visits</div>
            {face.metadata?.gender && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                {face.metadata.gender === 'M' ? '♂ Male' : '♀ Female'}
                {face.metadata.age ? `, ~${face.metadata.age}yr` : ''}
              </div>
            )}
          </div>
        ))}
        {filtered.length === 0 && (
          <div style={{ gridColumn: '1/-1', textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
            No faces registered yet.
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedFace && (
        <FaceModal face={selectedFace} onClose={() => setSelectedFace(null)} onToggleWatchlist={toggleWatchlist} />
      )}
    </div>
  );
}

function FaceModal({ face, onClose, onToggleWatchlist }) {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    axios.get(`/api/events?limit=100`).then(res => {
      setEvents(res.data.filter(e => e.face_uuid === face.face_uuid));
    }).catch(() => {});
  }, [face.face_uuid]);

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 100,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 16,
          padding: 28, width: 500, maxHeight: '80vh', overflow: 'auto',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700 }}>Face Detail</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>

        <div style={{ display: 'flex', gap: 20, marginBottom: 20 }}>
          <div style={{ width: 80, height: 80, borderRadius: 12, flexShrink: 0,
            background: 'var(--bg-secondary)', overflow: 'hidden',
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {face.thumbnail_path ? (
              <img
                src={`/logs/${face.thumbnail_path.replace(/\\/g, '/').replace(/.*logs\//, '')}`}
                alt="face"
                style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 12 }}
                onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
              />
            ) : null}
            <div style={{ display: face.thumbnail_path ? 'none' : 'flex',
              width: 80, height: 80, alignItems: 'center', justifyContent: 'center',
              fontSize: 32, borderRadius: 12, background: 'var(--bg-secondary)' }}>👤</div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>{face.face_uuid}</div>
            <div style={{ fontSize: 13, marginBottom: 4 }}>
              <span style={{ color: 'var(--text-muted)' }}>First seen: </span>
              {new Date(face.first_seen).toLocaleString()}
            </div>
            <div style={{ fontSize: 13, marginBottom: 4 }}>
              <span style={{ color: 'var(--text-muted)' }}>Visits: </span>
              <strong style={{ color: 'var(--accent-blue)' }}>{face.visit_count}</strong>
            </div>
            {face.metadata?.gender && (
              <div style={{ fontSize: 13 }}>
                <span style={{ color: 'var(--text-muted)' }}>Estimated: </span>
                {face.metadata.gender === 'M' ? 'Male' : 'Female'}
                {face.metadata.age ? `, ~${face.metadata.age} years` : ''}
              </div>
            )}
          </div>
        </div>

        <button
          onClick={() => onToggleWatchlist(face)}
          style={{
            background: face.is_watchlist ? 'rgba(239,68,68,0.15)' : 'rgba(249,115,22,0.15)',
            border: `1px solid ${face.is_watchlist ? '#ef4444' : '#f97316'}`,
            color: face.is_watchlist ? '#ef4444' : '#f97316',
            padding: '6px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 13, marginBottom: 20,
          }}
        >
          {face.is_watchlist ? '✓ On Watchlist — Click to Remove' : '+ Add to Watchlist'}
        </button>

        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 10 }}>RECENT EVENTS</div>
        {events.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No events found.</div>
        ) : (
          events.slice(0, 10).map(ev => (
            <div key={ev.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 0', borderBottom: '1px solid var(--border)',
            }}>
              <span className={`badge badge-${ev.event_type}`}>{ev.event_type}</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{new Date(ev.timestamp).toLocaleString()}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}