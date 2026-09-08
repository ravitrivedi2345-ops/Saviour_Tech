import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

const ROLE_PRESETS = [
  {
    role: 'Admin',
    label: 'System Admin',
    username: 'admin',
    password: 'Admin@123',
    icon: '👑',
    department: 'Central Command & System Ops',
    badgeColor: '#ef4444',
    badgeBg: 'rgba(239, 68, 68, 0.12)',
    badgeBorder: 'rgba(239, 68, 68, 0.35)',
    description: 'Full system control, blacklist CRUD, audit logs & analytics.',
  },
  {
    role: 'Traffic Police',
    label: 'Traffic Police Inspector',
    username: 'police_sharma',
    password: 'Police@123',
    icon: '👮‍♂️',
    department: 'South District Enforcement Cell',
    badgeColor: '#3b82f6',
    badgeBg: 'rgba(59, 130, 246, 0.12)',
    badgeBorder: 'rgba(59, 130, 246, 0.35)',
    description: 'Trajectory tracking, private citizen owner vault, alerts & video ANPR.',
  },
  {
    role: 'City Planner',
    label: 'Urban Mobility Planner',
    username: 'planner_verma',
    password: 'Planner@123',
    icon: '📊',
    department: 'Urban Mobility & Transit Bureau',
    badgeColor: '#10b981',
    badgeBg: 'rgba(16, 185, 129, 0.12)',
    badgeBorder: 'rgba(16, 185, 129, 0.35)',
    description: 'City traffic analytics, congestion heatmaps & corridor speed analysis.',
  },
];

