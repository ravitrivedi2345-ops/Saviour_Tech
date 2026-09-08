import { useState } from 'react';

export default function CongestionTable({ congestion, onInspect }) {
  const [sortKey, setSortKey] = useState('total');
  const [sortAsc, setSortAsc] = useState(false);

  if (!congestion) {
    return (
      <div className="card dev-panel">
        <div className="card-header">
          <div className="card-header-left">
            <span className="dev-tag">ANALYTICS: TRAFFIC JAM DETECTOR</span>
            <span className="card-title">City Congestion by Camera Location</span>
          </div>
        </div>
        <div className="card-body">
          <div className="student-empty-state">
            <div className="empty-icon-large">🚦</div>
            <div className="empty-title">Waiting for Simulation</div>
            <div className="empty-subtitle">Click "Run Simulation" at the top to measure traffic density across Delhi.</div>
          </div>
        </div>
      </div>
    );
  }

  const rows = Object.entries(congestion)
    .map(([id, data]) => ({ id, ...data }));

  rows.sort((a, b) => {
    let valA = sortKey === 'total' ? a.total : sortKey === 'peak' ? a.peak_count : a.zone;
    let valB = sortKey === 'total' ? b.total : sortKey === 'peak' ? b.peak_count : b.zone;
    if (valA < valB) return sortAsc ? -1 : 1;
    if (valA > valB) return sortAsc ? 1 : -1;
    return 0;
  });

  const maxTotal = Math.max(...rows.map(r => r.total), 1);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  return (
    <div className="card dev-panel">
      <div className="card-header">
        <div className="card-header-left">
          <span className="dev-tag">URBAN TRAFFIC ANALYTICS</span>
          <span className="card-title">Traffic Volume & Rush Hour by Delhi Camera</span>
        </div>
        <div className="card-header-right">
          <span className="card-badge dev-badge">{rows.length} CAMERAS MONITORED</span>
          <button 
            className="btn-dev-sm" 
            onClick={() => onInspect({ title: 'GET /analytics/congestion', data: congestion })}
          >
            Raw JSON
          </button>
        </div>
      </div>

      <div className="card-body" style={{ padding: '12px' }}>
        <p className="student-helper-text">
          💡 <strong>Student Tip:</strong> This table tells urban planners where traffic bottlenecks form. Cameras with red load bars are seeing the highest number of vehicles. Click any column header to sort!
        </p>

        <div className="table-wrapper">
          <table className="data-table dev-grid">
            <thead>
              <tr>
                <th onClick={() => handleSort('id')} style={{ cursor: 'pointer' }}>
                  CAMERA & LOCATION {sortKey === 'id' ? (sortAsc ? '▲' : '▼') : ''}
                </th>
                <th onClick={() => handleSort('zone')} style={{ cursor: 'pointer' }}>
                  DELHI ZONE {sortKey === 'zone' ? (sortAsc ? '▲' : '▼') : ''}
                </th>
                <th onClick={() => handleSort('total')} style={{ textAlign: 'right', cursor: 'pointer' }}>
                  TOTAL VEHICLES {sortKey === 'total' ? (sortAsc ? '▲' : '▼') : ''}
                </th>
                <th className="cong-bar-cell">TRAFFIC LOAD BAR</th>
                <th>RUSHEST HOUR</th>
                <th onClick={() => handleSort('peak')} style={{ textAlign: 'right', cursor: 'pointer' }}>
                  PEAK VOLUME {sortKey === 'peak' ? (sortAsc ? '▲' : '▼') : ''}
                </th>
                <th>INSPECT</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const pct = (row.total / maxTotal) * 100;
                const isHigh = pct > 65;
                const isMed = pct > 40;
                return (
                  <tr key={row.id} className="dev-row">
                    <td>
                      <div className="bold">{row.camera_name.split('—')[0].trim()}</div>
                      <div className="text-muted mono" style={{ fontSize: 11 }}>
                        {row.id} · {row.camera_name.split('—')[1] || ''}
                      </div>
                    </td>
                    <td>
                      <span className="zone-tag">{row.zone}</span>
                    </td>
                    <td style={{ textAlign: 'right' }} className="mono bold highlight-cyan">
                      {row.total} cars
                    </td>
                    <td className="cong-bar-cell">
                      <div className="cong-bar-wrap">
                        <div
                          className={`cong-bar-fill ${isHigh ? 'load-critical' : isMed ? 'load-elevated' : 'load-nominal'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </td>
                    <td className="mono text-muted">
                      🕒 {row.peak_hour}
                    </td>
                    <td style={{ textAlign: 'right' }} className="mono text-amber bold">
                      {row.peak_count} / hour
                    </td>
                    <td>
                      <button
                        className="btn-dev-xs"
                        onClick={() => onInspect({ title: `Node Influx [${row.id}]`, data: row })}
                      >
                        Hourly Data
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
