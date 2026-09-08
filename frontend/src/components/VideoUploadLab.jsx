import { useEffect, useRef, useState } from 'react';
import { createVideoProcessWebSocket, uploadVideo } from '../api';

const ACCEPTED_TYPES = '.mp4,.avi,.mov,.mkv,.webm';

export default function VideoUploadLab() {
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
    if (!ACCEPTED_TYPES.split(',').some((extension) => nextFile.name.toLowerCase().endsWith(extension))) {
      setError('Choose an MP4, AVI, MOV, MKV, or WEBM video.');
      return;
    }
    setFile(nextFile);
    setTask(null);
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) return setError('Select a video before starting analysis.');
    setError('');
    setUploading(true);
    try {
      const result = await uploadVideo(file, cameraId);
      setTask(result);
      socketRef.current?.close();
      socketRef.current = createVideoProcessWebSocket(result.task_id, (message) => {
        if (message.task) setTask(message.task);
        if (message.type === 'PROGRESS_UPDATE') {
          setTask((current) => current ? { ...current, ...message, detections: [...(current.detections || []), ...(message.new_detections || [])] } : current);
        }
      });
    } catch (err) {
      setError(err.message || 'Video upload failed.');
    } finally {
      setUploading(false);
    }
  }

  const progress = task?.progress_pct || 0;
  const detections = task?.detections || [];

  return (
    <section className="video-upload-lab">
      <div className="extension-heading">
        <div><span className="eyebrow">ANPR LAB</span><h2>Process a traffic video</h2></div>
        <span className="lab-note">Asynchronous processing with live progress feedback</span>
      </div>
      <form onSubmit={submit} className="video-upload-form">
        <label className="video-dropzone">
          <input type="file" accept={ACCEPTED_TYPES} onChange={(event) => chooseFile(event.target.files?.[0])} />
          <span className="dropzone-mark">+</span>
          <strong>{file ? file.name : 'Drop a video here or browse'}</strong>
          <span>Minimum duration: 10 seconds</span>
        </label>
        <div className="video-controls">
          <label>Camera node<select value={cameraId} onChange={(event) => setCameraId(event.target.value)}><option>CAM-01</option><option>CAM-02</option><option>CAM-03</option><option>CAM-04</option></select></label>
          <button className="btn btn-primary" disabled={uploading || !file}>{uploading ? 'Uploading...' : 'Start ANPR analysis'}</button>
        </div>
      </form>
      {error && <div className="extension-error">{error}</div>}
      {task && (
        <div className="video-task-panel">
          <div className="task-status-row"><span className="mono">{task.task_id}</span><strong>{task.status}</strong></div>
          <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
          <div className="task-meta"><span>{Math.round(progress)}% complete</span><span>{task.current_video_time_formatted || '00:00.00'} / {task.duration_seconds}s</span><span>{task.detections_count || detections.length} detections</span></div>
          {detections.length > 0 && <div className="video-results"><div className="feed-title"><span>DETECTED PLATES</span><span>CONFIDENCE</span></div>{detections.slice(-8).reverse().map((detection, index) => <div className="video-result-row" key={`${detection.frame_number}-${index}`}><span className="mono">{detection.plate}</span><span>{detection.timestamp_formatted}</span><span>{Math.round(detection.confidence * 100)}%</span></div>)}</div>}
        </div>
      )}
    </section>
  );
}
