import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  getAlertsPaginated,
  getAlertStats,
  getAlertDetail,
  updateAlertStatus,
  getBlacklist,
  addToBlacklist,
  removeFromBlacklist,
  getAlertConfig,
  updateAlertConfig,
  getQueueStatus,
  createAlertsWebSocket,
  simulate,
  getCameras,
} from '../api';

const ALERT_TYPE_META = {
  BLACKLIST_HIT: { label: 'Blacklist Hit', icon: '🎯', color: '#ef4444', desc: 'Exact match against enforcement blacklist' },
  POSSIBLE_MATCH: { label: 'Possible Match', icon: '🔍', color: '#f59e0b', desc: 'Fuzzy match / low-confidence OCR read' },
  LOITERING: { label: 'Loitering', icon: '⏱️', color: '#8b5cf6', desc: 'Repeated sightings at same camera location' },
  WRONG_WAY: { label: 'Wrong-Way / U-Turn', icon: '↩️', color: '#ec4899', desc: 'Backtracking or counter-flow corridor movement' },
  SPEED_ANOMALY: { label: 'Speed Anomaly', icon: '⚡', color: '#eab308', desc: 'Physically implausible velocity between cameras' },
  RESTRICTED_ZONE: { label: 'Restricted Zone', icon: '🚫', color: '#dc2626', desc: 'Vehicle in restricted security perimeter during curfew' },
};

const PRIORITY_META = {
  CRITICAL: { label: 'CRITICAL', bg: 'rgba(239, 68, 68, 0.2)', border: '#ef4444', text: '#fca5a5' },
  HIGH: { label: 'HIGH', bg: 'rgba(249, 115, 22, 0.2)', border: '#f97316', text: '#fdba74' },
  MEDIUM: { label: 'MEDIUM', bg: 'rgba(245, 158, 11, 0.2)', border: '#f59e0b', text: '#fde68a' },
  LOW: { label: 'LOW', bg: 'rgba(16, 185, 129, 0.2)', border: '#10b981', text: '#6ee7b7' },
};

const STATUS_META = {
  NEW: { label: 'New', color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.15)', border: '#0284c7' },
  UNDER_REVIEW: { label: 'Under Review', color: '#fbbf24', bg: 'rgba(251, 191, 36, 0.15)', border: '#d97706' },
  CONFIRMED: { label: 'Confirmed', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)', border: '#b91c1c' },
  DISMISSED: { label: 'Dismissed', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.15)', border: '#475569' },
};

