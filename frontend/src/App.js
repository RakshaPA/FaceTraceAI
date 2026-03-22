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
  const [darkMode, setDarkMode] = useState(true);
  const [liveStats, setLiveStats] = useState({ unique_visitors: 0, current_occupancy: 0 });
  const [recentEvents, setRecentEvents] = useState([]);
  const [pipelineStatus, setPipelineStatus] = useState({
    running: false, done: false, progress: 0, total_frames: 0, unique_visitors: 0
  });
  const socketRef = useRef(null);
  // Throttle face toasts — max 1 per second
  const lastToastTime = useRef(0);

  useEffect(() => {
    // Apply theme to root
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    const socket = io(window.location.origin, { transports: ['websocket', 'polling'] });
    socketRef.current = socket;

    socket.on('connect', () => {
      setConnected(true);
      toast.success('🟢 Connected to FaceTraceAI', { autoClose: 2000 });
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
      // Throttle toasts — max 1 per 2 seconds to avoid spam
      const now = Date.now();
      if (now - lastToastTime.current > 2000) {
        lastToastTime.current = now;
        const icon = data.event_type === 'entry' ? '🟢' : '🔴';
        toast.info(`${icon} Face ${data.event_type}: ...${data.face_uuid?.slice(-6)}`,
          { autoClose: 2000, position: 'bottom-right' });
      }
    });

    socket.on('alert', (data) => {
      toast.warning(`⚠️ ${data.message}`, { autoClose: 4000 });
    });

    socket.on('pipeline_status', (data) => {
      // If DB was cleared, reset all local state
      if (data.cleared) {
        setRecentEvents([]);
        setLiveStats({ unique_visitors: 0, current_occupancy: 0 });
        setPipelineStatus({ running: false, done: false, progress: 0,
          total_frames: 0, unique_visitors: 0 });
        return;
      }
      setPipelineStatus(data);
      if (data.done && !data.error) {
        toast.success(`✅ Done! ${data.unique_visitors} unique visitors`, { autoClose: 5000 });
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
    <div className={`app ${darkMode ? '' : 'light-mode'}`}>
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-icon">🎯</span>
          <div>
            <div className="logo-title">FaceTraceAI</div>
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
          {/* Processing progress bar */}
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

          {/* Dark/Light mode toggle */}
          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center',
            justifyContent: 'space-between' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {darkMode ? '🌙 Dark' : '☀️ Light'}
            </span>
            <div onClick={() => setDarkMode(!darkMode)}
              style={{
                width: 44, height: 24, borderRadius: 12, cursor: 'pointer',
                background: darkMode ? 'var(--accent-blue)' : '#e2e8f0',
                position: 'relative', transition: 'background 0.3s',
              }}>
              <div style={{
                width: 18, height: 18, borderRadius: '50%', background: '#fff',
                position: 'absolute', top: 3,
                left: darkMode ? 23 : 3,
                transition: 'left 0.3s',
              }} />
            </div>
          </div>

          <div className="conn-status" style={{ marginTop: 8 }}>
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

      <ToastContainer position="bottom-right" theme={darkMode ? 'dark' : 'light'}
        limit={3} />
    </div>
  );
}