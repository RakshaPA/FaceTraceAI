import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const ACCEPTED = '.mp4,.avi,.mov,.mkv,.webm';

export default function VideoUpload({ pipelineStatus }) {
  const [dragging, setDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [phase, setPhase] = useState('idle'); // idle | uploading | processing | done | stopped | error
  const [error, setError] = useState(null);
  const [frameSkip, setFrameSkip] = useState(null);
  const [clearing, setClearing] = useState(false);
  const inputRef = useRef();

  // Sync phase with pipelineStatus from WebSocket
  // Order matters: stopped must be checked before done
  useEffect(() => {
    if (pipelineStatus.cleared) { setPhase('idle'); return; }
    if (pipelineStatus.stopped) { setPhase('stopped'); return; }
    if (pipelineStatus.running) { setPhase('processing'); return; }
    if (pipelineStatus.done) { setPhase('done'); return; }
  }, [pipelineStatus]);

  // Poll pipeline status via REST as backup for when WebSocket is slow
  useEffect(() => {
    if (phase !== 'processing') return;
    const poll = setInterval(async () => {
      try {
        const res = await axios.get('/api/pipeline-status');
        const s = res.data;
        if (s && s.total_frames > 0) {
          // WebSocket will handle full updates, this just ensures total_frames is known
          if (!pipelineStatus.total_frames) {
            pipelineStatus.total_frames = s.total_frames;
            pipelineStatus.progress = s.progress;
          }
        }
      } catch (e) {}
    }, 1000);
    return () => clearInterval(poll);
  }, [phase]);

  // Fetch adaptive skip stats
  useEffect(() => {
    axios.get('/api/adaptive-skip').then(r => {
      if (!r.data?.error) setFrameSkip(r.data);
    }).catch(() => {});
  }, [phase]);

  const handleDrop = (e) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) { setSelectedFile(f); setError(null); }
  };

  const handleSelect = (e) => {
    if (e.target.files[0]) { setSelectedFile(e.target.files[0]); setError(null); }
  };

  const handleUpload = async () => {
    if (!selectedFile || phase === 'uploading' || phase === 'processing') return;
    setPhase('uploading');
    setError(null);
    const formData = new FormData();
    formData.append('video', selectedFile);
    try {
      await axios.post('/api/upload', formData,
        { headers: { 'Content-Type': 'multipart/form-data' } });
      setPhase('processing'); // will be overridden by WebSocket
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Upload failed');
      setPhase('idle');
    }
  };

  const handleStop = async () => {
    try { await axios.post('/api/stop'); } catch (e) {}
    setPhase('stopped');
  };

  const handleClear = async () => {
    if (!window.confirm('Clear all face data from database?')) return;
    setClearing(true);
    try {
      await axios.post('/api/clear');
      setPhase('idle');
      setSelectedFile(null);
      setError(null);
    } catch (e) {
      alert('Clear failed: ' + (e.response?.data?.error || e.message));
    } finally { setClearing(false); }
  };

  const pct = phase === 'done' ? 100
    : pipelineStatus.total_frames > 0
    ? Math.min(99, Math.round((pipelineStatus.progress / pipelineStatus.total_frames) * 100))
    : 0;

  const showCard = phase !== 'idle';

  return (
    <div>
      <h1 className="page-title">📁 Upload Video</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: 14 }}>
        Upload a video to run the FaceTraceAI pipeline. Supported: MP4, AVI, MOV, MKV, WebM.
      </p>

      {/* Stats bar */}
      {(frameSkip || phase === 'idle') && (
        <div style={{ display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', gap: 10 }}>
            {frameSkip && <>
              <Pill label="Frame Skip" value={`${frameSkip.current_skip}x`} color="var(--accent-orange)" />
              <Pill label="FPS" value={frameSkip.current_fps || '—'} color="var(--accent-green)" />
              <Pill label="CPU" value={frameSkip.current_cpu ? `${frameSkip.current_cpu}%` : '—'}
                color={frameSkip.current_cpu > 80 ? 'var(--accent-red)' : 'var(--accent-blue)'} />
            </>}
          </div>
          <button onClick={handleClear} disabled={clearing || phase === 'processing'}
            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid var(--accent-red)',
              color: 'var(--accent-red)', padding: '6px 14px', borderRadius: 8,
              cursor: 'pointer', fontSize: 13, fontWeight: 600,
              opacity: phase === 'processing' ? 0.4 : 1 }}>
            {clearing ? 'Clearing…' : '🗑️ Clear Old Data'}
          </button>
        </div>
      )}

      {/* Drop zone — only when idle */}
      {(phase === 'idle' || phase === 'done' || phase === 'stopped') && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current.click()}
          style={{
            border: `2px dashed ${dragging ? 'var(--accent-blue)' : 'var(--border)'}`,
            borderRadius: 16, padding: '40px 24px', textAlign: 'center',
            cursor: 'pointer', background: dragging ? 'rgba(59,130,246,0.05)' : 'var(--bg-card)',
            marginBottom: 16, transition: 'all 0.2s',
          }}>
          <div style={{ fontSize: 40, marginBottom: 10 }}>🎬</div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
            {dragging ? 'Drop it!' : 'Drag & drop a video here'}
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>or click to browse</div>
          <input ref={inputRef} type="file" accept={ACCEPTED}
            style={{ display: 'none' }} onChange={handleSelect} />
        </div>
      )}

      {/* Selected file row */}
      {selectedFile && phase !== 'processing' && phase !== 'uploading' && (
        <div className="card" style={{ display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', marginBottom: 16 }}>
          <div>
            <div style={{ fontWeight: 600 }}>📄 {selectedFile.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </div>
          </div>
          <button onClick={handleUpload}
            style={{ background: 'var(--accent-blue)', color: '#fff', border: 'none',
              padding: '10px 24px', borderRadius: 8, cursor: 'pointer',
              fontWeight: 600, fontSize: 14 }}>
            ▶ Start Processing
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid var(--accent-red)',
          borderRadius: 8, padding: 14, color: 'var(--accent-red)', marginBottom: 16 }}>
          ❌ {error}
        </div>
      )}

      {/* Pipeline card */}
      {showCard && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', marginBottom: 12 }}>
            <div className="card-title" style={{ margin: 0 }}>
              {phase === 'uploading' ? '📤 Uploading file…'
                : phase === 'processing' ? '⚙️ Processing…'
                : phase === 'stopped' ? '⏹ Stopped'
                : phase === 'error' ? '❌ Error'
                : '✅ Complete'}
            </div>
            {phase === 'processing' && (
              <button onClick={handleStop}
                style={{ background: 'rgba(239,68,68,0.15)',
                  border: '1px solid var(--accent-red)', color: 'var(--accent-red)',
                  padding: '6px 16px', borderRadius: 8, cursor: 'pointer',
                  fontWeight: 600, fontSize: 13 }}>
                ⏹ Stop
              </button>
            )}
          </div>



          {/* Progress bar */}
          <div style={{ height: 10, background: 'var(--border)', borderRadius: 5, marginBottom: 10 }}>
            <div style={{
              height: 10,
              width: phase === 'uploading' ? '5%' : `${pct}%`,
              background: phase === 'stopped' ? 'var(--accent-orange)'
                : phase === 'error' ? 'var(--accent-red)'
                : phase === 'done' ? 'var(--accent-green)'
                : 'var(--accent-blue)',
              borderRadius: 5, transition: 'width 0.4s ease',
            }} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between',
            fontSize: 13, color: 'var(--text-muted)' }}>
            <span>
              {phase === 'uploading' ? 'Uploading…'
                : `Frame ${pipelineStatus.progress} / ${pipelineStatus.total_frames || '?'}`}
            </span>
            <span style={{ fontWeight: 700,
              color: phase === 'done' ? 'var(--accent-green)'
                : phase === 'stopped' ? 'var(--accent-orange)' : 'var(--text-primary)' }}>
              {phase === 'uploading' ? '' : `${pct}%`}
            </span>
          </div>

          {phase === 'done' && (
            <div style={{ marginTop: 10, fontSize: 13, color: 'var(--accent-green)' }}>
              ✅ Processing complete. Check Dashboard, Faces, and Events tabs for results.
            </div>
          )}

          {phase === 'stopped' && (
            <div style={{ marginTop: 10, fontSize: 13, color: 'var(--accent-orange)' }}>
              Processing stopped at frame {pipelineStatus.progress}.
              {pipelineStatus.unique_visitors > 0 &&
                ` ${pipelineStatus.unique_visitors} unique visitors detected so far.`}
            </div>
          )}
        </div>
      )}

      {/* How it works */}
      {phase === 'idle' && !selectedFile && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title" style={{ marginBottom: 10 }}>How it works</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 2 }}>
            <div>1️⃣ &nbsp;Select or drag a video file above</div>
            <div>2️⃣ &nbsp;Click <strong style={{ color: 'var(--text-primary)' }}>Start Processing</strong></div>
            <div>3️⃣ &nbsp;Watch real-time progress — faces detected as they appear</div>
            <div>4️⃣ &nbsp;When done, view results in <strong style={{ color: 'var(--text-primary)' }}>Dashboard → Faces → Events</strong></div>
          </div>
        </div>
      )}
    </div>
  );
}

function Pill({ label, value, color }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '4px 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 700, color }}>{value}</span>
    </div>
  );
}