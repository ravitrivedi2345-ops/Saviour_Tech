import { useState, useMemo } from 'react';
import { fmtTime, confClass } from '../utils';

export default function DetectionsPanel({ detections, loading, onInspect, onSelectPlate }) {
  const [filterPlate, setFilterPlate] = useState('');
  const [selectedCamera, setSelectedCamera] = useState('ALL');
  const [selectedVType, setSelectedVType] = useState('ALL');
  const [onlyNoisy, setOnlyNoisy] = useState(false);
  const [minConf, setMinConf] = useState(60);

  const cameras = useMemo(() => {
    const set = new Set(detections.map(d => d.camera_id));
    return Array.from(set).sort();
  }, [detections]);

  const vehicleTypes = useMemo(() => {
    const set = new Set(detections.map(d => d.vehicle_type));
    return Array.from(set).sort();
  }, [detections]);

  const filteredDetections = useMemo(() => {
    return detections.filter(d => {
      if (filterPlate && !d.plate_raw.toLowerCase().includes(filterPlate.toLowerCase())) return false;
      if (selectedCamera !== 'ALL' && d.camera_id !== selectedCamera) return false;
      if (selectedVType !== 'ALL' && d.vehicle_type !== selectedVType) return false;
      if (onlyNoisy && !d.ocr_noisy) return false;
      if (d.confidence * 100 < minConf) return false;
      return true;
    });
  }, [detections, filterPlate, selectedCamera, selectedVType, onlyNoisy, minConf]);

  return (
    <div className="card dev-panel">
      <div className="card-header">
        <div className="card-header-left">
          <span className="dev-tag">FEATURE 1: LIVE SENSOR FEED</span>
          <span className="card-title">Live Camera Plate Detections</span>
        </div>
        <div className="card-header-right">
          <span className="card-badge dev-badge">
            Showing {filteredDetections.length} of {detections.length} scans
          </span>
          <button 
            className="btn-dev-sm" 
            onClick={() => onInspect({ title: 'Raw Ingest Batch', data: filteredDetections.slice(0, 20) })}
          >
            Raw JSON
          </button>
        </div>
      </div>

      <div className="card-body" style={{ padding: '12px' }}>
        <p className="student-helper-text">
          💡 <strong>Student Tip:</strong> Each row is a vehicle photographed by a Delhi traffic camera. Look for rows marked with ⚡—these simulate real-world camera read errors (like <code>0 ↔ O</code> or <code>1 ↔ I</code>) that our AI handles seamlessly.
        </p>

        {/* Filter Toolbar with Simple English Labels */}
        <div className="stream-filter-toolbar">
          <input
            type="text"
            className="search-input dev-input-sm"
            style={{ maxWidth: 170 }}
            placeholder="Search plate (e.g. DL01)..."
            value={filterPlate}
            onChange={e => setFilterPlate(e.target.value)}
          />

          <select
            className="dev-select-sm"
            value={selectedCamera}
            onChange={e => setSelectedCamera(e.target.value)}
          >
            <option value="ALL">All Cameras ({cameras.length})</option>
            {cameras.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <select
            className="dev-select-sm"
            value={selectedVType}
            onChange={e => setSelectedVType(e.target.value)}
          >
            <option value="ALL">All Vehicle Types</option>
            {vehicleTypes.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>

          <label className="dev-toggle-label" title="Show only reads where our simulator injected realistic camera OCR typos">
            <input
              type="checkbox"
              checked={onlyNoisy}
              onChange={e => setOnlyNoisy(e.target.checked)}
            />
            <span>⚡ Camera Typos Only</span>
          </label>

          <div className="dev-slider-wrap">
            <span className="slider-label">Accuracy &ge; {minConf}%</span>
            <input
              type="range"
              min="60"
              max="95"
              value={minConf}
              onChange={e => setMinConf(Number(e.target.value))}
              className="dev-slider"
            />
          </div>
        </div>

        {loading ? (
          <div className="dev-loading-box">
            <span className="loading-spinner" /> Reading camera signals...
          </div>
        ) : filteredDetections.length === 0 ? (
          <div className="student-empty-state">
            <div className="empty-icon-large">🔍</div>
            <div className="empty-title">No Matching Vehicles</div>
            <div className="empty-subtitle">Try adjusting your search filters or click "Reset" to see all scans.</div>
          </div>
        ) : (
          <div className="detections-list">
            <div className="detection-row dev-table-head">
              <span style={{ width: 18 }}>ERR</span>
              <span>NUMBER PLATE</span>
              <span>LOCATION / CAMERA</span>
              <span>TYPE</span>
              <span>ACCURACY</span>
              <span>TIME</span>
              <span>ACTIONS</span>
            </div>

            {filteredDetections.map((d) => (
              <div 
                key={d.id} 
                className={`detection-row dev-detection-row ${d.ocr_noisy ? 'row-noisy' : ''}`}
                onClick={() => onInspect({ title: `Detection Telemetry: ${d.id}`, data: d })}
              >
                <span style={{ width: 18 }} title={d.ocr_noisy ? 'Deliberate OCR typo (e.g. 0/O, 1/I, 8/B swap) injected to test AI' : 'Clean read'}>
                  {d.ocr_noisy ? (
                    <span className="noisy-indicator" title="Camera typo injected">⚡</span>
                  ) : (
                    <span className="clean-dot" />
                  )}
                </span>

                <span 
                  className="detection-plate dev-plate-link"
                  title="Click to track this vehicle's route"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (onSelectPlate) onSelectPlate(d.plate_raw);
                  }}
                >
                  {d.plate_raw}
                </span>

                <span className="detection-camera" title={d.camera_name}>
                  <strong>{d.camera_name.split('—')[0].trim()}</strong> <span className="mono text-muted" style={{ fontSize: 10 }}>({d.camera_id})</span>
                </span>

                <span className="detection-vtype">
                  {d.vehicle_type}
                </span>

                <span className={`conf-badge ${confClass(d.confidence)} mono`}>
                  {(d.confidence * 100).toFixed(0)}%
                </span>

                <span className="detection-time mono text-muted">
                  {fmtTime(d.timestamp)}
                </span>

                <span className="row-actions">
                  <button
                    className="btn-dev-xs highlight-cyan-btn"
                    title="Track where this vehicle went"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onSelectPlate) onSelectPlate(d.plate_raw);
                    }}
                  >
                    Track Route ➔
                  </button>
                  <button
                    className="btn-dev-xs"
                    title="View raw JSON data"
                    onClick={(e) => {
                      e.stopPropagation();
                      onInspect({ title: `Detection Frame [${d.id}]`, data: d });
                    }}
                  >
                    Data
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
