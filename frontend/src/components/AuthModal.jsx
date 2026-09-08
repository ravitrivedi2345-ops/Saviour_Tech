import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

const ROLE_COLORS = {
  Admin: { bg: 'rgba(239, 68, 68, 0.15)', border: '#ef4444', text: '#fca5a5' },
  'Traffic Police': { bg: 'rgba(59, 130, 246, 0.15)', border: '#3b82f6', text: '#93c5fd' },
  'City Planner': { bg: 'rgba(16, 185, 129, 0.15)', border: '#10b981', text: '#6ee7b7' },
};

export default function AuthModal({ onClose, required = false }) {
  const { login, loading, demoAccounts } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await login(username.trim(), password);
      if (onClose) onClose();
    } catch (err) {
      setError(err.message || 'Login failed');
    }
  };

  const handleDemoLogin = async (account) => {
    setUsername(account.username);
    setPassword(account.password);
    setError('');
    try {
      await login(account.username, account.password);
      if (onClose) onClose();
    } catch (err) {
      setError(err.message || 'Login failed');
    }
  };

  return (
    <div className="modal-backdrop" onClick={required ? undefined : onClose}>
      <div className="modal-content auth-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header auth-modal-header">
          <div className="modal-title-wrap">
            <span className="auth-lock-icon">🔐</span>
            <div>
              <div className="modal-title">Secure Access — Delhi ANPR Platform</div>
              <div className="auth-subtitle">JWT authentication with role-based access control</div>
            </div>
          </div>
          {!required && (
            <button className="btn-dev btn-close" onClick={onClose}>Close [X]</button>
          )}
        </div>

        <div className="modal-body">
          <div className="auth-info-banner">
            All login events and plate searches are permanently recorded in the audit log for statutory compliance.
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="auth-field">
              <label>USERNAME</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="e.g. police_sharma"
                autoComplete="username"
                required
              />
            </div>
            <div className="auth-field">
              <label>PASSWORD</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Enter password"
                autoComplete="current-password"
                required
              />
            </div>

            {error && <div className="auth-error">{error}</div>}

            <button type="submit" className="btn btn-primary auth-submit-btn" disabled={loading}>
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>

          <div className="auth-demo-section">
            <div className="auth-demo-title">One-Click Demo Credentials</div>
            <div className="auth-demo-grid">
              {demoAccounts.map(account => {
                const colors = ROLE_COLORS[account.role] || ROLE_COLORS.Admin;
                return (
                  <button
                    key={account.username}
                    type="button"
                    className="auth-demo-card"
                    style={{ background: colors.bg, borderColor: colors.border }}
                    onClick={() => handleDemoLogin(account)}
                    disabled={loading}
                  >
                    <span className="auth-demo-role" style={{ color: colors.text }}>{account.label}</span>
                    <span className="auth-demo-user mono">{account.username}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="auth-role-matrix">
            <div className="auth-matrix-title">Access Matrix</div>
            <table className="auth-matrix-table">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Admin</th>
                  <th>Traffic Police</th>
                  <th>City Planner</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Trajectory & Plate Search</td><td>✓</td><td>✓</td><td>✓</td></tr>
                <tr><td>Owner Identity Vault</td><td>✓</td><td>✓</td><td>✗</td></tr>
                <tr><td>Alert Disposition</td><td>✓</td><td>✓</td><td>✗</td></tr>
                <tr><td>Video ANPR Upload</td><td>✓</td><td>✓</td><td>✗</td></tr>
                <tr><td>Live Traffic Map</td><td>✓</td><td>✓</td><td>✓</td></tr>
                <tr><td>City Analytics</td><td>✓</td><td>✓</td><td>✓</td></tr>
                <tr><td>Audit Logs</td><td>✓</td><td>✗</td><td>✗</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
