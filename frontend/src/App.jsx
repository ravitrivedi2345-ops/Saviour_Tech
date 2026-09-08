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
import TrajectoryReconstructionLab from './components/TrajectoryReconstructionLab';
import AlertSystemDashboard from './components/AlertSystemDashboard';
import EnforcementVaultModal from './components/EnforcementVaultModal';
import JsonModal from './components/JsonModal';
import ApiConsoleDrawer from './components/ApiConsoleDrawer';
import OcrLiveLab from './components/OcrLiveLab';
import CityTrafficDashboard from './components/CityTrafficDashboard';
import AuthModal from './components/AuthModal';

const COUNT_OPTIONS = [100, 200, 500, 1000];

function AppContent() {
  const { user, isAuthenticated, canAccessVault, setShowLoginModal, showLoginModal, logout } = useAuth();
  const [simCount, setSimCount] = useState(200);
  const [loading, setLoading] = useState(false);
  const [simulated, setSimulated] = useState(false);
  const [activeTab, setActiveTab] = useState('TRACKER'); // 'TRACKER' | 'TRAFFIC' | 'ALERTS' | 'OCR'
  const [ocrInitialMode, setOcrInitialMode] = useState('IMAGE'); // 'IMAGE' | 'VIDEO'
  const [trajViewMode, setTrajViewMode] = useState('HYBRID'); // 'HYBRID' | 'TRAJECTORY' | 'LIVEMAP'
  const [alertInitialTab, setAlertInitialTab] = useState('alerts'); // 'alerts' | 'cameras' | 'blacklist' | 'config'

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
    setTrajViewMode('HYBRID');
    setSelectedPlate(plate);
    if (!simulated) {
      runSimulation(200);
    }
  };

  const handleOpenLiveMap = () => {
    setTrajViewMode('LIVEMAP');
    setActiveTab('TRACKER');
  };

  const handleOpenVideoLab = () => {
    setOcrInitialMode('VIDEO');
    setActiveTab('OCR');
  };

  const handleOpenImageLab = () => {
    setOcrInitialMode('IMAGE');
    setActiveTab('OCR');
  };

  const handleOpenAlerts = (subTab = 'alerts') => {
    setAlertInitialTab(subTab);
    setActiveTab('ALERTS');
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
              City-Wide ANPR Trajectory Tracking &amp; Urban Traffic Analytics
            </div>
            <div className="header-sub-meta">
              Delhi NCR Multi-Camera AI · Fuzzy Plate Matching · Speed Physics Checks · Isolated Police Vault
            </div>
          </div>
        </div>

        {/* Global Controls & Police View Button */}
        <div className="header-right-controls">
          {isAuthenticated ? (
            <div className="auth-header-user-wrap">
              <button className="session-chip" onClick={() => setShowLoginModal(true)} title="Click to switch role or view permissions">
                <span className="pulse-dot" /> 
                <strong>{user.username}</strong> ({user.role})
              </button>
              <button className="btn-dev-xs btn-signout" onClick={logout} title="Sign out">
                Sign Out
              </button>
            </div>
          ) : (
            <button className="btn-dev-enforcement btn-signin-pulse" onClick={() => setShowLoginModal(true)}>
              🔐 Sign In / Demo Roles
            </button>
          )}
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

      {/* ── 4 System Extensions Highlights Banner ── */}
      <div className="extensions-showcase-ribbon">
        <div className="ribbon-tag">
          <span className="ribbon-badge">✨ SYSTEM EXTENSIONS</span>
          <span className="ribbon-sub">4 Major Capabilities:</span>
        </div>
        <div className="ribbon-cards-grid">
          <button 
            type="button" 
            className={`ribbon-item-btn ${showLoginModal ? 'active' : ''}`}
            onClick={() => setShowLoginModal(true)}
          >
            <span className="ribbon-icon">🔐</span>
            <div className="ribbon-text">
              <span className="ribbon-item-title">1. Authentication (RBAC)</span>
              <span className="ribbon-item-desc">
                {isAuthenticated ? `Logged in: ${user.role}` : 'Admin, Police, Planner'}
              </span>
            </div>
          </button>

          <button 
            type="button" 
            className={`ribbon-item-btn ${activeTab === 'TRACKER' && trajViewMode === 'LIVEMAP' ? 'active' : ''}`}
            onClick={handleOpenLiveMap}
          >
            <span className="ribbon-icon">🌐</span>
            <div className="ribbon-text">
              <span className="ribbon-item-title">2. Live Traffic &amp; Heatmap</span>
              <span className="ribbon-item-desc">Real-time WebSocket + Delhi nodes</span>
            </div>
          </button>

          <button 
            type="button" 
            className={`ribbon-item-btn ${activeTab === 'OCR' && ocrInitialMode === 'VIDEO' ? 'active' : ''}`}
            onClick={handleOpenVideoLab}
          >
            <span className="ribbon-icon">📹</span>
            <div className="ribbon-text">
              <span className="ribbon-item-title">3. Video Upload ANPR Lab</span>
              <span className="ribbon-item-desc">≥10s validation + ML OCR stream</span>
            </div>
          </button>

          <button 
            type="button" 
            className={`ribbon-item-btn ${activeTab === 'TRACKER' && trajViewMode === 'HYBRID' ? 'active' : ''}`}
            onClick={() => {
              setTrajViewMode('HYBRID');
              setActiveTab('TRACKER');
            }}
          >
            <span className="ribbon-icon">🛣️</span>
            <div className="ribbon-text">
              <span className="ribbon-item-title">4. Indian Road Network</span>
              <span className="ribbon-item-desc">Delhi NCR OSRM road snapping</span>
            </div>
          </button>
        </div>
      </div>

      {/* ── Student & Evaluator Quick Guide Banner ── */}
      <StudentGuideBanner onTryDemo={handleTryDemo} onOpenLive={handleOpenLiveMap} onOpenVideo={handleOpenVideoLab} />

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

      {/* ── 4 Streamlined Master Navigation Tabs ── */}
      <div className="student-nav-bar">
        <button
          className={`student-tab-btn new-ext-tab ${activeTab === 'TRACKER' ? 'active' : ''}`}
          onClick={() => setActiveTab('TRACKER')}
        >
          🛣️ 1. Trajectory Engine &amp; Live Traffic Center <span className="tab-pill-ext">UNIFIED</span>
        </button>

        <button
          className={`student-tab-btn ${activeTab === 'TRAFFIC' ? 'active' : ''}`}
          onClick={() => setActiveTab('TRAFFIC')}
        >
          🚦 2. City Traffic Analytics
        </button>

        <button
          className={`student-tab-btn new-ext-tab ${activeTab === 'ALERTS' ? 'active' : ''}`}
          onClick={() => handleOpenAlerts('alerts')}
        >
          🚨 3. Alert Command Center &amp; Delhi Camera Network <span className="tab-pill-ext">UNIFIED</span>
        </button>

        <button
          className={`student-tab-btn new-ext-tab ${activeTab === 'OCR' ? 'active' : ''}`}
          onClick={handleOpenImageLab}
        >
          🔬 4. Live AI OCR &amp; Video ANPR Engine <span className="tab-pill-ext">UNIFIED</span>
        </button>
      </div>

      {/* ── Main Operations Workspace ── */}
      <main className="dev-main-workspace">
        {activeTab === 'TRACKER' && (
          <div>
            <TrajectoryReconstructionLab
              key={`${selectedPlate}-${trajViewMode}`}
              defaultPlate={selectedPlate || 'DL01AB1234'}
              initialViewMode={trajViewMode}
              onInspect={setInspectData}
            />
            {simulated && (
              <div style={{ marginTop: 20 }}>
                <DetectionsPanel 
                  detections={detections} 
                  loading={loading}
                  onInspect={setInspectData}
                  onSelectPlate={(plate) => {
                    setSelectedPlate(plate);
                    setTrajViewMode('HYBRID');
                  }}
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

        {activeTab === 'ALERTS' && (
          <div>
            <AlertSystemDashboard 
              key={alertInitialTab}
              initialTab={alertInitialTab}
              onNavigateToTrajectory={(plate) => {
                setSelectedPlate(plate);
                setTrajViewMode('HYBRID');
                setActiveTab('TRACKER');
              }}
              onNavigateToIdentity={handleOpenEnforcement}
              onInspect={setInspectData}
            />
          </div>
        )}

        {activeTab === 'OCR' && (
          <div className="dev-analytics-grid">
            <OcrLiveLab 
              key={ocrInitialMode}
              initialSubTab={ocrInitialMode}
              onSendToTracker={(plate) => {
                setSelectedPlate(plate);
                setTrajViewMode('HYBRID');
                setActiveTab('TRACKER');
                if (!simulated) runSimulation(200);
              }}
              onInspect={setInspectData}
            />
          </div>
        )}
      </main>

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

      {showLoginModal && (
        <AuthModal 
          required={false} 
          onClose={() => setShowLoginModal(false)} 
        />
      )}

      {/* Developer Telemetry & Network Console Drawer (collapsible) */}
      <ApiConsoleDrawer onInspect={setInspectData} />
    </div>
  );
}

export default function App() {
  return <AuthProvider><AppContent /></AuthProvider>;
}
