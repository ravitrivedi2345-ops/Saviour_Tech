import { useEffect, useRef, useState } from 'react';
import { createVideoProcessWebSocket, uploadVideo } from '../api';
import { useAuth } from '../context/AuthContext';

const ACCEPTED_TYPES = '.mp4,.avi,.mov,.mkv,.webm';

export default function VideoUploadLab({ onOpenAuth }) {
  const { user, isAuthenticated, canAccessVideo, login } = useAuth();
  const [file, setFile] = useState(null);
  const [cameraId, setCameraId] = useState('CAM-01');
  const [task, setTask] = useState(null);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const socketRef = useRef(null);

  useEffect(() => () => socketRef.current?.close(), []);

  function chooseFile(nextFile) {
    setError('');
    if (!nextFile) return;
    if (!ACCEPTED_TYPES.split(',').some((ext) => nextFile.name.toLowerCase().endsWith(ext))) {
      setError('Unsupported video format. Please choose an MP4, AVI, MOV, MKV, or WEBM video.');
      return;
    }
    setFile(nextFile);
    setTask(null);
  }

  async function handleQuickPoliceLogin() {
    try {
      await login('police_sharma', 'Police@123');
    } catch (err) {
      setError(err.message || 'Login failed');
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) return setError('Please select or drop a video file before starting analysis.');
    setError('');
    setUploading(true);
    try {
      const result = await uploadVideo(file, cameraId);
      setTask(result);
      socketRef.current?.close();
      socketRef.current = createVideoProcessWebSocket(result.task_id, (message) => {
        if (message.task) setTask(message.task);
        if (message.type === 'PROGRESS_UPDATE') {
          setTask((current) => current ? { 
            ...current, 
            ...message, 
            detections: [...(current.detections || []), ...(message.new_detections || [])] 
          } : current);
        }
      });
    } catch (err) {
      setError(err.message || 'Video upload failed. Remember minimum duration is 10.0 seconds.');
    } finally {
      setUploading(false);
    }
  }

  const progress = task?.progress_pct || 0;
  const detections = task?.detections || [];

  return (
    <section className="video-upload-lab">
      {/* ── Heading ── */}
      <div className="extension-heading">
        <div>
          <div className="extension-badge-wrap">
            <span className="eyebrow">SYSTEM EXTENSION #3</span>
            <span className="badge-new-ext">ML FRAME PIPELINE</span>
          </div>
          <h2>Video Upload &amp; Live OCR Stream Analysis</h2>
          <p className="extension-subtext">
            Upload traffic CCTV video footage (minimum 10.0s duration validation) to execute frame-by-frame license plate recognition with live streaming telemetry.
          </p>
        </div>
        <div className="lab-header-status">
          <span className="lab-note">⚡ Asynchronous processing with live progress feedback</span>
        </div>
      </div>

      {/* ── Access Role Banner if unauthenticated or non-police ── */}
      {!canAccessVideo && (
        <div className="auth-feature-callout-banner">
          <div className="callout-icon">👮‍♂️</div>
          <div className="callout-text">
            <strong>Enforcement Lab Authorization:</strong> Video OCR processing requires Traffic Police or Admin credentials.
          </div>
          <button 
            type="button" 
            className="btn-demo-pill highlight"
            onClick={handleQuickPoliceLogin}
          >
            ⚡ 1-Click Login as Police (police_sharma)
          </button>
        </div>
      )}

      {/* ── Upload Form ── */}
      <form onSubmit={submit} className="video-upload-form">
        <label className="video-dropzone">
          <input 
            type="file" 
            accept={ACCEPTED_TYPES} 
            onChange={(event) => chooseFile(event.target.files?.[0])} 
          />
          <span className="dropzone-mark">📹</span>
          <strong className="dropzone-title">
            {file ? `Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)` : 'Drop CCTV video here or click to browse'}
          </strong>
          <span className="dropzone-req">
            Format: MP4, AVI, MOV, MKV · <strong>Minimum Duration: 10.0 Seconds</strong>
          </span>
        </label>

        <div className="video-controls">
          <label>
            SELECT CAMERA NODE
            <select value={cameraId} onChange={(event) => setCameraId(event.target.value)}>
              <option value="CAM-01">CAM-01 (AIIMS Flyover - Ring Road)</option>
              <option value="CAM-02">CAM-02 (Lajpat Nagar Central)</option>
              <option value="CAM-03">CAM-03 (Ashram Chowk Junction)</option>
              <option value="CAM-04">CAM-04 (Dhaula Kuan - NH-48)</option>
              <option value="CAM-05">CAM-05 (Mahipalpur Bypass)</option>
            </select>
          </label>

          <button 
            type="submit" 
            className="btn btn-primary video-submit-btn" 
            disabled={uploading || !file}
          >
            {uploading ? (
              <>
                <span className="auth-spinner" />
                <span>Validating &amp; Uploading...</span>
              </>
            ) : (
              <span>🚀 Start Video ANPR Analysis</span>
            )}
          </button>
        </div>
      </form>

      {/* ── Error Callout ── */}
      {error && (
        <div className="extension-error" role="alert">
          <span style={{ fontSize: 16 }}>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* ── Live Task Progress & Detection Telemetry ── */}
      {task && (
        <div className="video-task-panel">
          <div className="task-status-row">
            <div className="task-id-badge">
              <span>TASK ID:</span>
              <strong className="mono">{task.task_id}</strong>
            </div>
            <div className={`task-badge status-${(task.status || '').toLowerCase()}`}>
              {task.status}
            </div>
          </div>

          <div className="progress-track">
            <span style={{ width: `${progress}%` }} />
          </div>

          <div className="task-meta">
            <span><strong>{Math.round(progress)}%</strong> Complete</span>
            <span>⏱️ <strong>{task.current_video_time_formatted || '00:00.00'}</strong> / {task.duration_seconds || '10.0'}s</span>
            <span>🚗 <strong>{task.detections_count || detections.length}</strong> Plates Detected</span>
            <span>⚡ <strong>{task.processing_fps || 0}</strong> Frames/sec</span>
          </div>

          {detections.length > 0 && (
            <div className="video-results">
              <div className="feed-title">
                <span>DETECTED NUMBER PLATE</span>
                <span>TIMESTAMP IN VIDEO</span>
                <span>OCR CONFIDENCE</span>
              </div>
              <div className="video-results-list">
                {detections.slice(-10).reverse().map((detection, index) => (
                  <div className="video-result-row" key={`${detection.frame_number}-${index}`}>
                    <div className="video-plate-wrap">
                      {detection.thumbnail_base64 && (
                        <img 
                          src={detection.thumbnail_base64} 
                          alt="Plate Crop" 
                          className="video-thumb-crop"
                        />
                      )}
                      <span className="mono plate-text bold">{detection.plate}</span>
                    </div>
                    <span className="mono text-muted">{detection.timestamp_formatted || `Frame #${detection.frame_number}`}</span>
                    <span className="conf-badge mono">{Math.round((detection.confidence || 0.9) * 100)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
