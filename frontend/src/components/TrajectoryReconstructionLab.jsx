import { useState, useEffect, useCallback } from 'react';
import { queryTrajectory, getTrajectoryCsvUrl, getTrajectoryReportUrl } from '../api';
import { fmtDateTime, confClass } from '../utils';
import TrajectoryMap from './TrajectoryMap';

const SAMPLE_PLATES = [
  { plate: 'DL01AB1234', label: '🚗 DL01AB1234 (Delhi Central → Rohini with 45m Gap)', hint: 'Normal multi-hop route with intentional unobserved gap' },
  { plate: 'MH12XY5678', label: '⚡ MH12XY5678 (Wanted Cross-City Transit)', hint: 'Wanted vehicle with speed anomaly gap' },
  { plate: 'UP32CD9999', label: '📦 UP32CD9999 (Clean Delivery Route)', hint: 'Continuous 4-stop urban delivery without gaps' },
  { plate: 'DLO1AB1234', label: '🔍 DLO1AB1234 (OCR Character Swap)', hint: 'Tests fuzzy matching (0 replaced with letter O)' },
];

export default function TrajectoryReconstructionLab({ onInspect, defaultPlate = 'DL01AB1234' }) {
  const [plateInput, setPlateInput] = useState(defaultPlate);
  const [activePlate, setActivePlate] = useState(defaultPlate);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [minConfidence, setMinConfidence] = useState(0.0);
  const [deduplicate, setDeduplicate] = useState(true);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);

  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [selectedWaypoint, setSelectedWaypoint] = useState(null);

  // Fetch trajectory data
  const loadTrajectory = useCallback(async () => {
    if (!activePlate.trim()) return;
    setLoading(true);
    setError('');

    try {
      const res = await queryTrajectory({
        plate: activePlate.trim(),
        start: startDate,
        end: endDate,
        minConfidence: parseFloat(minConfidence),
        page,
        limit,
        deduplicate,
      });

      setData(res);
      if (res.waypoints && res.waypoints.length > 0) {
        setSelectedWaypoint(res.waypoints[0]);
      } else {
        setSelectedWaypoint(null);
      }
    } catch (err) {
      setError(err.message || 'Failed to reconstruct trajectory.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [activePlate, startDate, endDate, minConfidence, page, limit, deduplicate]);

  // Initial load
  useEffect(() => {
    loadTrajectory();
  }, [loadTrajectory]);

  function handleSearch(e) {
    if (e) e.preventDefault();
    if (!plateInput.trim()) return;
    setActivePlate(plateInput.trim().toUpperCase());
    setPage(1);
  }

  function handleSelectSample(p) {
    setPlateInput(p);
    setActivePlate(p);
    setPage(1);
  }

  function handleQuickDate(range) {
    const now = new Date();
    if (range === 'all') {
      setStartDate('');
      setEndDate('');
    } else if (range === 'today') {
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      setStartDate(todayStart.toISOString().slice(0, 16));
      setEndDate('');
    } else if (range === '24h') {
      const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      setStartDate(dayAgo.toISOString().slice(0, 16));
      setEndDate('');
    }
    setPage(1);
  }

  const csvUrl = getTrajectoryCsvUrl({
    plate: activePlate,
    start: startDate,
    end: endDate,
    minConfidence,
  });

  const reportUrl = getTrajectoryReportUrl({
    plate: activePlate,
    start: startDate,
    end: endDate,
    minConfidence,
  });

  const summary = data?.summary;
  const waypoints = data?.waypoints || [];
  const allWaypoints = data?.all_waypoints || [];
  const segments = data?.segments || [];
  const pagination = data?.pagination;

  return (
    <div className="card dev-panel trajectory-engine-card">
      {/* Panel Header */}
      <div className="card-header">
        <div className="card-header-left">
          <span className="dev-tag">COMPONENT 2: TRAJECTORY RECONSTRUCTION ENGINE</span>
          <span className="card-title">Chronological Pathing, Deduplication &amp; Coverage Gap Detection</span>
        </div>
        <div className="card-header-right">
          {data && (
            <button
              className="btn-dev-sm"
              onClick={() => onInspect({ title: `Trajectory Engine Response [${activePlate}]`, data })}
            >
              Payload JSON
            </button>
          )}
          <a
            href={csvUrl}
            target="_blank"
            rel="noreferrer"
            className="btn-dev-sm btn-action-csv"
            title="Download RFC 4180 CSV export for law enforcement analysis"
          >
            📥 Export CSV
          </a>
          <a
            href={reportUrl}
            target="_blank"
            rel="noreferrer"
            className="btn-dev-sm btn-action-report"
            title="Open printable Law Enforcement Movement Dossier"
          >
            📄 Police Report (PDF)
          </a>
        </div>
      </div>

      <div className="card-body" style={{ padding: '16px' }}>
        {/* Helper Explainer Banner */}
        <p className="student-helper-text">
          💡 <strong>Component 2 Core Architecture:</strong> This engine groups OCR reads, collapses multi-frame bursts at the same camera into single waypoints, and connects sightings chronologically. <strong>Crucial rule:</strong> Continuous tracking is <em>never</em> assumed — missing camera intervals or speed jumps appear explicitly as <strong>amber dashed coverage gaps</strong>.
        </p>

        {/* Filter Controls Form */}
        <form onSubmit={handleSearch} className="trajectory-filter-form">
          {/* Row 1: Plate Search and Sample Pills */}
          <div className="filter-row-top">
            <div className="search-input-group">
              <label className="dev-label-inline bold">Target License Plate:</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  className="dev-input mono search-box"
                  placeholder="e.g. DL01AB1234"
                  value={plateInput}
                  onChange={e => setPlateInput(e.target.value.toUpperCase())}
                />
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Reconstructing...' : '🔍 Trace Vehicle'}
                </button>
              </div>
            </div>

            <div className="sample-plates-container">
              <span className="sample-label">Quick Test Scenarios:</span>
              <div className="sample-pills">
                {SAMPLE_PLATES.map(s => (
                  <button
                    key={s.plate}
                    type="button"
                    className={`btn-demo-pill ${activePlate === s.plate ? 'highlight' : ''}`}
                    onClick={() => handleSelectSample(s.plate)}
                    title={s.hint}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Row 2: Date/Time Range & Filters */}
          <div className="filter-row-bottom">
            {/* Start & End Date Pickers */}
            <div className="date-picker-group">
              <label className="dev-label-inline">Date/Time Window:</label>
              <div className="date-inputs">
                <input
                  type="datetime-local"
                  className="dev-input"
                  value={startDate}
                  onChange={e => setStartDate(e.target.value)}
                  title="Start Date & Time"
                />
                <span className="text-muted">to</span>
                <input
                  type="datetime-local"
                  className="dev-input"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                  title="End Date & Time"
                />
              </div>
              <div className="quick-date-buttons">
                <button type="button" className="btn-dev-xs" onClick={() => handleQuickDate('all')}>All Time</button>
                <button type="button" className="btn-dev-xs" onClick={() => handleQuickDate('24h')}>Last 24h</button>
                <button type="button" className="btn-dev-xs" onClick={() => handleQuickDate('today')}>Today</button>
              </div>
            </div>

            {/* Confidence Filter Slider */}
            <div className="confidence-slider-group">
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <label className="dev-label-inline">Confidence Threshold:</label>
                <span className="mono bold" style={{ color: minConfidence > 0.85 ? '#f59e0b' : '#38bdf8' }}>
                  ≥ {(minConfidence * 100).toFixed(0)}%
                </span>
              </div>
              <input
                type="range"
                min="0.0"
                max="0.95"
                step="0.05"
                className="slider-input"
                value={minConfidence}
                onChange={e => setMinConfidence(parseFloat(e.target.value))}
              />
              <span className="slider-subtext text-muted" style={{ fontSize: 10 }}>
                {minConfidence === 0 ? 'Showing all sightings' : 'Excluding noisy/low-confidence reads'}
              </span>
            </div>

            {/* Deduplication Toggle */}
            <div className="dedup-toggle-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={deduplicate}
                  onChange={e => setDeduplicate(e.target.checked)}
                />
                <span>Collapse Multi-Frame Bursts (60s)</span>
              </label>
              <span className="text-muted" style={{ fontSize: 11, display: 'block', marginTop: 2 }}>
                {summary?.deduplicated_bursts_collapsed > 0 ? (
                  <span className="highlight-cyan">✓ {summary.deduplicated_bursts_collapsed} camera burst frames collapsed</span>
                ) : (
                  'Reduces camera spam into single stop waypoints'
                )}
              </span>
            </div>
          </div>
        </form>

        {/* Error Alert */}
        {error && (
          <div className="dev-error-box" style={{ marginTop: 12 }}>
            <strong>Query Error:</strong> {error}
          </div>
        )}

        {/* Empty State when no data found */}
        {data && !data.found && (
          <div className="student-empty-state" style={{ minHeight: 280, margin: '20px 0' }}>
            <div className="empty-icon-large">🔍</div>
            <div className="empty-title">No Vehicle Sightings Recorded</div>
            <div className="empty-subtitle">
              Plate <strong>{activePlate}</strong> had 0 camera detections matching your filter criteria.
            </div>
            <div className="empty-suggestions">
              Suggestions:
              <ul>
                <li>Clear the Date/Time window to search all historical periods.</li>
                <li>Lower the Confidence Slider if plate photos were taken in poor weather.</li>
                <li>Try testing one of our known fleet vehicles above (e.g. <code>DL01AB1234</code> or <code>MH12XY5678</code>).</li>
              </ul>
            </div>
          </div>
        )}

        {/* Content View when Trajectory Found */}
        {data && data.found && (
          <div className="trajectory-results-area" style={{ marginTop: 16 }}>
            {/* KPI Summary Strip */}
            {summary && (
              <div className="traj-kpi-grid">
                <div className="kpi-box">
                  <span className="kpi-sub">Total Distance</span>
                  <span className="kpi-num">{summary.total_distance_km} <small>km</small></span>
                </div>
                <div className="kpi-box">
                  <span className="kpi-sub">Total Transit Time</span>
                  <span className="kpi-num">{summary.total_travel_time}</span>
                </div>
                <div className="kpi-box">
                  <span className="kpi-sub">Average Speed</span>
                  <span className="kpi-num">{summary.avg_speed_kmph} <small>km/h</small></span>
                </div>
                <div className="kpi-box">
                  <span className="kpi-sub">Observed Waypoints</span>
                  <span className="kpi-num">{data.total_waypoints} <small>stops</small></span>
                </div>
                <div className={`kpi-box ${summary.gap_count > 0 ? 'kpi-warning' : 'kpi-success'}`}>
                  <span className="kpi-sub">Coverage Gaps</span>
                  <span className="kpi-num">
                    {summary.gap_count > 0 ? `⚠️ ${summary.gap_count} Gaps` : '✓ Continuous'}
                  </span>
                </div>
              </div>
            )}

            {/* Interactive Leaflet Map */}
            <div className="map-view-section">
              <div className="section-title-bar">
                <span className="section-title">🗺️ Reconstructed Delhi NCR Transit Route</span>
                <span className="text-muted" style={{ fontSize: 12 }}>
                  Solid blue lines = observed continuous route &bull; Dashed amber lines = coverage gaps (&gt;30m or blindspot)
                </span>
              </div>
              <TrajectoryMap
                waypoints={allWaypoints}
                segments={segments}
                activeWaypointId={selectedWaypoint?.id}
                onSelectWaypoint={wp => setSelectedWaypoint(wp)}
              />
            </div>

            {/* Chronological Timeline & Stop List */}
            <div className="timeline-section" style={{ marginTop: 24 }}>
              <div className="section-title-bar">
                <span className="section-title">⏱️ Chronological Waypoint Timeline ({data.total_waypoints} Stops)</span>
                <span className="text-muted" style={{ fontSize: 12 }}>
                  Click any stop below to highlight and pan the map to that camera location
                </span>
              </div>

              <div className="timeline-cards-list">
                {waypoints.map((wp, idx) => {
                  const isSelected = selectedWaypoint?.id === wp.id;
                  const isGap = wp.is_gap;

                  return (
                    <div key={wp.id || idx}>
                      {/* Explicit Gap Callout Banner if this hop represents an unobserved gap */}
                      {isGap && (
                        <div className="timeline-gap-alert-card">
                          <div className="gap-alert-left">
                            <span className="gap-icon">⚠️</span>
                            <div>
                              <strong>COVERAGE GAP / UNOBSERVED INTERVAL ({wp.formatted_delta})</strong>
                              <div className="gap-reason-text">{wp.gap_reason}</div>
                            </div>
                          </div>
                          <div className="gap-alert-right mono">
                            <span>Dist: {wp.distance_km} km</span>
                            <span>Speed: {wp.speed_kmph} km/h</span>
                          </div>
                        </div>
                      )}

                      {/* Waypoint Stop Card */}
                      <div
                        className={`timeline-stop-card ${isSelected ? 'stop-card-selected' : ''} ${isGap ? 'stop-card-gap' : ''}`}
                        onClick={() => setSelectedWaypoint(wp)}
                      >
                        <div className="stop-card-left">
                          <div className={`stop-seq-badge ${idx === 0 ? 'badge-first' : idx === waypoints.length - 1 ? 'badge-last' : ''}`}>
                            {wp.sequence}
                          </div>
                          <div className="stop-main-info">
                            <div className="stop-camera-name">
                              <strong>{wp.camera_name}</strong>
                              <span className="stop-camera-id mono text-muted">({wp.camera_id})</span>
                            </div>
                            <div className="stop-time text-muted">
                              🕒 Sighted: <strong>{fmtDateTime(wp.timestamp)}</strong>
                            </div>
                            <div className="stop-gps mono text-muted" style={{ fontSize: 11 }}>
                              📍 GPS: {wp.lat.toFixed(4)}, {wp.lon.toFixed(4)}
                            </div>
                          </div>
                        </div>

                        <div className="stop-card-right">
                          <div className="stop-metrics">
                            {wp.distance_km > 0 && (
                              <span className="stop-metric-item">
                                📏 {wp.distance_km} km ({wp.formatted_delta})
                              </span>
                            )}
                            {wp.speed_kmph > 0 && (
                              <span className="stop-metric-item mono">
                                ⚡ {wp.speed_kmph} km/h
                              </span>
                            )}
                          </div>

                          <div className="stop-badges">
                            <span className={`conf-badge ${confClass(wp.confidence)} mono`}>
                              {(wp.confidence * 100).toFixed(0)}% Conf
                            </span>
                            {wp.burst_count > 1 && (
                              <span className="burst-collapsed-badge" title="Multiple video frames combined into this stop">
                                📸 {wp.burst_count} frames
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Pagination controls if total pages > 1 */}
              {pagination && pagination.total_pages > 1 && (
                <div className="pagination-bar" style={{ marginTop: 16, display: 'flex', justifyContent: 'center', gap: 12 }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={page <= 1}
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                  >
                    ← Previous Page
                  </button>
                  <span className="pagination-info" style={{ alignSelf: 'center', fontSize: 13 }}>
                    Page <strong>{page}</strong> of <strong>{pagination.total_pages}</strong> ({pagination.total} total stops)
                  </span>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={page >= pagination.total_pages}
                    onClick={() => setPage(p => Math.min(pagination.total_pages, p + 1))}
                  >
                    Next Page →
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
