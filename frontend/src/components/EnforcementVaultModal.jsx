import { useState } from 'react';
import { getIdentity } from '../api';

export default function EnforcementVaultModal({ initialPlate, onClose }) {
  const [plate, setPlate] = useState(initialPlate || 'DL01AB1234');
  const [reason, setReason] = useState('CRIME_INVESTIGATION_FIR_2026_09');
  const [badgeId, setBadgeId] = useState('LEO-DELHI-88219');
  const [identityData, setIdentityData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLookup = async (e) => {
    if (e) e.preventDefault();
    if (!plate.trim()) return;
    setLoading(true);
    setError('');
    setIdentityData(null);

    try {
      const data = await getIdentity(plate.trim());
      setIdentityData(data);
    } catch (err) {
      setError(err.message || 'Identity lookup failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content enforcement-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header enforcement-header">
          <div className="modal-title-wrap">
            <span className="enforcement-badge-icon">🛡️</span>
            <div>
              <div className="modal-title enforcement-title">
                Police View: Citizen Vehicle Identity Vault
              </div>
              <div className="enforcement-subtitle">
                Air-gapped database for vehicle registration & owner records (Endpoint: /enforcement/identity/{'{plate}'})
              </div>
            </div>
          </div>
          <button className="btn-dev btn-close" onClick={onClose}>
            Close [X]
          </button>
        </div>

        <div className="enforcement-warning-banner">
          <div className="warning-prefix">🎓 Student Privacy Concept (Privacy by Design):</div>
          Traffic engineers who analyze traffic jams <strong>never see citizen names or addresses</strong>.
          Personal data is completely isolated in this police subsystem. To look up an owner, an officer must provide their Badge ID and an authorized Case / FIR reason.
        </div>

        <div className="modal-body">
          <form className="enforcement-auth-bar" onSubmit={handleLookup}>
            <div className="auth-field">
              <label>OFFICER BADGE ID</label>
              <input
                type="text"
                className="dev-input mono"
                value={badgeId}
                onChange={e => setBadgeId(e.target.value)}
                required
              />
            </div>
            <div className="auth-field">
              <label>POLICE CASE / FIR NUMBER</label>
              <input
                type="text"
                className="dev-input mono"
                value={reason}
                onChange={e => setReason(e.target.value)}
                required
              />
            </div>
            <div className="auth-field">
              <label>PLATE TO DE-ANONYMIZE</label>
              <input
                type="text"
                className="dev-input mono highlight-cyan"
                placeholder="e.g. DL01AB1234"
                value={plate}
                onChange={e => setPlate(e.target.value.toUpperCase())}
                required
              />
            </div>
            <div className="auth-action">
              <button 
                type="submit" 
                className="btn btn-danger-action"
                disabled={loading}
              >
                {loading ? 'Querying Police DB...' : '🔓 Fetch Owner Record'}
              </button>
            </div>
          </form>

          {/* Quick preset plate test buttons */}
          <div className="quick-plates-bar" style={{ marginBottom: 12 }}>
            <span className="quick-label">Try Stolen / Wanted Plates:</span>
            {['DL01AB1234', 'MH12XY5678', 'UP32CD9999', 'KA05EF2222', 'RJ14GH7777'].map(p => (
              <button
                key={p}
                type="button"
                className="btn-dev-xs mono"
                onClick={() => { setPlate(p); }}
              >
                {p}
              </button>
            ))}
          </div>

          {error && (
            <div className="dev-error-box">
              <span className="error-title">Lookup Notice:</span> {error}
            </div>
          )}

          {identityData && (
            <div className="identity-record-view">
              <div className="record-header">
                <div>
                  <span className="record-plate mono">{identityData.plate}</span>
                  {identityData.is_wanted && (
                    <span className="status-badge badge-danger" style={{ marginLeft: 12 }}>
                      🚨 ACTIVE POLICE WANTED / STOLEN FLAG
                    </span>
                  )}
                </div>
                <span className="audit-stamp mono">
                  Logged by {badgeId} on {new Date().toLocaleTimeString()}
                </span>
              </div>

              <div className="record-grid">
                <div className="record-cell">
                  <span className="cell-label">REGISTERED OWNER</span>
                  <span className="cell-val bold">{identityData.identity.owner_name}</span>
                </div>
                <div className="record-cell">
                  <span className="cell-label">VEHICLE MODEL</span>
                  <span className="cell-val mono">{identityData.identity.vehicle_model}</span>
                </div>
                <div className="record-cell">
                  <span className="cell-label">RTO DISTRICT OFFICE</span>
                  <span className="cell-val">{identityData.identity.rto_district}</span>
                </div>
                <div className="record-cell">
                  <span className="cell-label">YEAR REGISTERED</span>
                  <span className="cell-val mono">{identityData.identity.registered_year}</span>
                </div>
                <div className="record-cell">
                  <span className="cell-label">LEGAL STATUS</span>
                  <span className={`cell-val bold ${identityData.identity.status.includes('Stolen') || identityData.identity.status.includes('Wanted') ? 'text-red' : 'text-green'}`}>
                    {identityData.identity.status}
                  </span>
                </div>
                <div className="record-cell span-2">
                  <span className="cell-label">POLICE DISPATCH ACTION</span>
                  <span className="cell-val text-red mono bold">{identityData.identity.action}</span>
                </div>
              </div>

              <div className="arch-isolation-explainer">
                <div className="explainer-title">How Our Code Enforces This Separation:</div>
                <div className="explainer-body">
                  In our backend code, <code>identity.py</code> is ONLY imported inside the <code>/enforcement/identity/{'{plate}'}</code> route.
                  The public trajectory matcher, camera graph, and congestion analytics have <strong>zero imports or access to citizen identities</strong>.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
