import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import { ToastContainer, toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import Dashboard from './pages/Dashboard';
import FaceGallery from './pages/FaceGallery';
import EventLog from './pages/EventLog';
import Alerts from './pages/Alerts';
import VideoUpload from './pages/VideoUpload';
import './App.css';

const TABS = [
  { id: 'upload',    label: '📁 Upload Video' },
  { id: 'dashboard', label: '📊 Dashboard' },
  { id: 'gallery',   label: '🖼️ Faces' },
  { id: 'events',    label: '📋 Events' },
  { id: 'alerts',    label: '🔔 Alerts' },
];

export default function App() {
  const [tab, setTab] = useState('upload');
  const [connected, setConnected] = useState(false);
  const [liveStats, setLiveStats] = useState({ unique_visitors: 0, current_occupancy: 0 });
  const [recentEvents, setRecentEvents] = useState([]);
  const [pipelineStatus, setPipelineStatus] = useState({ running: false, done: false, progress: 0, total_frames: 0 });
  const socketRef = useRef(null);

  useEffect(() => {
    const socket = io(window.location.origin, { transports: ['websocket', 'polling'] });
    socketRef.current = socket;

    socket.on('connect', () => {
      setConnected(true);
      toast.success('🟢 Connected to tracker', { autoClose: 2000 });
    });
    socket.on('disconnect', () => {
      setConnected(false);
      toast.error('🔴 Disconnected');
    });
    socket.on('stats', (data) => setLiveStats(data));
    socket.on('face_event', (data) => {
      setRecentEvents(prev => [
        { ...data, timestamp: new Date().toISOString(), id: Date.now() },
        ...prev.slice(0, 49),
      ]);
      const icon = data.event_type === 'entry' ? '🟢' : '🔴';
      toast.info(`${icon} Face ${data.event_type}: ...${data.face_uuid?.slice(-6)}`,
        { autoClose: 2500, position: 'bottom-right' });
    });
    socket.on('alert', (data) => {
      toast.warning(`⚠️ ${data.message}`, { autoClose: 5000 });
    });
    socket.on('pipeline_status', (data) => {
      setPipelineStatus(data);
      if (data.done && !data.error) {
        toast.success(`✅ Processing complete! ${data.unique_visitors} unique visitors`, { autoClose: 5000 });
        setTab('dashboard');
      }
      if (data.error) {
        toast.error(`❌ Pipeline error: ${data.error}`);
      }
    });

    return () => socket.disconnect();
  }, []);

  const pct = pipelineStatus.total_frames > 0
    ? Math.round((pipelineStatus.progress / pipelineStatus.total_frames) * 100)
    : 0;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-icon">👁️</span>
          <div>
            <div className="logo-title">FaceTracker</div>
            <div className="logo-sub">AI Visitor Counter</div>
          </div>
        </div>

        <nav className="nav">
          {TABS.map(t => (
            <button key={t.id}
              className={`nav-item ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-stats">
          {/* Pipeline progress bar */}
          {pipelineStatus.running && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                Processing… {pct}%
              </div>
              <div style={{ height: 6, background: 'var(--border)', borderRadius: 3 }}>
                <div style={{ height: 6, width: `${pct}%`, background: 'var(--accent-blue)',
                              borderRadius: 3, transition: 'width 0.5s' }} />
              </div>
            </div>
          )}

          <div className="stat-row">
            <span className="stat-label">Unique Visitors</span>
            <span className="stat-val green">{liveStats.unique_visitors}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">In Frame Now</span>
            <span className="stat-val blue">{liveStats.current_occupancy}</span>
          </div>
          <div className="conn-status">
            <span className={`status-dot ${connected ? 'online' : 'offline'}`} />
            {connected ? 'Live' : 'Offline'}
          </div>
        </div>
      </aside>

      <main className="main-content">
        {tab === 'upload'    && <VideoUpload pipelineStatus={pipelineStatus} />}
        {tab === 'dashboard' && <Dashboard liveStats={liveStats} recentEvents={recentEvents} />}
        {tab === 'gallery'   && <FaceGallery />}
        {tab === 'events'    && <EventLog recentEvents={recentEvents} />}
        {tab === 'alerts'    && <Alerts />}
      </main>

      <ToastContainer position="bottom-right" theme="dark" />
    </div>
  );
}