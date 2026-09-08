import { useState } from 'react';
import { fmtDateTime, confClass } from '../utils';

export default function AlertsPanel({ alerts, onInspect, onSelectPlate, onOpenEnforcement }) {
  const [sevFilter, setSevFilter] = useState('ALL');

  if (!alerts) {
    return (
      <div className="card dev-panel">
        <div className="card-header">
          <div className="card-header-left">
            <span className="dev-tag">FEATURE 3: POLICE ALERTS</span>
            <span className="card-title">Flagged & Stolen Vehicle Watchlist</span>
          </div>
        </div>
        <div className="card-body">
          <div className="student-empty-state">
            <div className="empty-icon-large">🚨</div>
            <div className="empty-title">Waiting for Simulation</div>
            <div className="empty-subtitle">Click "Run Simulation" at the top to scan for wanted cars in Delhi.</div>
          </div>
        </div>
      </div>
    );
  }

  const highCount = alerts.filter(a => a.severity === 'HIGH').length;
  const medCount  = alerts.filter(a => a.severity === 'MEDIUM').length;

  const filtered = alerts.filter(a => {
    if (sevFilter === 'HIGH') return a.severity === 'HIGH';
    if (sevFilter === 'MEDIUM') return a.severity === 'MEDIUM';
    return true;
  });

  return (
    <div className="card dev-panel">
      <div className="card-header">
        <div className="card-header-left">
          <span className="dev-tag">FEATURE 3: AUTOMATED POLICE ALERTS</span>
          <span className="card-title">Stolen & Wanted Vehicle Sighting Alerts</span>
        </div>
        <div className="card-header-right">
          <div className="badge-group">
            <button 
              className={`filter-pill ${sevFilter === 'ALL' ? 'active' : ''}`}
              onClick={() => setSevFilter('ALL')}
            >
              All Alerts ({alerts.length})
            </button>
            <button 
              className={`filter-pill pill-red ${sevFilter === 'HIGH' ? 'active' : ''}`}
              onClick={() => setSevFilter('HIGH')}
            >
              🔴 High ({highCount})
            </button>
            <button 
              className={`filter-pill pill-amber ${sevFilter === 'MEDIUM' ? 'active' : ''}`}
              onClick={() => setSevFilter('MEDIUM')}
            >
              🟡 Medium / Fuzzy ({medCount})
            </button>
          </div>
          <button 
            className="btn-dev-sm" 
            onClick={() => onInspect({ title: 'Alerts Batch Payload', data: alerts })}
          >
            Raw JSON
          </button>
        </div>
      </div>

      <div className="card-body" style={{ padding: '12px' }}>
        <p className="student-helper-text">
          💡 <strong>Student Note:</strong> Notice how the AI caught vehicles even when the camera made a typo (marked <code>FUZZY MATCH</code>)! A naive exact match would have completely missed these stolen cars.
        </p>

        {alerts.length === 0 ? (
          <div className="student-empty-state">
            <div className="empty-icon-large">✅</div>
            <div className="empty-title">All Clear! No Flagged Vehicles</div>
            <div className="empty-subtitle">No vehicles in this batch matched the police stolen watchlist.</div>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table dev-grid">
              <thead>
                <tr>
                  <th>ALERT LEVEL</th>
                  <th>CAMERA SCAN</th>
                  <th>WANTED PLATE</th>
                  <th>SIGHTING LOCATION</th>
                  <th>VEHICLE TYPE</th>
                  <th>OCR ACCURACY</th>
                  <th>TIMESTAMP</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(alert => {
                  const isFuzzy = alert.plate_raw !== alert.matched_wanted_plate;
                  return (
                    <tr key={alert.detection_id} className={`dev-row ${alert.severity === 'HIGH' ? 'row-alert-high' : 'row-alert-med'}`}>
                      <td>
                        <span className={`status-badge ${alert.severity === 'HIGH' ? 'badge-danger' : 'badge-warning'}`}>
                          {alert.severity === 'HIGH' ? '🔴 HIGH PRIORITY' : '🟡 MEDIUM PRIORITY'}
                        </span>
                      </td>
                      <td>
                        <span className="mono dev-bold highlight-cyan">{alert.plate_raw}</span>
                        {isFuzzy && (
                          <span className="fuzzy-match-tag" title="Matched using Levenshtein edit distance <= 2 despite OCR typo">
                            ⚡ AI Fuzzy Match
                          </span>
                        )}
                      </td>
                      <td className="mono dev-bold">{alert.matched_wanted_plate}</td>
                      <td>
                        <strong>{alert.camera_name.split('—')[0].trim()}</strong> <span className="mono text-muted" style={{ fontSize: 10 }}>({alert.camera_id})</span>
                      </td>
                      <td>{alert.vehicle_type}</td>
                      <td className="mono">
                        <span className={`conf-badge ${confClass(alert.confidence)}`}>
                          {(alert.confidence * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="mono text-muted">{fmtDateTime(alert.timestamp)}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="btn-dev-xs highlight-cyan-btn"
                            title="See all cameras this wanted car drove through"
                            onClick={() => onSelectPlate(alert.plate_raw)}
                          >
                            Track Journey ➔
                          </button>
                          <button
                            className="btn-dev-xs btn-enforcement-action"
                            title="View registered owner in the secure police vault"
                            onClick={() => onOpenEnforcement(alert.matched_wanted_plate)}
                          >
                            🔒 Owner Record
                          </button>
                        </div>
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
