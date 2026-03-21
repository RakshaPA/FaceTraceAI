import React, { useState, useRef } from 'react';
import axios from 'axios';

const ACCEPTED = '.mp4,.avi,.mov,.mkv,.webm';

export default function VideoUpload({ pipelineStatus }) {
  const [dragging, setDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) setSelectedFile(file);
  };

  const handleSelect = (e) => {
    if (e.target.files[0]) setSelectedFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setError(null);
    setUploadResult(null);

    const formData = new FormData();
    formData.append('video', selectedFile);

    try {
      const res = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (p) => {
          // upload progress (not processing progress)
        },
      });
      setUploadResult(res.data);
    } catch (e) {
      setError(e.response?.data?.error || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const pct = pipelineStatus.total_frames > 0
    ? Math.round((pipelineStatus.progress / pipelineStatus.total_frames) * 100)
    : 0;

  return (
    <div>
      <h1 className="page-title">📁 Upload Video</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 24, fontSize: 14 }}>
        Upload a video file to run the face tracker pipeline on it. Supported formats: MP4, AVI, MOV, MKV, WebM.
      </p>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--accent-blue)' : 'var(--border)'}`,
          borderRadius: 16,
          padding: '48px 24px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragging ? 'rgba(59,130,246,0.05)' : 'var(--bg-card)',
          transition: 'all 0.2s',
          marginBottom: 20,
        }}
      >
        <div style={{ fontSize: 48, marginBottom: 12 }}>🎬</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6, color: 'var(--text-primary)' }}>
          {dragging ? 'Drop it!' : 'Drag & drop a video here'}
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          or click to browse
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          style={{ display: 'none' }}
          onChange={handleSelect}
        />
      </div>

      {/* Selected file info */}
      {selectedFile && (
        <div className="card" style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>📄 {selectedFile.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </div>
          </div>
          <button
            onClick={handleUpload}
            disabled={uploading || pipelineStatus.running}
            style={{
              background: uploading || pipelineStatus.running ? 'var(--border)' : 'var(--accent-blue)',
              color: '#fff',
              border: 'none',
              padding: '10px 24px',
              borderRadius: 8,
              cursor: uploading || pipelineStatus.running ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            {uploading ? 'Uploading…' : pipelineStatus.running ? 'Processing…' : '▶ Start Processing'}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid var(--accent-red)',
                      borderRadius: 8, padding: 16, color: 'var(--accent-red)', marginBottom: 16 }}>
          ❌ {error}
        </div>
      )}

      {/* Upload success */}
      {uploadResult && (
        <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid var(--accent-green)',
                      borderRadius: 8, padding: 16, color: 'var(--accent-green)', marginBottom: 16 }}>
          ✅ {uploadResult.message}
        </div>
      )}

      {/* Processing progress */}
      {(pipelineStatus.running || pipelineStatus.done) && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}>
            {pipelineStatus.running ? '⚙️ Processing…' : pipelineStatus.error ? '❌ Error' : '✅ Complete'}
          </div>

          {pipelineStatus.source && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, fontFamily: 'monospace' }}>
              Source: {pipelineStatus.source}
            </div>
          )}

          {/* Progress bar */}
          <div style={{ height: 10, background: 'var(--border)', borderRadius: 5, marginBottom: 12 }}>
            <div style={{
              height: 10,
              width: pipelineStatus.done ? '100%' : `${pct}%`,
              background: pipelineStatus.error ? 'var(--accent-red)' : 'var(--accent-blue)',
              borderRadius: 5, transition: 'width 0.5s',
            }} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--text-muted)' }}>
            <span>Frame {pipelineStatus.progress} / {pipelineStatus.total_frames || '?'}</span>
            <span>{pct}%</span>
          </div>

          {pipelineStatus.done && !pipelineStatus.error && (
            <div style={{ marginTop: 16, padding: 14, background: 'rgba(34,197,94,0.1)',
                          borderRadius: 8, border: '1px solid var(--accent-green)' }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent-green)' }}>
                👤 {pipelineStatus.unique_visitors} Unique Visitors Detected
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                Check the Dashboard, Faces, and Events tabs for full results.
              </div>
            </div>
          )}

          {pipelineStatus.error && (
            <div style={{ marginTop: 12, color: 'var(--accent-red)', fontSize: 13 }}>
              Error: {pipelineStatus.error}
            </div>
          )}
        </div>
      )}

      {/* Instructions */}
      {!pipelineStatus.running && !pipelineStatus.done && !selectedFile && (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>How it works</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.8 }}>
            <div>1️⃣ &nbsp;Select or drag a video file above</div>
            <div>2️⃣ &nbsp;Click <strong style={{ color: 'var(--text-primary)' }}>Start Processing</strong></div>
            <div>3️⃣ &nbsp;Watch the progress bar — results stream in real-time</div>
            <div>4️⃣ &nbsp;When done, view results in <strong style={{ color: 'var(--text-primary)' }}>Dashboard → Faces → Events</strong></div>
          </div>
        </div>
      )}
    </div>
  );
}