import { useState, useEffect, useCallback, useRef } from 'react';
import { queryTrajectory, getTrajectoryCsvUrl, getTrajectoryReportUrl, createLiveTrafficWebSocket } from '../api';
import { fmtDateTime, confClass } from '../utils';
import TrajectoryMap from './TrajectoryMap';

const SAMPLE_PLATES = [
  { plate: 'DL01AB1234', label: '🚗 DL01AB1234 (Delhi Central → Rohini with 45m Gap)', hint: 'Normal multi-hop route with intentional unobserved gap' },
  { plate: 'MH12XY5678', label: '⚡ MH12XY5678 (Wanted Cross-City Transit)', hint: 'Wanted vehicle with speed anomaly gap' },
  { plate: 'UP32CD9999', label: '📦 UP32CD9999 (Clean Delivery Route)', hint: 'Continuous 4-stop urban delivery without gaps' },
  { plate: 'DLO1AB1234', label: '🔍 DLO1AB1234 (OCR Character Swap)', hint: 'Tests fuzzy matching (0 replaced with letter O)' },
];

export default function TrajectoryReconstructionLab({ onInspect, defaultPlate = 'DL01AB1234', initialViewMode = 'HYBRID' }) {
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

  // ── Merged Live Traffic & Heatmap States ──
  const [viewMode, setViewMode] = useState(initialViewMode); // 'HYBRID' | 'TRAJECTORY' | 'LIVEMAP'
  const [showLiveHeatmap, setShowLiveHeatmap] = useState(true);
  const [showLiveCameras, setShowLiveCameras] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [liveCameraStats, setLiveCameraStats] = useState({});
  const [liveDetections, setLiveDetections] = useState([]);
  const [liveHeatmapData, setLiveHeatmapData] = useState([]);
  const [liveCameraNodes, setLiveCameraNodes] = useState([]);
  const socketRef = useRef(null);

  // Connect to Live Traffic WebSocket
  useEffect(() => {
    const socket = createLiveTrafficWebSocket(
      (message) => {
        if (message.type === 'SNAPSHOT') {
          setLiveCameraStats(message.camera_stats || {});
          setLiveCameraNodes(message.camera_nodes || []);
          setLiveHeatmapData(
            Object.entries(message.camera_stats || {}).map(([camId, stat]) => {
              const node = (message.camera_nodes || []).find(c => c.camera_id === camId) || {};
              return {
                camera_id: camId,
                lat: node.lat,
                lng: node.lng,
                intensity: stat.congestion_score,
                congestion_level: stat.congestion_level,
                avg_speed_kmh: stat.avg_speed_kmh,
              };
            })
          );
        }
        if (message.type === 'LIVE_DETECTION') {
          setLiveDetections((current) => [message.detection, ...current].slice(0, 15));
        }
        if (message.type === 'CONGESTION_HEATMAP_UPDATE') {
          setLiveCameraStats(message.camera_stats || {});
          setLiveHeatmapData(message.heatmap || []);
        }
      },
      () => setWsConnected(true),
      () => setWsConnected(false),
      () => setWsConnected(false),
    );

    socketRef.current = socket;
    return () => socket.close();
  }, []);

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

  function handleSelectLivePlate(plate) {
    if (!plate) return;
    setPlateInput(plate);
    setActivePlate(plate);
    setPage(1);
    setViewMode('HYBRID');
  }

  const csvUrl = getTrajectoryCsvUrl({
    plate: activePlate,
    start: startDate,
    end: endDate,
    minConfidence,
  });

  const stats = Object.values(liveCameraStats);
  const avgCongestion = stats.length 
    ? stats.reduce((sum, stat) => sum + (stat.congestion_score || 0), 0) / stats.length 
    : 0.35;

  return (
    <div className="card dev-panel">
      {/* ── Header ── */}
      <div className="card-header">
        <div className="card-header-left">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="dev-tag">COMMAND CENTER (COMPONENTS 2 + EXTENSION 2 + 4)</span>
            <span className="badge-grant full" style={{ fontSize: 10 }}>UNIFIED TRAFFIC &amp; TRAJECTORY</span>
          </div>
          <span className="card-title">
            Vehicle Journey Reconstruction, OSRM Road Snapping &amp; Live Delhi Heatmap
          </span>
        </div>

        <div className="card-header-right">
          <span className={`connection-pill ${wsConnected ? 'online' : ''}`} style={{ fontSize: 11 }}>
            <span className="pulse-dot" /> {wsConnected ? 'LIVE FEED ACTIVE' : 'CONNECTING...'}
          </span>
          {data && (
            <button
              className="btn-dev-sm"
              onClick={() => onInspect({ title: `Trajectory Data for ${activePlate}`, data })}
            >
              Payload JSON
            </button>
          )}
        </div>
      </div>

      <div className="card-body" style={{ padding: '16px' }}>
        {/* ── Top View Mode Pills ── */}
        <div className="ocr-mode-switcher-bar" style={{ marginBottom: 12 }}>
          <button
            type="button"
            className={`ocr-mode-btn ${viewMode === 'HYBRID' ? 'active' : ''}`}
            onClick={() => setViewMode('HYBRID')}
          >
            🔀 1. Hybrid Command Center (Trajectory + Live Congestion Heatmap)
          </button>
          <button
            type="button"
            className={`ocr-mode-btn ${viewMode === 'TRAJECTORY' ? 'active' : ''}`}
            onClick={() => setViewMode('TRAJECTORY')}
          >
            🛣️ 2. Trajectory Journey Reconstruction Only
          </button>
          <button
            type="button"
            className={`ocr-mode-btn ${viewMode === 'LIVEMAP' ? 'active' : ''}`}
            onClick={() => setViewMode('LIVEMAP')}
          >
            🌐 3. Delhi NCR Live Traffic Feed &amp; Heatmap
          </button>
        </div>

        {/* ── Live Stream KPI Ribbon ── */}
        {(viewMode === 'HYBRID' || viewMode === 'LIVEMAP') && (
          <div className="live-traffic-kpis" style={{ marginBottom: 14 }}>
            <div><span>DELHI NODES</span><strong>{liveCameraNodes.length || 14} Cameras</strong></div>
            <div><span>CITY CONGESTION INDEX</span><strong style={{ color: avgCongestion > 0.6 ? '#ef4444' : '#00f0ff' }}>{Math.round(avgCongestion * 100)}%</strong></div>
            <div><span>LIVE STREAM EVENTS</span><strong>{liveDetections.length} Recent</strong></div>
            <div><span>OSRM ROAD SNAPPING</span><strong className="text-green">Active (Delhi NCR)</strong></div>
          </div>
        )}

        {/* ── Search Bar & Filter Controls (for Trajectory & Hybrid) ── */}
        {(viewMode === 'HYBRID' || viewMode === 'TRAJECTORY') && (
          <div className="trajectory-search-box">
            <form onSubmit={handleSearch} className="trajectory-form">
              <div className="search-input-wrap">
                <label className="dev-label-inline bold">TARGET LICENSE PLATE:</label>
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                  <input
                    type="text"
                    className="dev-input mono search-plate-input"
                    placeholder="e.g. DL01AB1234"
                    value={plateInput}
                    onChange={e => setPlateInput(e.target.value.toUpperCase())}
                  />
                  <button type="submit" className="btn btn-primary" disabled={loading}>
                    {loading ? 'Reconstructing...' : '🔍 Search Trajectory'}
                  </button>
                </div>
              </div>

              {/* Sample Plates Quick Select */}
              <div className="sample-plates-row">
                <span className="dev-label-inline" style={{ fontSize: 11 }}>Quick Presets:</span>
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
            </form>
          </div>
        )}

        {/* ── Layer Toggles Bar ── */}
        <div className="map-layer-toggles-bar">
          <div className="toggles-left">
            <label className="toggle-checkbox-label">
              <input 
                type="checkbox" 
                checked={showLiveHeatmap} 
                onChange={e => setShowLiveHeatmap(e.target.checked)} 
              />
              <span>🔥 Live Congestion Heatmap</span>
            </label>
            <label className="toggle-checkbox-label">
              <input 
                type="checkbox" 
                checked={showLiveCameras} 
                onChange={e => setShowLiveCameras(e.target.checked)} 
              />
              <span>📡 Delhi Camera Stations</span>
            </label>
          </div>

          <div className="toggles-right">
            {data && data.waypoints && (
              <span className="text-secondary" style={{ fontSize: 12 }}>
                Found <strong>{data.total_sightings || data.waypoints.length}</strong> sightings &bull; <strong>{data.trip_count || 1}</strong> trips reconstructed
              </span>
            )}
            {csvUrl && (
              <a href={csvUrl} download className="btn-dev-xs">
                Export Trajectory CSV
              </a>
            )}
          </div>
        </div>

        {/* ── Main Map & Live Feeds Workspace ── */}
        <div className="trajectory-merged-layout">
          {/* Main Leaflet Map */}
          <div className="merged-map-column">
            <TrajectoryMap
              waypoints={data?.waypoints || []}
              segments={data?.road_geometry || data?.segments || []}
              activeWaypointId={selectedWaypoint?.id}
              onSelectWaypoint={setSelectedWaypoint}
              showLiveHeatmap={showLiveHeatmap}
              heatmapData={liveHeatmapData}
              showLiveCameras={showLiveCameras}
              cameraNodes={liveCameraNodes}
              onSelectPlate={handleSelectLivePlate}
            />
          </div>

          {/* Side Panel: Live Detection Stream & Waypoints Timeline */}
          <div className="merged-sidebar-column">
            {/* Live Incoming Detection Stream Box */}
            <div className="live-detection-feed-box">
              <div className="feed-title">
                <span>🔴 REAL-TIME DETECTIONS FEED</span>
                <span className="mono pulse-dot-inline">LIVE</span>
              </div>
              <div className="live-feed-scroll">
                {liveDetections.length === 0 && (
                  <p className="empty-feed">Streaming Delhi NCR camera feeds...</p>
                )}
                {liveDetections.map((det, idx) => (
                  <div 
                    className="live-stream-card" 
                    key={`${det.camera_id}-${det.plate_number}-${idx}`}
                    onClick={() => handleSelectLivePlate(det.plate_number)}
                    title="Click to reconstruct this vehicle's trajectory"
                  >
                    <div className="stream-card-left">
                      <strong className="mono plate-pill">{det.plate_number}</strong>
                      <span className="stream-cam-name">{det.camera_id} · {det.corridor || 'Corridor'}</span>
                    </div>
                    <div className="stream-card-right">
                      <span className="mono stream-speed">{Math.round(det.speed_kmph || det.speed_kmh || 52)} km/h</span>
                      <span className="stream-track-link">Track →</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Trajectory Timeline Sightings */}
            {data && data.waypoints && data.waypoints.length > 0 && (
              <div className="timeline-sightings-box">
                <div className="feed-title">
                  <span>🛣️ JOURNEY SIGHTINGS TIMELINE</span>
                  <span className="mono text-muted">{data.waypoints.length} Stops</span>
                </div>
                <div className="timeline-scroll">
                  {data.waypoints.map((wp, idx) => {
                    const isSelected = selectedWaypoint?.id === wp.id;
                    return (
                      <div
                        key={wp.id || idx}
                        className={`timeline-item-card ${isSelected ? 'selected' : ''} ${wp.is_gap ? 'gap-item' : ''}`}
                        onClick={() => setSelectedWaypoint(wp)}
                      >
                        <div className="timeline-item-top">
                          <span className="timeline-seq-badge">#{wp.sequence || idx + 1}</span>
                          <span className="timeline-node-name bold">{wp.camera_name}</span>
                        </div>
                        <div className="timeline-item-meta mono text-muted">
                          {fmtDateTime(wp.timestamp)}
                        </div>
                        {wp.distance_km > 0 && (
                          <div className="timeline-hop-info">
                            <span>📏 {wp.distance_km} km</span>
                            <span>⚡ {wp.speed_kmph} km/h</span>
                          </div>
                        )}
                        {wp.is_gap && (
                          <div className="timeline-gap-warning">
                            ⚠️ {wp.gap_reason || 'Coverage Gap'}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