export default function AlertSystemDashboard({ onNavigateToTrajectory, onNavigateToIdentity, onInspect, initialTab = 'alerts' }) {
  // ─── State ──────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState(initialTab); // 'alerts' | 'cameras' | 'blacklist' | 'config'
  const [cameras, setCameras] = useState(null);
  const [selectedCam, setSelectedCam] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [totalAlerts, setTotalAlerts] = useState(0);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [searchPlate, setSearchPlate] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 25;

  // Selected alert for modal
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [alertModalLoading, setAlertModalLoading] = useState(false);
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewerName, setReviewerName] = useState('Officer Sharma (Duty #4)');
  const [statusUpdating, setStatusUpdating] = useState(false);

  // Real-time WebSocket
  const [wsStatus, setWsStatus] = useState('connecting'); // 'connected' | 'connecting' | 'disconnected'
  const [liveBanner, setLiveBanner] = useState(null);
  const wsRef = useRef(null);

  // Blacklist state
  const [blacklist, setBlacklist] = useState([]);
  const [blacklistLoading, setBlacklistLoading] = useState(false);
  const [showAddBlacklistModal, setShowAddBlacklistModal] = useState(false);
  const [newPlate, setNewPlate] = useState('');
  const [newReason, setNewReason] = useState('');
  const [newPriority, setNewPriority] = useState('HIGH');
  const [blacklistSubmitting, setBlacklistSubmitting] = useState(false);

  // Config state
  const [configs, setConfigs] = useState({});
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [configSuccessMsg, setConfigSuccessMsg] = useState('');
  const [queueStatus, setQueueStatus] = useState(null);

  // Simulating state
  const [isSimulating, setIsSimulating] = useState(false);

  // ─── WebSocket Connection ───────────────────────────────────────────────────
  useEffect(() => {
    wsRef.current = createAlertsWebSocket(
      (msg) => {
        if (msg.event === 'CONNECTED') {
          setWsStatus('connected');
        } else if (msg.event === 'NEW_ALERT' && msg.alert) {
          const newAlert = msg.alert;
          setAlerts((prev) => [newAlert, ...prev.filter((a) => a.id !== newAlert.id)]);
          setTotalAlerts((prev) => prev + 1);
          setLiveBanner({
            id: newAlert.id,
            plate: newAlert.plate_number,
            type: newAlert.alert_type,
            priority: newAlert.priority,
            location: newAlert.location_name,
          });
          // Auto-hide banner after 6s
          setTimeout(() => setLiveBanner(null), 6000);
          fetchStats();
        } else if (msg.event === 'ALERT_STATUS_UPDATED') {
          setAlerts((prev) =>
            prev.map((a) => (a.id === msg.alert_id ? { ...a, status: msg.new_status } : a))
          );
          if (selectedAlert && selectedAlert.id === msg.alert_id) {
            fetchAlertDetail(msg.alert_id);
          }
          fetchStats();
        }
      },
      () => setWsStatus('connected'),
      () => setWsStatus('disconnected'),
      () => setWsStatus('disconnected')
    );

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // ─── Data Fetching ──────────────────────────────────────────────────────────
  const fetchAlerts = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAlertsPaginated({
        status: statusFilter,
        alertType: typeFilter,
        priority: priorityFilter,
        plate: searchPlate,
        page: currentPage,
        limit: pageSize,
      });
      setAlerts(data.alerts || []);
      setTotalAlerts(data.total || 0);
    } catch (err) {
      setError(err.message || 'Failed to fetch alerts');
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const s = await getAlertStats();
      setStats(s);
    } catch (err) {
      console.warn('Failed to load alert stats', err);
    }
  };

  const fetchBlacklist = async () => {
    setBlacklistLoading(true);
    try {
      const data = await getBlacklist({ isActive: null });
      setBlacklist(data.blacklist || []);
    } catch (err) {
      console.warn('Failed to load blacklist', err);
    } finally {
      setBlacklistLoading(false);
    }
  };

  const fetchConfigs = async () => {
    setConfigLoading(true);
    try {
      const [cfgData, qData] = await Promise.all([getAlertConfig(), getQueueStatus()]);
      setConfigs(cfgData.configs || {});
      setQueueStatus(qData);
    } catch (err) {
      console.warn('Failed to load configs', err);
    } finally {
      setConfigLoading(false);
    }
  };

  const fetchCameras = async () => {
    try {
      const res = await getCameras();
      setCameras(res.cameras);
    } catch (err) {
      console.warn('Failed to load cameras in AlertSystemDashboard', err);
    }
  };

  useEffect(() => {
    fetchAlerts();
    fetchStats();
    fetchBlacklist();
    fetchConfigs();
    fetchCameras();
  }, [statusFilter, typeFilter, priorityFilter, searchPlate, currentPage]);

  useEffect(() => {
    if (activeTab === 'blacklist') fetchBlacklist();
    if (activeTab === 'config') fetchConfigs();
  }, [activeTab]);

  // ─── Detail Modal ───────────────────────────────────────────────────────────
  const fetchAlertDetail = async (alertId) => {
    setAlertModalLoading(true);
    try {
      const data = await getAlertDetail(alertId);
      setSelectedAlert(data);
    } catch (err) {
      console.error('Failed to load alert detail', err);
    } finally {
      setAlertModalLoading(false);
    }
  };

  const handleOpenAlert = (alert) => {
    setSelectedAlert(alert);
    setReviewNotes('');
    fetchAlertDetail(alert.id);
  };

  const handleUpdateStatus = async (newStatus) => {
    if (!selectedAlert) return;
    setStatusUpdating(true);
    try {
      const updated = await updateAlertStatus(selectedAlert.id, {
        status: newStatus,
        reviewedBy: reviewerName,
        notes: reviewNotes,
      });
      setSelectedAlert(updated);
      setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      setReviewNotes('');
      fetchStats();
    } catch (err) {
      alert(`Status update failed: ${err.message}`);
    } finally {
      setStatusUpdating(false);
    }
  };

  // ─── Blacklist Handlers ─────────────────────────────────────────────────────
  const handleAddBlacklist = async (e) => {
    e.preventDefault();
    if (!newPlate.trim() || !newReason.trim()) return;
    setBlacklistSubmitting(true);
    try {
      await addToBlacklist({
        plateNumber: newPlate.trim(),
        reason: newReason.trim(),
        priority: newPriority,
        addedBy: reviewerName,
      });
      setShowAddBlacklistModal(false);
      setNewPlate('');
      setNewReason('');
      fetchBlacklist();
      fetchStats();
    } catch (err) {
      alert(`Failed to add plate to blacklist: ${err.message}`);
    } finally {
      setBlacklistSubmitting(false);
    }
  };

  const handleRemoveBlacklist = async (plate) => {
    if (!window.confirm(`Deactivate plate ${plate} from active blacklist?`)) return;
    try {
      await removeFromBlacklist(plate);
      fetchBlacklist();
      fetchStats();
    } catch (err) {
      alert(`Failed to remove: ${err.message}`);
    }
  };

  // ─── Config Handlers ────────────────────────────────────────────────────────
  const handleSaveConfigs = async () => {
    setConfigSaving(true);
    setConfigSuccessMsg('');
    try {
      const updates = {};
      Object.keys(configs).forEach((key) => {
        updates[key] = configs[key].value;
      });
      await updateAlertConfig(updates, reviewerName);
      setConfigSuccessMsg('Configuration thresholds updated successfully.');
      setTimeout(() => setConfigSuccessMsg(''), 4000);
      fetchConfigs();
    } catch (err) {
      alert(`Save failed: ${err.message}`);
    } finally {
      setConfigSaving(false);
    }
  };

  const handleTriggerSimulation = async () => {
    setIsSimulating(true);
    try {
      await simulate(250);
      await Promise.all([fetchAlerts(), fetchStats()]);
    } catch (err) {
      alert(`Simulation failed: ${err.message}`);
    } finally {
      setIsSimulating(false);
    }
  };

  // ─── Helper Formatters ──────────────────────────────────────────────────────
  const formatTime = (isoString) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return isoString;
    }
  };

  const formatRelativeTime = (isoString) => {
    if (!isoString) return '';
    try {
      const diffMs = Date.now() - new Date(isoString).getTime();
      const diffSec = Math.floor(diffMs / 1000);
      if (diffSec < 45) return 'Just now';
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
      return `${Math.floor(diffSec / 86400)}d ago`;
    } catch {
      return '';
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="alert-command-center">
      {/* ── Live Toast Banner ──────────────────────────────────────────────── */}
      {liveBanner && (
        <div
          className="live-alert-banner"
          style={{ borderLeftColor: ALERT_TYPE_META[liveBanner.type]?.color || '#ef4444' }}
          onClick={() => {
            const match = alerts.find((a) => a.id === liveBanner.id);
            if (match) handleOpenAlert(match);
          }}
        >
          <div className="banner-icon">🚨</div>
          <div className="banner-body">
            <div className="banner-title">
              <strong>NEW {liveBanner.priority} ALERT:</strong> {ALERT_TYPE_META[liveBanner.type]?.label || liveBanner.type}
            </div>
            <div className="banner-subtitle">
              Plate <span className="plate-tag">{liveBanner.plate}</span> detected at {liveBanner.location}
            </div>
          </div>
          <button className="banner-dismiss" onClick={(e) => { e.stopPropagation(); setLiveBanner(null); }}>✕</button>
        </div>
      )}

      {/* ── Header & KPI Statistics Ribbon ─────────────────────────────────── */}
      <div className="acc-header">
        <div className="acc-title-area">
          <div className="acc-badge">COMPONENT 4 • REAL-TIME ALERT ENGINE</div>
          <h2>🚨 Alert Command & Intelligence Center</h2>
          <p className="acc-desc">
            Sub-second blacklist matching, fuzzy OCR ambiguity resolution, and multi-camera anomaly detectors (loitering, wrong-way, speed anomalies, restricted zones) with legal audit logging.
          </p>
        </div>

        <div className="acc-header-actions">
          {/* WebSocket Status */}
          <div className={`ws-badge ${wsStatus}`}>
            <span className="ws-dot" />
            <span className="ws-label">
              {wsStatus === 'connected' ? 'LIVE STREAM ACTIVE' : wsStatus === 'connecting' ? 'CONNECTING...' : 'DISCONNECTED'}
            </span>
          </div>

          {/* Simulate Action */}
          <button
            className="btn btn-primary sim-btn"
            onClick={handleTriggerSimulation}
            disabled={isSimulating}
          >
            {isSimulating ? '⚡ Processing Detections...' : '⚡ Generate ANPR Traffic'}
          </button>
        </div>
      </div>

      {/* ── KPI Stat Cards ─────────────────────────────────────────────────── */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">TOTAL ALERTS</div>
          <div className="kpi-value text-cyan">{stats?.status_counts?.TOTAL ?? totalAlerts}</div>
          <div className="kpi-sub">Lifetime engine detections</div>
        </div>

        <div className="kpi-card border-glow-blue">
          <div className="kpi-label">🔴 ACTIVE / NEW</div>
          <div className="kpi-value text-blue">{stats?.status_counts?.NEW ?? 0}</div>
          <div className="kpi-sub">Awaiting operator review</div>
        </div>

        <div className="kpi-card border-glow-amber">
          <div className="kpi-label">🟡 UNDER REVIEW</div>
          <div className="kpi-value text-amber">{stats?.status_counts?.UNDER_REVIEW ?? 0}</div>
          <div className="kpi-sub">Active field investigation</div>
        </div>

        <div className="kpi-card border-glow-red">
          <div className="kpi-label">🚨 CONFIRMED</div>
          <div className="kpi-value text-red">{stats?.status_counts?.CONFIRMED ?? 0}</div>
          <div className="kpi-sub">Verified enforcement hits</div>
        </div>

        <div className="kpi-card border-glow-purple">
          <div className="kpi-label">🎯 BLACKLIST DB</div>
          <div className="kpi-value text-purple">{stats?.active_blacklist_count ?? 5}</div>
          <div className="kpi-sub">Active targeted plates</div>
        </div>
      </div>

      {/* ── Navigation Tabs ────────────────────────────────────────────────── */}
      <div className="acc-nav-tabs">
        <button
          className={`acc-tab-btn ${activeTab === 'alerts' ? 'active' : ''}`}
          onClick={() => setActiveTab('alerts')}
        >
          🚨 Real-Time Alert Feed ({totalAlerts})
        </button>
        <button
          className={`acc-tab-btn ${activeTab === 'cameras' ? 'active' : ''}`}
          onClick={() => setActiveTab('cameras')}
        >
          📡 Delhi Camera Network ({cameras ? Object.keys(cameras).length : 9} Nodes)
        </button>
        <button
          className={`acc-tab-btn ${activeTab === 'blacklist' ? 'active' : ''}`}
          onClick={() => setActiveTab('blacklist')}
        >
          🎯 Blacklist Management ({blacklist.length || stats?.active_blacklist_count || 5})
        </button>
        <button
          className={`acc-tab-btn ${activeTab === 'config' ? 'active' : ''}`}
          onClick={() => setActiveTab('config')}
        >
          ⚙️ Anomaly Rules & Engine Config
        </button>
      </div>

      {/* ──────────────────────────────────────────────────────────────────────
          TAB 1: ALERTS FEED
         ────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'alerts' && (
        <div className="alerts-tab-content">
          {/* Filters Bar */}
          <div className="filter-ribbon">
            <div className="filter-group">
              <span className="filter-label">Status:</span>
              <div className="status-pills">
                {['ALL', 'NEW', 'UNDER_REVIEW', 'CONFIRMED', 'DISMISSED'].map((st) => (
                  <button
                    key={st}
                    className={`pill-btn ${statusFilter === st ? 'active' : ''}`}
                    onClick={() => { setStatusFilter(st); setCurrentPage(1); }}
                  >
                    {st === 'ALL' ? 'All' : STATUS_META[st]?.label || st}
                  </button>
                ))}
              </div>
            </div>

            <div className="filter-group-inline">
              <div className="filter-select-wrap">
                <label>Type:</label>
                <select
                  value={typeFilter}
                  onChange={(e) => { setTypeFilter(e.target.value); setCurrentPage(1); }}
                >
                  <option value="ALL">All Anomaly Types</option>
                  <option value="BLACKLIST_HIT">🎯 Blacklist Hit</option>
                  <option value="POSSIBLE_MATCH">🔍 Possible Match</option>
                  <option value="LOITERING">⏱️ Loitering</option>
                  <option value="WRONG_WAY">↩️ Wrong-Way / U-Turn</option>
                  <option value="SPEED_ANOMALY">⚡ Speed Anomaly</option>
                  <option value="RESTRICTED_ZONE">🚫 Restricted Zone</option>
                </select>
              </div>

              <div className="filter-select-wrap">
                <label>Priority:</label>
                <select
                  value={priorityFilter}
                  onChange={(e) => { setPriorityFilter(e.target.value); setCurrentPage(1); }}
                >
                  <option value="ALL">All Priorities</option>
                  <option value="CRITICAL">🔴 CRITICAL</option>
                  <option value="HIGH">🟠 HIGH</option>
                  <option value="MEDIUM">🟡 MEDIUM</option>
                  <option value="LOW">🟢 LOW</option>
                </select>
              </div>

              <div className="filter-search-wrap">
                <input
                  type="text"
                  placeholder="Search license plate..."
                  value={searchPlate}
                  onChange={(e) => { setSearchPlate(e.target.value); setCurrentPage(1); }}
                />
                {searchPlate && (
                  <button className="clear-search" onClick={() => setSearchPlate('')}>✕</button>
                )}
              </div>
            </div>
          </div>

          {/* Alert Table */}
          <div className="alert-table-wrap">
            {loading ? (
              <div className="loading-state">
                <div className="spinner" />
                <p>Querying alert database & anomaly state...</p>
              </div>
            ) : error ? (
              <div className="error-state">
                <p>⚠️ {error}</p>
                <button className="btn btn-secondary" onClick={fetchAlerts}>Retry</button>
              </div>
            ) : alerts.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">🛡️</div>
                <h3>No Alerts Match Current Filter</h3>
                <p>No anomalous vehicle movements or blacklist violations match the selected criteria.</p>
                <button
                  className="btn btn-primary"
                  onClick={handleTriggerSimulation}
                  disabled={isSimulating}
                >
                  Generate Simulated Traffic
                </button>
              </div>
            ) : (
              <table className="acc-table">
                <thead>
                  <tr>
                    <th>PRIORITY</th>
                    <th>RULE / ANOMALY</th>
                    <th>PLATE NUMBER</th>
                    <th>CAMERA & LOCATION</th>
                    <th>CONFIDENCE</th>
                    <th>TIMESTAMP</th>
                    <th>WORKFLOW STATUS</th>
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert) => {
                    const typeMeta = ALERT_TYPE_META[alert.alert_type] || {
                      label: alert.alert_type,
                      icon: '⚠️',
                      color: '#94a3b8',
                    };
                    const pMeta = PRIORITY_META[alert.priority] || PRIORITY_META.MEDIUM;
                    const stMeta = STATUS_META[alert.status] || STATUS_META.NEW;

                    return (
                      <tr
                        key={alert.id}
                        className={`alert-row status-${alert.status.toLowerCase()}`}
                        onClick={() => handleOpenAlert(alert)}
                      >
                        {/* Priority Badge */}
                        <td>
                          <span
                            className="priority-pill"
                            style={{
                              backgroundColor: pMeta.bg,
                              borderColor: pMeta.border,
                              color: pMeta.text,
                            }}
                          >
                            {alert.priority}
                          </span>
                        </td>

                        {/* Alert Type */}
                        <td>
                          <div className="type-cell">
                            <span className="type-icon">{typeMeta.icon}</span>
                            <div>
                              <div className="type-name">{typeMeta.label}</div>
                              <div className="type-hint">
                                {alert.trigger_details?.match_type === 'fuzzy' || alert.trigger_details?.match_type === 'low_confidence_canonical'
                                  ? `Edit dist ${alert.trigger_details.edit_distance ?? 1}`
                                  : alert.alert_type === 'SPEED_ANOMALY'
                                  ? `${alert.trigger_details?.implied_speed_kmph ?? '—'} km/h`
                                  : alert.alert_type === 'LOITERING'
                                  ? `${alert.trigger_details?.detection_count ?? 3}x at camera`
                                  : alert.trigger_details?.rule || ''}
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Plate */}
                        <td>
                          <span className="plate-badge-mono">{alert.plate_number}</span>
                        </td>

                        {/* Location */}
                        <td>
                          <div className="loc-cell">
                            <span className="loc-cam-id">{alert.camera_id}</span>
                            <span className="loc-name">{alert.location_name}</span>
                          </div>
                        </td>

                        {/* Confidence */}
                        <td>
                          <div className="confidence-meter-wrap">
                            <div className="confidence-bar-bg">
                              <div
                                className="confidence-bar-fill"
                                style={{
                                  width: `${Math.round((alert.confidence || 0) * 100)}%`,
                                  backgroundColor:
                                    alert.confidence >= 0.85
                                      ? '#10b981'
                                      : alert.confidence >= 0.7
                                      ? '#f59e0b'
                                      : '#ef4444',
                                }}
                              />
                            </div>
                            <span className="confidence-num">
                              {Math.round((alert.confidence || 0) * 100)}%
                            </span>
                          </div>
                        </td>

                        {/* Timestamp */}
                        <td>
                          <div className="time-cell">
                            <span className="time-primary">{formatTime(alert.timestamp)}</span>
                            <span className="time-relative">{formatRelativeTime(alert.timestamp)}</span>
                          </div>
                        </td>

                        {/* Status */}
                        <td>
                          <span
                            className="status-pill"
                            style={{
                              backgroundColor: stMeta.bg,
                              borderColor: stMeta.border,
                              color: stMeta.color,
                            }}
                          >
                            {stMeta.label}
                          </span>
                        </td>

                        {/* Action buttons */}
                        <td onClick={(e) => e.stopPropagation()}>
                          <div className="row-actions">
                            <button
                              className="action-link-btn"
                              title="Reconstruct full vehicle trajectory"
                              onClick={() => {
                                if (onNavigateToTrajectory) {
                                  onNavigateToTrajectory(alert.plate_number);
                                }
                              }}
                            >
                              🗺️ Track
                            </button>
                            <button
                              className="action-link-btn"
                              title="View enforcement identity dossier"
                              onClick={() => {
                                if (onNavigateToIdentity) {
                                  onNavigateToIdentity(alert.plate_number);
                                }
                              }}
                            >
                              🔒 Owner
                            </button>
                            <button
                              className="action-btn-primary"
                              onClick={() => handleOpenAlert(alert)}
                            >
                              Review →
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────
          TAB 2: BLACKLIST MANAGEMENT
         ────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'blacklist' && (
        <div className="blacklist-tab-content">
          <div className="bl-header">
            <div>
              <h3>Enforcement Blacklist Database</h3>
              <p className="subtext">
                Plates on this list trigger instant alerts when captured by any ANPR camera across Delhi NCR. Matches are evaluated in O(1) time via in-memory hashed cache.
              </p>
            </div>
            <button
              className="btn btn-primary"
              onClick={() => setShowAddBlacklistModal(true)}
            >
              + Add Vehicle Plate
            </button>
          </div>

          <div className="bl-table-wrap">
            {blacklistLoading ? (
              <div className="loading-state"><div className="spinner" /><p>Loading blacklist...</p></div>
            ) : (
              <table className="acc-table">
                <thead>
                  <tr>
                    <th>PLATE NUMBER</th>
                    <th>PRIORITY</th>
                    <th>WARRANT / REASON</th>
                    <th>STATUS</th>
                    <th>DATE ADDED</th>
                    <th>ADDED BY</th>
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {blacklist.map((item) => (
                    <tr key={item.id || item.plate_number} className={!item.is_active ? 'dimmed-row' : ''}>
                      <td>
                        <span className="plate-badge-mono">{item.plate_number}</span>
                      </td>
                      <td>
                        <span
                          className="priority-pill"
                          style={{
                            backgroundColor: PRIORITY_META[item.priority]?.bg,
                            borderColor: PRIORITY_META[item.priority]?.border,
                            color: PRIORITY_META[item.priority]?.text,
                          }}
                        >
                          {item.priority}
                        </span>
                      </td>
                      <td className="bl-reason-cell">{item.reason}</td>
                      <td>
                        <span className={`status-pill ${item.is_active ? 'active' : 'inactive'}`}>
                          {item.is_active ? 'ACTIVE' : 'DEACTIVATED'}
                        </span>
                      </td>
                      <td className="time-cell">{formatTime(item.date_added)}</td>
                      <td><span className="reviewer-tag">{item.added_by || 'system'}</span></td>
                      <td>
                        {item.is_active ? (
                          <button
                            className="btn-danger-sm"
                            onClick={() => handleRemoveBlacklist(item.plate_number)}
                          >
                            Deactivate
                          </button>
                        ) : (
                          <span className="text-muted">Archived</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────
          TAB 3: CONFIGURATION & ANOMALY RULES
         ────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'config' && (
        <div className="config-tab-content">
          <div className="cfg-header">
            <div>
              <h3>Anomaly Engine Thresholds & Channel Integrations</h3>
              <p className="subtext">
                Tune rule-based anomaly detection sensitivity, loitering windows, speed bounds, and notification dispatcher parameters. Changes persist in database and invalidate in-memory engine cache instantly.
              </p>
            </div>
            <div className="cfg-actions">
              {configSuccessMsg && <span className="success-tag">✓ {configSuccessMsg}</span>}
              <button
                className="btn btn-primary"
                onClick={handleSaveConfigs}
                disabled={configSaving}
              >
                {configSaving ? 'Saving...' : '💾 Save Configurations'}
              </button>
            </div>
          </div>

          {/* Queue & Broker Status Card */}
          <div className="broker-status-card">
            <div className="broker-status-icon">📬</div>
            <div className="broker-status-info">
              <div className="broker-title">
                Message Queue Consumer: <strong>{queueStatus?.mode === 'broker' ? 'RabbitMQ / Kafka Broker' : 'In-Process Simulation Bridge'}</strong>
              </div>
              <div className="broker-desc">
                Topic: <code>{queueStatus?.topic || 'anpr.detections'}</code> • Type: {queueStatus?.queue_type || 'rabbitmq'} • Broker Connected: {queueStatus?.is_connected ? '🟢 Yes' : '⚪ Simulation Fallback'}
              </div>
            </div>
          </div>

          {configLoading ? (
            <div className="loading-state"><div className="spinner" /><p>Loading configurations...</p></div>
          ) : (
            <div className="config-grid">
              {/* Card 1: Loitering Rule */}
              <div className="config-section-card">
                <h4>⏱️ Loitering Anomaly Detector</h4>
                <p className="config-card-desc">
                  Flags vehicles that repeatedly pass or circle the same camera node within a sliding time window.
                </p>
                <div className="form-group">
                  <label>Sighting Count Threshold (Detections)</label>
                  <input
                    type="number"
                    min="2"
                    max="20"
                    value={configs['loitering_count_threshold']?.value || '3'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        loitering_count_threshold: { ...configs['loitering_count_threshold'], value: e.target.value },
                      })
                    }
                  />
                  <span className="field-hint">Default: 3 sightings at the same camera</span>
                </div>
                <div className="form-group">
                  <label>Sliding Window (Minutes)</label>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={configs['loitering_window_minutes']?.value || '10'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        loitering_window_minutes: { ...configs['loitering_window_minutes'], value: e.target.value },
                      })
                    }
                  />
                  <span className="field-hint">Default: 10 minutes</span>
                </div>
              </div>

              {/* Card 2: Speed Anomaly */}
              <div className="config-section-card">
                <h4>⚡ Implausible Speed Detector</h4>
                <p className="config-card-desc">
                  Flags consecutive camera sightings whose implied velocity exceeds physical road limits (indicates plate clone or OCR error).
                </p>
                <div className="form-group">
                  <label>Max Plausible Speed (km/h)</label>
                  <input
                    type="number"
                    min="80"
                    max="300"
                    value={configs['speed_anomaly_threshold_kmph']?.value || '150'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        speed_anomaly_threshold_kmph: { ...configs['speed_anomaly_threshold_kmph'], value: e.target.value },
                      })
                    }
                  />
                  <span className="field-hint">Default: 150 km/h (flags potential plate clones)</span>
                </div>
                <div className="form-group">
                  <label>Deduplication Suppression Window (Minutes)</label>
                  <input
                    type="number"
                    min="1"
                    max="30"
                    value={configs['dedup_window_minutes']?.value || '5'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        dedup_window_minutes: { ...configs['dedup_window_minutes'], value: e.target.value },
                      })
                    }
                  />
                  <span className="field-hint">Suppresses alert flooding for the same plate/rule</span>
                </div>
              </div>

              {/* Card 3: Fuzzy Matching */}
              <div className="config-section-card">
                <h4>🔍 OCR Fuzzy Matcher & Ambiguity</h4>
                <p className="config-card-desc">
                  Triggers "Possible Match — Needs Review" when OCR confidence is low and plate is within edit distance of blacklist.
                </p>
                <div className="form-group">
                  <label>Fuzzy Match OCR Confidence Ceiling</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0.5"
                    max="1.0"
                    value={configs['fuzzy_match_confidence_threshold']?.value || '0.85'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        fuzzy_match_confidence_threshold: { ...configs['fuzzy_match_confidence_threshold'], value: e.target.value },
                      })
                    }
                  />
                  <span className="field-hint">Only inspects fuzzy edit distance when OCR confidence &lt; threshold</span>
                </div>
                <div className="form-group">
                  <label>Max Levenshtein Edit Distance</label>
                  <input
                    type="number"
                    min="1"
                    max="3"
                    value={configs['fuzzy_match_max_edit_distance']?.value || '2'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        fuzzy_match_max_edit_distance: { ...configs['fuzzy_match_max_edit_distance'], value: e.target.value },
                      })
                    }
                  />
                  <span className="field-hint">Default: ≤ 2 character edits</span>
                </div>
              </div>

              {/* Card 4: Notification Channels */}
              <div className="config-section-card">
                <h4>📡 Dispatcher Channels (Email / SMS)</h4>
                <p className="config-card-desc">
                  Real-time push via WebSocket is always active. Optional external dispatch to SMS/Email for HIGH &amp; CRITICAL alerts.
                </p>
                <div className="form-group">
                  <label>Email Notifications (SMTP)</label>
                  <select
                    value={configs['email_enabled']?.value || 'false'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        email_enabled: { ...configs['email_enabled'], value: e.target.value },
                      })
                    }
                  >
                    <option value="false">Disabled (WebSocket Only)</option>
                    <option value="true">Enabled (Send HTML Email for HIGH/CRITICAL)</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>SMS Notifications (Twilio)</label>
                  <select
                    value={configs['sms_enabled']?.value || 'false'}
                    onChange={(e) =>
                      setConfigs({
                        ...configs,
                        sms_enabled: { ...configs['sms_enabled'], value: e.target.value },
                      })
                    }
                  >
                    <option value="false">Disabled</option>
                    <option value="true">Enabled (Send SMS for CRITICAL Only)</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────
          TAB 4: DELHI CAMERA SENSOR TOPOLOGY (MERGED)
         ────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'cameras' && (
        <div className="cameras-tab-content">
          <div className="card-header" style={{ padding: '0 0 14px 0', borderBottom: '1px solid rgba(255,255,255,0.08)', marginBottom: 16 }}>
            <div className="card-header-left">
              <span className="dev-tag">SENSOR TOPOLOGY &amp; NCR HARDWARE TELEMETRY</span>
              <h3 style={{ margin: '4px 0 0 0', color: '#fff' }}>
                Delhi NCR Multi-Camera Sensor Infrastructure ({cameras ? Object.keys(cameras).length : 9} Stations)
              </h3>
            </div>
            {onInspect && cameras && (
              <button 
                className="btn-dev-sm" 
                onClick={() => onInspect({ title: 'Camera Network Matrix JSON', data: cameras })}
              >
                Matrix JSON
              </button>
            )}
          </div>

          <p className="student-helper-text" style={{ marginBottom: 16 }}>
            💡 <strong>Sensor Network Context:</strong> These smart ANPR cameras continuously stream telemetry and trigger instant alerts for blacklist violations, loitering, wrong-way movement, and speed physics anomalies across Delhi NCR. Click any camera card to highlight it.
          </p>

          <div className="topology-grid">
            <div className="topology-table-wrap">
              <table className="data-table dev-grid">
                <thead>
                  <tr>
                    <th>CAMERA ID</th>
                    <th>INTERSECTION / LANDMARK</th>
                    <th>NCR REGION</th>
                    <th>GPS COORDINATES</th>
                    <th>TELEMETRY</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(cameras || {}).map(([id, cam]) => (
                    <tr 
                      key={id} 
                      className={`dev-row ${selectedCam === id ? 'row-selected' : ''}`}
                      onClick={() => setSelectedCam(id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="mono bold highlight-cyan">{id}</td>
                      <td><strong>{cam.name ? cam.name.split('—')[0].trim() : id}</strong></td>
                      <td>
                        <span className="zone-tag">{cam.zone || 'Delhi Arterial'}</span>
                      </td>
                      <td className="mono text-muted" style={{ fontSize: 11 }}>
                        {cam.lat ? cam.lat.toFixed(4) : '28.6139'}°N, {cam.lon ? cam.lon.toFixed(4) : '77.2090'}°E
                      </td>
                      <td>
                        <button 
                          className="btn-dev-xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (onInspect) onInspect({ title: `Node Telemetry: ${id}`, data: { id, ...cam } });
                          }}
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="topology-schematic">
              <div className="schematic-header">
                <span className="bold">NCR SENSOR SCHEMATIC MAP</span>
                <span className="schematic-status">● {cameras ? Object.keys(cameras).length : 9} SENSORS OPERATIONAL</span>
              </div>
              <div className="schematic-nodes">
                {Object.entries(cameras || {}).map(([id, cam]) => (
                  <div 
                    key={id} 
                    className={`schematic-node-card ${selectedCam === id ? 'node-active' : ''}`}
                    onClick={() => setSelectedCam(id)}
                  >
                    <div className="node-id-bar">
                      <span className="mono bold">{id}</span>
                      <span className="node-status-dot" />
                    </div>
                    <div className="node-name">{cam.name ? cam.name.split('—')[0].trim() : id}</div>
                    <div className="node-zone">{cam.zone || 'Delhi NCR'}</div>
                    <div className="node-coords">
                      {cam.lat ? cam.lat.toFixed(4) : '28.6139'}°N, {cam.lon ? cam.lon.toFixed(4) : '77.2090'}°E
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────
          ALERT DETAILS & AUDIT TRAIL MODAL
         ────────────────────────────────────────────────────────────────────── */}
      {selectedAlert && (
        <div className="modal-overlay" onClick={() => setSelectedAlert(null)}>
          <div className="modal-content alert-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-group">
                <span
                  className="priority-pill"
                  style={{
                    backgroundColor: PRIORITY_META[selectedAlert.priority]?.bg,
                    borderColor: PRIORITY_META[selectedAlert.priority]?.border,
                    color: PRIORITY_META[selectedAlert.priority]?.text,
                  }}
                >
                  {selectedAlert.priority}
                </span>
                <h3>
                  {ALERT_TYPE_META[selectedAlert.alert_type]?.icon}{' '}
                  {ALERT_TYPE_META[selectedAlert.alert_type]?.label || selectedAlert.alert_type}
                </h3>
              </div>
              <button className="modal-close" onClick={() => setSelectedAlert(null)}>✕</button>
            </div>

            <div className="modal-body">
              {alertModalLoading ? (
                <div className="loading-state"><div className="spinner" /><p>Loading audit trail...</p></div>
              ) : (
                <>
                  {/* Overview Grid */}
                  <div className="detail-overview-grid">
                    <div className="detail-field">
                      <span className="field-title">TARGET LICENSE PLATE</span>
                      <span className="plate-badge-mono large">{selectedAlert.plate_number}</span>
                    </div>

                    <div className="detail-field">
                      <span className="field-title">SIGHTING LOCATION</span>
                      <span className="field-value">
                        {selectedAlert.location_name} (<code>{selectedAlert.camera_id}</code>)
                      </span>
                    </div>

                    <div className="detail-field">
                      <span className="field-title">TIMESTAMP</span>
                      <span className="field-value">{formatTime(selectedAlert.timestamp)} ({formatRelativeTime(selectedAlert.timestamp)})</span>
                    </div>

                    <div className="detail-field">
                      <span className="field-title">OCR CONFIDENCE</span>
                      <span className="field-value">{Math.round((selectedAlert.confidence || 0) * 100)}%</span>
                    </div>
                  </div>

                  {/* Trigger Explanation Card */}
                  <div className="trigger-explanation-card">
                    <h4>🔍 Detection Engine Explanation</h4>
                    <p className="trigger-desc">
                      {selectedAlert.trigger_details?.description || 'Alert triggered by anomaly detection pipeline.'}
                    </p>
                    <pre className="trigger-json">
                      {JSON.stringify(selectedAlert.trigger_details || {}, null, 2)}
                    </pre>
                  </div>

                  {/* Workflow Transition Box */}
                  <div className="workflow-action-box">
                    <h4>🛡️ Operator Workflow Action</h4>
                    <div className="workflow-form">
                      <div className="workflow-inputs">
                        <div className="form-group">
                          <label>Reviewing Officer ID / Name</label>
                          <input
                            type="text"
                            value={reviewerName}
                            onChange={(e) => setReviewerName(e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Action Notes &amp; Legal Justification</label>
                          <textarea
                            placeholder="Add disposition notes, dispatch details, or case reference..."
                            rows="2"
                            value={reviewNotes}
                            onChange={(e) => setReviewNotes(e.target.value)}
                          />
                        </div>
                      </div>

                      <div className="workflow-buttons">
                        <button
                          className="btn-status-under-review"
                          disabled={statusUpdating || selectedAlert.status === 'UNDER_REVIEW'}
                          onClick={() => handleUpdateStatus('UNDER_REVIEW')}
                        >
                          🟡 Mark Under Review
                        </button>
                        <button
                          className="btn-status-confirm"
                          disabled={statusUpdating || selectedAlert.status === 'CONFIRMED'}
                          onClick={() => handleUpdateStatus('CONFIRMED')}
                        >
                          🔴 Confirm Violation
                        </button>
                        <button
                          className="btn-status-dismiss"
                          disabled={statusUpdating || selectedAlert.status === 'DISMISSED'}
                          onClick={() => handleUpdateStatus('DISMISSED')}
                        >
                          ⚪ Dismiss Alert
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Legal Audit Trail Timeline */}
                  <div className="audit-trail-section">
                    <h4>📋 Legal Chain of Custody &amp; Audit Trail ({selectedAlert.audit_trail?.length || 0} entries)</h4>
                    {(!selectedAlert.audit_trail || selectedAlert.audit_trail.length === 0) ? (
                      <p className="subtext">No workflow status changes recorded yet. Alert is in initial NEW state.</p>
                    ) : (
                      <div className="audit-timeline">
                        {selectedAlert.audit_trail.map((audit, idx) => (
                          <div key={audit.id || idx} className="audit-item">
                            <div className="audit-marker" />
                            <div className="audit-content">
                              <div className="audit-top">
                                <span className="audit-action">
                                  Status Changed: <strong>{audit.old_status}</strong> → <strong>{audit.new_status}</strong>
                                </span>
                                <span className="audit-time">{formatTime(audit.reviewed_at)}</span>
                              </div>
                              <div className="audit-reviewer">Reviewed by: {audit.reviewed_by}</div>
                              {audit.notes && <div className="audit-notes">"{audit.notes}"</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Deep link actions */}
                  <div className="modal-footer-actions">
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        setSelectedAlert(null);
                        if (onNavigateToTrajectory) onNavigateToTrajectory(selectedAlert.plate_number);
                      }}
                    >
                      🗺️ View Full Historical Trajectory →
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={() => {
                        setSelectedAlert(null);
                        if (onNavigateToIdentity) onNavigateToIdentity(selectedAlert.plate_number);
                      }}
                    >
                      🔒 Enforcement Identity Lookup →
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────
          ADD TO BLACKLIST MODAL
         ────────────────────────────────────────────────────────────────────── */}
      {showAddBlacklistModal && (
        <div className="modal-overlay" onClick={() => setShowAddBlacklistModal(false)}>
          <div className="modal-content add-bl-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>🎯 Add Vehicle to Enforcement Blacklist</h3>
              <button className="modal-close" onClick={() => setShowAddBlacklistModal(false)}>✕</button>
            </div>
            <form onSubmit={handleAddBlacklist}>
              <div className="modal-body">
                <div className="form-group">
                  <label>License Plate Number *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. DL-01-AB-1234"
                    value={newPlate}
                    onChange={(e) => setNewPlate(e.target.value.toUpperCase())}
                  />
                  <span className="field-hint">Spaces and hyphens are automatically normalized</span>
                </div>

                <div className="form-group">
                  <label>Priority Level</label>
                  <select value={newPriority} onChange={(e) => setNewPriority(e.target.value)}>
                    <option value="CRITICAL">🔴 CRITICAL (Armed Robbery / Stolen / Amber Alert)</option>
                    <option value="HIGH">🟠 HIGH (Hit &amp; Run / Escaped Impound)</option>
                    <option value="MEDIUM">🟡 MEDIUM (Repeat Challan Violations)</option>
                    <option value="LOW">🟢 LOW (Administrative Watch)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Legal Reason / FIR Case Reference *</label>
                  <textarea
                    required
                    placeholder="e.g. Reported stolen vehicle — FIR #2026/DL/9941 at Connaught Place PS"
                    rows="3"
                    value={newReason}
                    onChange={(e) => setNewReason(e.target.value)}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowAddBlacklistModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={blacklistSubmitting}
                >
                  {blacklistSubmitting ? 'Adding...' : 'Add to Blacklist'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
