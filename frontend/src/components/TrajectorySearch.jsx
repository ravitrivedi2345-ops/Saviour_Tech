import { useState, useEffect } from 'react';
import { getTrajectory } from '../api';
import { fmtDateTime, confClass } from '../utils';

function TrajectoryScoreBar({ score }) {
  const pct = Math.round(score * 100);
  const color = pct >= 75 ? 'var(--accent-emerald)' : pct >= 50 ? 'var(--accent-amber)' : 'var(--accent-red)';
  const quality = pct >= 75 ? 'High Confidence (Clean Path)' : pct >= 50 ? 'Moderate (Some OCR Noise)' : 'Low (High Uncertainty)';

  return (
    <div className="traj-overall-score">
      <div className="traj-score-left">
        <span className="traj-score-label">AI Trajectory Confidence Score</span>
        <span className="traj-score-desc">{quality} — combines camera confidence & time gaps</span>
      </div>
      <div className="traj-score-bar-wrap">
        <div className="traj-score-bar">
          <div
            className="traj-score-fill"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
        <span className="traj-score-value mono" style={{ color }}>{pct}%</span>
      </div>
    </div>
  );
}

function TrajStop({ det, isFirst, isLast, onInspect }) {
  return (
    <div className="traj-stop dev-traj-stop">
      <div className={`traj-dot ${isFirst ? 'first-stop' : ''} ${isLast ? 'last-stop' : ''}`} />
      <div className="traj-stop-info">
        <div className="traj-stop-header">
          <div className="traj-stop-camera">
            <span className="bold highlight-cyan" style={{ fontSize: 13 }}>{det.camera_name}</span>
            <span className="camera-fullname mono text-muted" style={{ fontSize: 11, marginLeft: 6 }}>({det.camera_id})</span>
          </div>
          <button 
            className="btn-dev-xs"
            onClick={() => onInspect({ title: `Detection Stop [${det.id}]`, data: det })}
            title="Inspect raw data"
          >
            Inspect JSON
          </button>
        </div>

        <div className="traj-stop-time text-muted" style={{ fontSize: 12 }}>
          🕒 Sighted at: <strong>{fmtDateTime(det.timestamp)}</strong>
        </div>

        <div className="traj-stop-conf">
          <span className="dev-mini-tag">Vehicle: {det.vehicle_type}</span>
          <span className={`conf-badge ${confClass(det.confidence)} mono`}>
            Camera Accuracy: {(det.confidence * 100).toFixed(0)}%
          </span>
          {det.ocr_noisy && (
            <span className="ocr-noise-flag" title="Simulated camera read error that our AI resolved">
              ⚡ OCR Typo Injected (Fixed by AI)
            </span>
          )}
          <span className="mono text-muted" style={{ fontSize: 11 }}>
            Camera read: "{det.plate_raw}"
          </span>
        </div>
      </div>
    </div>
  );
}

function TrajGap({ gap, onInspect }) {
  const minutes = Math.round(gap.gap_seconds / 60);
  return (
    <div className="traj-gap dev-traj-gap">
      <div className="gap-indicator-icon">⚠️</div>
      <div className="gap-content">
        <div className="gap-title-row">
          <span className="traj-gap-text" style={{ fontSize: 12, fontWeight: 700 }}>
            DISCONTINUITY DETECTED (Time Gap: {minutes} minutes)
          </span>
          <button 
            className="btn-dev-xs"
            onClick={() => onInspect({ title: 'Discontinuity Gap Metadata', data: gap })}
          >
            Gap Details
          </button>
        </div>
        <div className="traj-gap-reason" style={{ fontSize: 12, margin: '4px 0' }}>
          <strong>Why the AI split this trip:</strong> {gap.reason}
        </div>
        <div className="gap-physics-note">
          💡 <strong>Student Note:</strong> In the real world, vehicles cannot travel faster than 80 km/h across town. If the same plate appears too quickly at two distant cameras, it usually means <em>two different cars with cloned plates</em> or a false read. Our AI safely splits them instead of drawing an impossible route!
        </div>
      </div>
    </div>
  );
}

