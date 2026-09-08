import { useState } from 'react';

export default function CorridorSpeedPanel({ speeds, onInspect }) {
  const [filter, setFilter] = useState('');
  const speedEntries = speeds ? Object.entries(speeds) : [];

  const filtered = speedEntries.filter(([key, item]) => {
    if (!filter) return true;
    const f = filter.toLowerCase();
    return (
      key.toLowerCase().includes(f) ||
      item.cam_a_name.toLowerCase().includes(f) ||
      item.cam_b_name.toLowerCase().includes(f)
    );
  });

  return (
    <div className="card dev-panel">
      <div className="card-header">
        <div className="card-header-left">
          <span className="dev-tag">ANALYTICS: SPEED ESTIMATOR</span>
          <span className="card-title">Average Vehicle Speeds Between Cameras</span>
        </div>
        <div className="card-header-right">
          <span className="card-badge dev-badge">
            {speedEntries.length} Travel Corridors
          </span>
          <button 
            className="btn-dev-sm" 
            onClick={() => onInspect({ title: 'GET /analytics/speeds', data: speeds })}
          >
            Raw JSON
          </button>
        </div>
      </div>

      <div className="card-body">
        <p className="student-helper-text">
          💡 <strong>How it works for students:</strong> If Camera 1 photographed a car at 10:00 AM and Camera 2 photographed it 10 km away at 10:10 AM, the speed was <code>10 km / 0.166 hr = 60 km/h</code>. Corridors exceeding 80 km/h are flagged with a speed alert!
        </p>

        <div className="dev-table-controls">
          <input
            type="text"
            className="search-input dev-input-sm"
            style={{ maxWidth: 280 }}
            placeholder="Search road (e.g. DND, Ring Road, CP)..."
            value={filter}
            onChange={e => setFilter(e.target.value)}
          />
          <span className="dev-table-metric">
            City Speed Limit Baseline: 80 km/h · Physics Feasibility Filter Active
          </span>
        </div>

        {speedEntries.length === 0 ? (
          <div className="student-empty-state">
            <div className="empty-icon-large">⚡</div>
            <div className="empty-title">No Corridors Measured Yet</div>
            <div className="empty-subtitle">Run a simulation with 200+ detections to see vehicles travel between cameras.</div>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table dev-grid">
              <thead>
                <tr>
                  <th>CORRIDOR (FROM ➔ TO)</th>
                  <th>START CAMERA</th>
                  <th>END CAMERA</th>
                  <th>DISTANCE</th>
                  <th>CARS MEASURED</th>
                  <th>AVERAGE SPEED</th>
                  <th>SAFETY STATUS</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(([key, item]) => {
                  const isHigh = item.avg_speed_kmph > 70;
                  const isSuspicious = item.avg_speed_kmph > 80;
                  return (
                    <tr key={key} className="dev-row">
                      <td className="mono bold highlight-cyan">{key}</td>
                      <td>{item.cam_a_name.split('—')[0].trim()}</td>
                      <td>{item.cam_b_name.split('—')[0].trim()}</td>
                      <td className="mono">{item.distance_km.toFixed(1)} km</td>
                      <td className="mono">{item.sample_count} cars</td>
                      <td className="mono">
                        <span className={`speed-pill ${isSuspicious ? 'speed-alert' : isHigh ? 'speed-high' : 'speed-normal'}`}>
                          {item.avg_speed_kmph} km/h
                        </span>
                      </td>
                      <td>
                        {isSuspicious ? (
                          <span className="status-badge badge-warning">⚡ Speed Warning (&gt;80 km/h)</span>
                        ) : (
                          <span className="status-badge badge-ok">✅ Normal City Speed</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