export default function AuthModal({ onClose, required = false }) {
  const { login, loading } = useAuth();
  const [username, setUsername] = useState('police_sharma');
  const [password, setPassword] = useState('Police@123');
  const [showPassword, setShowPassword] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('police_sharma');
  const [error, setError] = useState('');
  const [activeView, setActiveView] = useState('login'); // 'login' | 'matrix'

  // Auto-focus & escape handling
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !required && onClose) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [required, onClose]);

  const handleSelectPreset = (preset, autoSubmit = false) => {
    setSelectedPreset(preset.username);
    setUsername(preset.username);
    setPassword(preset.password);
    setError('');
    if (autoSubmit) {
      handleDirectLogin(preset.username, preset.password);
    }
  };

  const handleDirectLogin = async (userVal, passVal) => {
    setError('');
    try {
      await login(userVal.trim(), passVal);
      if (onClose) onClose();
    } catch (err) {
      setError(err.message || 'Authentication failed. Please check credentials.');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please enter both username and password.');
      return;
    }
    handleDirectLogin(username, password);
  };

  return (
    <div className="auth-overlay-backdrop" onClick={required ? undefined : onClose}>
      <div className="auth-modal-card" onClick={e => e.stopPropagation()}>
        {/* Glowing ambient background flare */}
        <div className="auth-modal-glow" />

        {/* ── Header ── */}
        <div className="auth-header-bar">
          <div className="auth-brand-badge">
            <div className="auth-shield-icon">🛡️</div>
            <div>
              <div className="auth-platform-tag">
                <span className="auth-dot-pulse" />
                DELHI TRAFFIC POLICE · SECURE AI GATEWAY
              </div>
              <h2 className="auth-modal-heading">Platform Authentication</h2>
            </div>
          </div>
          {!required && (
            <button 
              type="button" 
              className="auth-close-btn" 
              onClick={onClose} 
              aria-label="Close modal"
              title="Close (Esc)"
            >
              ✕
            </button>
          )}
        </div>

        {/* ── Subtitle / Mode Tabs ── */}
        <div className="auth-nav-tabs">
          <button 
            type="button"
            className={`auth-nav-tab ${activeView === 'login' ? 'active' : ''}`}
            onClick={() => setActiveView('login')}
          >
            🔑 Sign In Portal
          </button>
          <button 
            type="button"
            className={`auth-nav-tab ${activeView === 'matrix' ? 'active' : ''}`}
            onClick={() => setActiveView('matrix')}
          >
            📋 Role & Permissions Matrix
          </button>
        </div>

        {activeView === 'login' ? (
          <div className="auth-body-content">
            {/* ── 1-Click Quick Select Demo Cards ── */}
            <div className="auth-preset-section">
              <div className="auth-section-label">
                <span>⚡ 1-Click Quick Demo Sign In</span>
                <span className="auth-section-sub">Select a role to auto-fill credentials</span>
              </div>
              <div className="auth-preset-grid">
                {ROLE_PRESETS.map((preset) => {
                  const isSelected = selectedPreset === preset.username;
                  return (
                    <div
                      key={preset.username}
                      className={`auth-preset-card ${isSelected ? 'selected' : ''}`}
                      style={{
                        '--preset-color': preset.badgeColor,
                        '--preset-bg': preset.badgeBg,
                        '--preset-border': preset.badgeBorder,
                      }}
                      onClick={() => handleSelectPreset(preset, false)}
                    >
                      <div className="auth-preset-top">
                        <span className="auth-preset-icon">{preset.icon}</span>
                        <span className="auth-role-pill">{preset.role}</span>
                      </div>
                      <div className="auth-preset-name">{preset.label}</div>
                      <div className="auth-preset-dept">{preset.department}</div>
                      
                      <div className="auth-preset-footer">
                        <span className="auth-creds-preview mono">{preset.username}</span>
                        <button
                          type="button"
                          className="auth-quick-login-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelectPreset(preset, true);
                          }}
                          disabled={loading}
                          title={`Log in instantly as ${preset.role}`}
                        >
                          Sign In →
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── Form Section ── */}
            <form className="auth-form-wrapper" onSubmit={handleSubmit}>
              <div className="auth-form-header-line">
                <span>Or Enter Credentials Manually</span>
              </div>

              {error && (
                <div className="auth-alert-box error" role="alert">
                  <span className="auth-alert-icon">⚠️</span>
                  <div className="auth-alert-msg">{error}</div>
                </div>
              )}

              <div className="auth-input-group">
                <label className="auth-field-label" htmlFor="auth-username">
                  <span>Username</span>
                  <span className="auth-field-hint">e.g. police_sharma, admin, planner_verma</span>
                </label>
                <div className="auth-input-container">
                  <span className="auth-input-icon">👤</span>
                  <input
                    id="auth-username"
                    type="text"
                    className="auth-text-input"
                    value={username}
                    onChange={(e) => {
                      setUsername(e.target.value);
                      setSelectedPreset('');
                    }}
                    placeholder="Enter your username"
                    autoComplete="username"
                    required
                  />
                </div>
              </div>

              <div className="auth-input-group">
                <div className="auth-label-row">
                  <label className="auth-field-label" htmlFor="auth-password">
                    Password
                  </label>
                  <button
                    type="button"
                    className="auth-toggle-pwd-btn"
                    onClick={() => setShowPassword(!showPassword)}
                    tabIndex={-1}
                  >
                    {showPassword ? '🙈 Hide' : '👁️ Show'}
                  </button>
                </div>
                <div className="auth-input-container">
                  <span className="auth-input-icon">🔒</span>
                  <input
                    id="auth-password"
                    type={showPassword ? 'text' : 'password'}
                    className="auth-text-input"
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setSelectedPreset('');
                    }}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                className="auth-primary-submit-btn"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="auth-spinner" />
                    <span>Verifying JWT Credentials...</span>
                  </>
                ) : (
                  <>
                    <span>Sign In to ANPR Platform</span>
                    <span className="auth-btn-arrow">→</span>
                  </>
                )}
              </button>
            </form>

            {/* ── Security & Compliance Footer ── */}
            <div className="auth-security-notice">
              <span className="auth-lock-micro">🔒</span>
              <span>
                <strong>Statutory Compliance Notice:</strong> All login events, plate lookups, and identity queries are permanently recorded in the immutable audit log.
              </span>
            </div>
          </div>
        ) : (
          /* ── Role & Permissions Matrix View ── */
          <div className="auth-matrix-view">
            <div className="auth-matrix-intro">
              The Delhi ANPR & Trajectory Tracking Platform enforces strict <strong>Role-Based Access Control (RBAC)</strong> to comply with statutory data privacy standards.
            </div>

            <div className="auth-matrix-table-card">
              <table className="auth-matrix-grid">
                <thead>
                  <tr>
                    <th>Capability Area</th>
                    <th className="th-admin">👑 Admin</th>
                    <th className="th-police">👮‍♂️ Traffic Police</th>
                    <th className="th-planner">📊 City Planner</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <div className="cap-title">Vehicle Trajectory Reconstruction</div>
                      <div className="cap-desc">Fuzzy plate search & trip timeline</div>
                    </td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                  </tr>
                  <tr>
                    <td>
                      <div className="cap-title">Private Citizen Identity Vault</div>
                      <div className="cap-desc">Owner address, phone & vehicle registration</div>
                    </td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-deny">Protected (403)</span></td>
                  </tr>
                  <tr>
                    <td>
                      <div className="cap-title">Alert Center & Stolen Blacklist</div>
                      <div className="cap-desc">Wanted vehicles & hotlist resolution</div>
                    </td>
                    <td><span className="badge-grant full">CRUD & Resolve</span></td>
                    <td><span className="badge-grant full">Resolve Alerts</span></td>
                    <td><span className="badge-deny">View Only / Blocked</span></td>
                  </tr>
                  <tr>
                    <td>
                      <div className="cap-title">Live Traffic & Congestion Heatmap</div>
                      <div className="cap-desc">Delhi NCR real-time node map</div>
                    </td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                  </tr>
                  <tr>
                    <td>
                      <div className="cap-title">Video Upload ANPR Lab</div>
                      <div className="cap-desc">Multipart upload with &ge;10s OCR validation</div>
                    </td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-deny">Blocked</span></td>
                  </tr>
                  <tr>
                    <td>
                      <div className="cap-title">City Traffic Analytics</div>
                      <div className="cap-desc">Corridor speeds, peak hours, OD matrix</div>
                    </td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-grant full">Full Access</span></td>
                  </tr>
                  <tr>
                    <td>
                      <div className="cap-title">Statutory Audit Logs</div>
                      <div className="cap-desc">Immutable officer activity & query tracking</div>
                    </td>
                    <td><span className="badge-grant full">Full Access</span></td>
                    <td><span className="badge-deny">Blocked</span></td>
                    <td><span className="badge-deny">Blocked</span></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="auth-matrix-back-bar">
              <button 
                type="button" 
                className="btn btn-primary"
                onClick={() => setActiveView('login')}
              >
                ← Back to Sign In
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