export default function TrajectorySearch({ selectedPlate, onInspect, onOpenEnforcement }) {
  const [query, setQuery] = useState(selectedPlate || '');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (selectedPlate) {
      setQuery(selectedPlate);
      executeSearch(selectedPlate);
    }
  }, [selectedPlate]);

  async function executeSearch(plateToSearch) {
    if (!plateToSearch || !plateToSearch.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await getTrajectory(plateToSearch.trim());
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleSearch(e) {
    e.preventDefault();
    executeSearch(query);
  }

  const QUICK_PLATES = [
    { label: 'DL01AB1234 (Wanted Car)', plate: 'DL01AB1234' },
    { label: 'DLO1A81234 (Typo / Noise)', plate: 'DLO1A81234' },
    { label: 'MH12XY5678 (Truck)', plate: 'MH12XY5678' },
    { label: 'UP32CD9999 (SUV)', plate: 'UP32CD9999' },
    { label: 'KA05EF2222 (Auto)', plate: 'KA05EF2222' },
  ];

  return (
    <div className="card dev-panel">
      <div className="card-header">
        <div className="card-header-left">
          <span className="dev-tag">FEATURE 2: SMART VEHICLE PATH TRACKER</span>
          <span className="card-title">Where Did This Vehicle Travel?</span>
        </div>
        <div className="card-header-right">
          {result && (
            <button 
              className="btn-dev-sm" 
              onClick={() => onInspect({ title: `Trajectory Object [${result.canonical_plate}]`, data: result })}
            >
              View JSON Data
            </button>
          )}
        </div>
      </div>

      <div className="card-body">
        <p className="student-helper-text">
          Enter any number plate to reconstruct its journey through the 9 Delhi cameras. Even if you type a plate with OCR typos (like <code>O</code> for <code>0</code>), the AI will find it!
        </p>

        <form className="search-form dev-search-form" onSubmit={handleSearch}>
          <input
            className="search-input dev-input mono"
            type="text"
            placeholder="Type plate e.g. DL01AB1234 or typo DLO1A81234..."
            value={query}
            onChange={e => setQuery(e.target.value.toUpperCase())}
          />
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? <span className="loading-spinner" /> : '🔍 Reconstruct Journey'}
          </button>
          {result && (
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => { setResult(null); setQuery(''); setError(''); }}
            >
              Clear
            </button>
          )}
        </form>

        {/* Quick query buttons */}
        <div className="quick-plates-bar">
          <span className="quick-label">Try Example Vehicles:</span>
          {QUICK_PLATES.map(p => (
            <button
              key={p.plate}
              type="button"
              className="btn-dev-xs quick-plate-btn"
              onClick={() => { setQuery(p.plate); executeSearch(p.plate); }}
            >
              {p.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="dev-error-box">
            <span className="error-title">No Journey Found:</span> {error}
            <div style={{ marginTop: 4, fontSize: 11, color: '#fecaca' }}>
              💡 Tip: Click "Run Simulation" at the top to generate a fresh batch of 200 vehicle detections first.
            </div>
          </div>
        )}

        {!result && !error && (
          <div className="student-empty-state">
            <div className="empty-icon-large">🗺️</div>
            <div className="empty-title">Ready to Track a Vehicle</div>
            <div className="empty-subtitle">
              Type a plate number above or click on one of the example vehicles to see its complete camera-by-camera timeline.
            </div>
          </div>
        )}

        {result && (
          <div className="trajectory-result-container">
            {/* Meta strip */}
            <div className="trajectory-meta dev-meta-grid">
              <div className="meta-box">
                <span className="meta-label">IDENTIFIED PLATE</span>
                <span className="meta-val mono highlight-cyan bold">{result.canonical_plate}</span>
              </div>
              <div className="meta-box">
                <span className="meta-label">VEHICLE TYPE</span>
                <span className="meta-val bold">{result.vehicle_type}</span>
              </div>
              <div className="meta-box">
                <span className="meta-label">TOTAL SIGHTINGS</span>
                <span className="meta-val mono">{result.total_detections} camera stops</span>
              </div>
              <div className="meta-box">
                <span className="meta-label">VALID PATHS</span>
                <span className="meta-val mono">{result.total_segments} trips</span>
              </div>
              <div className="meta-box">
                <span className="meta-label">POLICE LOOKUP</span>
                <button
                  type="button"
                  className="btn-dev-xs btn-enforcement-action"
                  onClick={() => onOpenEnforcement(result.representative_plate)}
                >
                  🔒 Owner Info
                </button>
              </div>
            </div>

            <TrajectoryScoreBar score={result.overall_confidence} />

            <div className="trajectory-stepper">
              {result.segments.map((seg, si) => {
                if (seg.type === 'gap') {
                  return <TrajGap key={`gap-${si}`} gap={seg} onInspect={onInspect} />;
                }
                return (
                  <div key={`seg-${si}`} className="traj-segment-block">
                    {result.total_segments > 1 && (
                      <div className="traj-segment-header">
                        <span>Trip Segment #{result.segments.filter((s, idx) => s.type === 'segment' && idx <= si).length}</span>
                        <span className="segment-conf-badge">Quality: {Math.round(seg.score * 100)}% ({seg.hop_count} camera hits)</span>
                      </div>
                    )}
                    {seg.detections.map((det, di) => (
                      <TrajStop
                        key={det.id}
                        det={det}
                        isFirst={si === 0 && di === 0}
                        isLast={
                          si === result.segments.length - 1 &&
                          di === seg.detections.length - 1
                        }
                        onInspect={onInspect}
                      />
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
