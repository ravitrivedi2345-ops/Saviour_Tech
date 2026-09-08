import { useState, useEffect } from 'react';
import { subscribeLogs, requestLogs } from '../api';

export default function ApiConsoleDrawer({ onInspect }) {
  const [logs, setLogs] = useState([...requestLogs]);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    return subscribeLogs(updated => {
      setLogs(updated);
    });
  }, []);

  return (
    <div className={`dev-console-drawer ${isOpen ? 'drawer-open' : 'drawer-collapsed'}`}>
      <div className="drawer-handle" onClick={() => setIsOpen(!isOpen)}>
        <div className="drawer-handle-left">
          <span className="console-indicator" />
          <span className="console-title">DEVELOPER TELEMETRY & NETWORK CONSOLE</span>
          <span className="console-badge">{logs.length} EVENTS</span>
          {logs[0] && (
            <span className="console-last-req mono">
              LAST: [{logs[0].method}] {logs[0].url} · {logs[0].duration}ms · {logs[0].status}
            </span>
          )}
        </div>
        <div className="drawer-handle-right">
          <button className="btn-dev-toggle">
            {isOpen ? '▼ COLLAPSE' : '▲ EXPAND TRACE LOG'}
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="drawer-content">
          <div className="table-wrapper">
            <table className="data-table dev-grid console-table">
              <thead>
                <tr>
                  <th>TIMESTAMP</th>
                  <th>METHOD</th>
                  <th>REST ENDPOINT</th>
                  <th>DURATION (LATENCY)</th>
                  <th>HTTP STATUS</th>
                  <th>DIAGNOSTIC</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="text-center text-muted">No network traces captured yet.</td>
                  </tr>
                ) : (
                  logs.map(log => (
                    <tr key={log.id} className="dev-row">
                      <td className="mono text-muted">{log.timestamp}</td>
                      <td>
                        <span className={`method-badge ${log.method.toLowerCase()}`}>
                          {log.method}
                        </span>
                      </td>
                      <td className="mono dev-bold highlight-cyan">{log.url}</td>
                      <td className="mono">{log.duration} ms</td>
                      <td>
                        <span className={`status-badge ${log.ok ? 'badge-ok' : 'badge-danger'}`}>
                          {log.status}
                        </span>
                      </td>
                      <td>
                        {log.error ? (
                          <span className="text-red mono">{log.error}</span>
                        ) : (
                          <span className="text-green mono">EXEC_COMPLETED</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
