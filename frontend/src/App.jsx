import { useState, useCallback, useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { 
  simulate, 
  getDetections, 
  getCongestion, 
  getSpeeds, 
  getAlerts, 
  getSummary, 
  getCameras 
} from './api';

import StudentGuideBanner from './components/StudentGuideBanner';
import DetectionsPanel from './components/DetectionsPanel';
import TrajectorySearch from './components/TrajectorySearch';
import TrajectoryReconstructionLab from './components/TrajectoryReconstructionLab';
import CongestionTable from './components/CongestionTable';
import AlertSystemDashboard from './components/AlertSystemDashboard';
import CorridorSpeedPanel from './components/CorridorSpeedPanel';
import CameraTopologyPanel from './components/CameraTopologyPanel';
import EnforcementVaultModal from './components/EnforcementVaultModal';
import JsonModal from './components/JsonModal';
import ApiConsoleDrawer from './components/ApiConsoleDrawer';
import OcrLiveLab from './components/OcrLiveLab';
import CityTrafficDashboard from './components/CityTrafficDashboard';
import AuthModal from './components/AuthModal';
import LiveTrafficMapDashboard from './components/LiveTrafficMapDashboard';
import VideoUploadLab from './components/VideoUploadLab';

const COUNT_OPTIONS = [100, 200, 500, 1000];

function AppContent() {
  const { user, isAuthenticated, canAccessVault, canAccessVideo, setShowLoginModal, showLoginModal, logout } = useAuth();
  const [simCount, setSimCount] = useState(200);
  const [loading, setLoading] = useState(false);
  const [simulated, setSimulated] = useState(false);
  const [activeTab, setActiveTab] = useState('TRACKER'); // 'TRACKER' | 'TRAFFIC' | 'MAP' | 'ALERTS' | 'OCR' | 'LIVE' | 'VIDEO'

  // Data states
  const [detections, setDetections] = useState([]);
  const [congestion, setCongestion] = useState(null);
  const [speeds, setSpeeds]         = useState(null);
  const [alerts, setAlerts]         = useState(null);
  const [summary, setSummary]       = useState(null);
  const [cameras, setCameras]       = useState(null);
  const [lastRun, setLastRun]       = useState(null);

  // Interaction states
  const [selectedPlate, setSelectedPlate] = useState('');
  const [inspectData, setInspectData]     = useState(null);
  const [enforcementPlate, setEnforcementPlate] = useState(null);

  // Initial load: Fetch camera network definition
  useEffect(() => {
    getCameras()
      .then(res => setCameras(res.cameras))
      .catch(err => console.warn('Backend not ready on start:', err.message));
  }, []);

  const runSimulation = useCallback(async (countToSimulate) => {
    const count = typeof countToSimulate === 'number' ? countToSimulate : simCount;
    setLoading(true);
    try {
      await simulate(count);
      const [dets, cong, spds, alts, summ, cams] = await Promise.all([
        getDetections(150),
        getCongestion(),
        getSpeeds(),
        getAlerts(),
        getSummary(),
        getCameras(),
      ]);
      setDetections(dets.detections);
      setCongestion(cong.congestion);
      setSpeeds(spds.speeds);
      setAlerts(alts.alerts);
      setSummary(summ);
      setCameras(cams.cameras);
      setSimulated(true);
      setLastRun(new Date().toLocaleTimeString('en-IN', { hour12: false }));
    } catch (err) {
      console.error(err);
      alert(`Simulation failed: ${err.message}\n\nMake sure the FastAPI backend is running on port 8000.`);
    } finally {
      setLoading(false);
    }
  }, [simCount]);

  const handleOpenEnforcement = (plate) => {
    if (!isAuthenticated) {
      setShowLoginModal(true);
      return;
    }
    if (!canAccessVault) return;
    setEnforcementPlate(plate || 'DL01AB1234');
  };

  const handleTryDemo = (plate) => {
    setActiveTab('TRACKER');
    setSelectedPlate(plate);
    if (!simulated) {
      runSimulation(200);
    }
  };

  return (
    <div className="dev-app">
      {/* ── Top Header ── */}
      <header className="dev-header">
        <div className="header-brand-wrap">
          <div className="system-status-indicator">
            <span className="pulse-dot" />
            <span className="status-label">AI ENGINE ONLINE</span>
          </div>
          <div className="header-divider" />
          <div className="header-titles">
            <div className="header-main-title">
              City-Wide ANPR Trajectory Tracking & Urban Traffic Analytics
            </div>
            <div className="header-sub-meta">
              Delhi NCR Multi-Camera AI · Fuzzy Plate Matching · Speed Physics Checks · Isolated Police Vault
            </div>
          </div>
        </div>

        {/* Global Controls & Police View Button */}
        <div className="header-right-controls">
          {isAuthenticated ? <button className="session-chip" onClick={logout} title="Sign out">
            <span className="pulse-dot" /> {user.username} · {user.role} · Sign out
          </button> : <button className="btn-dev-enforcement" onClick={() => setShowLoginModal(true)}>Sign in</button>}
          <button
            className="btn-dev-enforcement"
            onClick={() => handleOpenEnforcement('DL01AB1234')}
            disabled={!canAccessVault}
            title="Demonstrates the secure privacy vault for vehicle owner records"
          >
            🔒 Police View (Private Info)
          </button>
        </div>
      </header>

      {/* ── Student & Evaluator Quick Guide Banner ── */}
      <StudentGuideBanner onTryDemo={handleTryDemo} />

      {/* ── Control Bar ── */}
      <div className="dev-command-bar">
        <div className="command-bar-left">
          <span className="command-tag">Simulate City Traffic:</span>
          <label className="dev-label-inline">Number of Scans:</label>
          <select
            value={simCount}
            onChange={e => setSimCount(Number(e.target.value))}
            className="dev-select-sm"
          >
            {COUNT_OPTIONS.map(n => (
              <option key={n} value={n}>{n} Scans</option>
            ))}
          </select>
          <button
            className="btn btn-primary dev-action-btn"
            onClick={() => runSimulation(simCount)}
            disabled={loading}
          >
            {loading ? (
              <><span className="loading-spinner" /> Generating Traffic Scans...</>
            ) : (
              <>⚡ {simulated ? 'Re-Run Traffic Simulation' : 'Run Traffic Simulation'}</>
            )}
          </button>
        </div>

        <div className="command-bar-right">
          {simulated && lastRun && (
            <span className="text-muted" style={{ fontSize: 12 }}>Last updated: {lastRun}</span>
          )}
          {summary && (
            <button
              className="btn-dev-xs"
              onClick={() => setInspectData({ title: 'Complete System State', data: summary })}
            >
              Export JSON
            </button>
          )}
        </div>
      </div>

      {/* ── Telemetry Summary Strip (Plain English) ── */}
      {summary && summary.total > 0 && (
        <div className="dev-telemetry-ribbon">
          <div className="telemetry-cell">
            <span className="telemetry-label">TOTAL CAMERA SCANS</span>
            <span className="telemetry-val highlight-cyan mono">{summary.total}</span>
            <span className="telemetry-sub">Photographs taken</span>
          </div>
          <div className="telemetry-cell">
            <span className="telemetry-label">UNIQUE VEHICLES</span>
            <span className="telemetry-val mono">{summary.unique_plates}</span>
            <span className="telemetry-sub">Distinct cars tracked</span>
          </div>
          <div className="telemetry-cell">
            <span className="telemetry-label">ACTIVE CAMERAS</span>
            <span className="telemetry-val text-green mono">{summary.cameras_active} / 9</span>
            <span className="telemetry-sub">Delhi NCR nodes</span>
          </div>
          <div className="telemetry-cell">
            <span className="telemetry-label">OCR NOISE INJECTED</span>
            <span className="telemetry-val text-amber mono">
              {summary.noisy_reads} <span style={{ fontSize: 11 }}>({summary.noise_pct}%)</span>
            </span>
            <span className="telemetry-sub">Camera typos fixed by AI</span>
          </div>
          <div className="telemetry-cell">
            <span className="telemetry-label">STOLEN CAR ALERTS</span>
            <span className="telemetry-val text-red mono bold">
              {alerts ? alerts.length : 0}
            </span>
            <span className="telemetry-sub">Watchlist sightings</span>
          </div>
          <div className="telemetry-cell">
            <span className="telemetry-label">PHYSICS CONSTRAINTS</span>
            <span className="telemetry-val mono" style={{ fontSize: 13, marginTop: 2 }}>
              Speed Cap: 80 km/h
            </span>
            <span className="telemetry-sub">Impossible jumps = GAPs</span>
          </div>
        </div>
      )}

      {/* ── Student Friendly Navigation Tabs ── */}
      <div className="student-nav-bar">
        <button
          className={`student-tab-btn ${activeTab === 'TRACKER' ? 'active' : ''}`}
          onClick={() => setActiveTab('TRACKER')}
        >
          🛣️ 1. Trajectory Engine (Component 2)
        </button>
        <button className={`student-tab-btn ${activeTab === 'LIVE' ? 'active' : ''}`} onClick={() => setActiveTab('LIVE')}>
          Live Map & Heatmap
        </button>
        {canAccessVideo && <button className={`student-tab-btn ${activeTab === 'VIDEO' ? 'active' : ''}`} onClick={() => setActiveTab('VIDEO')}>
          Video ANPR Lab
        </button>}
        <button
          className={`student-tab-btn ${activeTab === 'TRAFFIC' ? 'active' : ''}`}
          onClick={() => setActiveTab('TRAFFIC')}
        >
          🚦 2. City Traffic Analytics (Component 3)
        </button>
        <button
          className={`student-tab-btn ${activeTab === 'MAP' ? 'active' : ''}`}
          onClick={() => setActiveTab('MAP')}
        >
          🗺️ 3. Delhi Camera Map (9 Stations)
        </button>
        <button
          className={`student-tab-btn ${activeTab === 'ALERTS' ? 'active' : ''}`}
          onClick={() => setActiveTab('ALERTS')}
        >
          🚨 4. Alert Command Center (Component 4)
        </button>
        <button
          className={`student-tab-btn ${activeTab === 'OCR' ? 'active' : ''}`}
          onClick={() => setActiveTab('OCR')}
        >
          🔬 5. Live AI OCR Engine (Component 1)
        </button>
      </div>

      {/* ── Initial Friendly Empty State (Only for Map Tab before simulation) ── */}
      {!simulated && activeTab === 'MAP' && (
        <div className="dev-terminal-idle-state">
          <div className="idle-terminal-box student-welcome-box">
            <div className="welcome-header">
              <span className="welcome-icon">🏙️</span>
              <h2>Welcome to the Delhi City-Wide ANPR AI Prototype!</h2>
              <p className="welcome-sub">
                This project demonstrates how smart traffic cameras can track vehicle journeys, detect stolen cars, and analyze urban congestion—even when cameras make OCR reading mistakes.
              </p>
            </div>

            <div className="welcome-cards-grid">
              <div className="welcome-card">
                <div className="card-icon">1️⃣</div>
                <div className="card-title">Simulated Traffic Feed</div>
                <div className="card-text">
                  Generates realistic Indian number plates across 9 Delhi intersections with 15% deliberate OCR character swaps (e.g. 0/O, 1/I).
                </div>
              </div>
              <div className="welcome-card">
                <div className="card-icon">2️⃣</div>
                <div className="card-title">AI Fuzzy Trajectory Matcher</div>
                <div className="card-text">
                  Connects sightings into trips using Levenshtein edit distance and splits physically impossible trips (&gt;80 km/h) into labeled GAPs.
                </div>
              </div>
              <div className="welcome-card">
                <div className="card-icon">3️⃣</div>
                <div className="card-title">Air-Gapped Privacy Vault</div>
                <div className="card-text">
                  Keeps vehicle owner identities strictly separated from public traffic planners to protect citizen privacy.
                </div>
              </div>
            </div>

            <div className="welcome-cta">
              <button
                className="btn btn-primary btn-large-cta"
                onClick={() => runSimulation(200)}
                disabled={loading}
              >
                {loading ? 'Starting Engine...' : '🚀 Click Here to Run Traffic Simulation (200 Scans)'}
              </button>
              <div className="cta-hint">No hardware needed · Everything runs locally in memory</div>
            </div>
          </div>
        </div>
      )}

      {/* ── Main Operations Workspace ── */}
      {(simulated || activeTab === 'OCR' || activeTab === 'TRACKER' || activeTab === 'TRAFFIC' || activeTab === 'ALERTS') && (
        <main className="dev-main-workspace">
          {activeTab === 'TRACKER' && (
            <div>
              <TrajectoryReconstructionLab
                defaultPlate={selectedPlate || 'DL01AB1234'}
                onInspect={setInspectData}
              />
              {simulated && (
                <div style={{ marginTop: 20 }}>
                  <DetectionsPanel 
                    detections={detections} 
                    loading={loading}
                    onInspect={setInspectData}
                    onSelectPlate={setSelectedPlate}
                  />
                </div>
              )}
            </div>
          )}

          {activeTab === 'TRAFFIC' && (
            <div>
              <CityTrafficDashboard onInspect={setInspectData} />
            </div>
          )}

          {activeTab === 'MAP' && (
            <div className="dev-topology-grid">
              <CameraTopologyPanel cameras={cameras} onInspect={setInspectData} />
            </div>
          )}

          {activeTab === 'ALERTS' && (
            <div>
              <AlertSystemDashboard 
                onNavigateToTrajectory={(plate) => {
                  setSelectedPlate(plate);
                  setActiveTab('TRACKER');
                }}
                onNavigateToIdentity={handleOpenEnforcement}
              />
            </div>
          )}

          {activeTab === 'OCR' && (
            <div className="dev-analytics-grid">
              <OcrLiveLab 
                onSendToTracker={(plate) => {
                  setSelectedPlate(plate);
                  setActiveTab('TRACKER');
                  if (!simulated) runSimulation(200);
                }}
                onInspect={setInspectData}
              />
            </div>
          )}

          {activeTab === 'LIVE' && <LiveTrafficMapDashboard />}

          {activeTab === 'VIDEO' && canAccessVideo && <VideoUploadLab />}
        </main>
      )}

      {/* ── Modals & Drawers ── */}
      {inspectData && (
        <JsonModal
          title={inspectData.title}
          data={inspectData.data}
          onClose={() => setInspectData(null)}
        />
      )}

      {enforcementPlate && (
        <EnforcementVaultModal
          initialPlate={enforcementPlate}
          onClose={() => setEnforcementPlate(null)}
        />
      )}

      {showLoginModal && <AuthModal required={!isAuthenticated} onClose={() => setShowLoginModal(false)} />}

      {/* Developer Telemetry & Network Console Drawer (collapsible) */}
      <ApiConsoleDrawer onInspect={setInspectData} />
    </div>
  );
}

export default function App() {
  return <AuthProvider><AppContent /></AuthProvider>;
}
