import { useState } from 'react';

export default function CameraTopologyPanel({ cameras, onInspect }) {
  const [selectedCam, setSelectedCam] = useState(null);
  const cameraList = cameras ? Object.entries(cameras) : [];

  return (
    <div className="card dev-panel">
      <div className="card-header">
        <div className="card-header-left">
          <span className="dev-tag">SENSOR NETWORK TOPOLOGY</span>
          <span className="card-title">Delhi NCR Traffic Camera Network (9 Stations)</span>
        </div>
        <div className="card-header-right">
          <span className="card-badge dev-badge">{cameraList.length} CAMERAS ONLINE</span>
          <button 
            className="btn-dev-sm" 
            onClick={() => onInspect({ title: 'Camera Network Matrix', data: cameras })}
          >
            Matrix JSON
          </button>
        </div>
      </div>

      <div className="card-body">
        <p className="student-helper-text">
          💡 <strong>Student Context:</strong> These 9 cameras simulate smart ANPR poles installed across major intersections in the Delhi National Capital Region (from CP to Noida & Cyber City Gurgaon). Click on any camera card to highlight it.
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
                  <th>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {cameraList.map(([id, cam]) => (
                  <tr 
                    key={id} 
                    className={`dev-row ${selectedCam === id ? 'row-selected' : ''}`}
                    onClick={() => setSelectedCam(id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="mono bold highlight-cyan">{id}</td>
                    <td><strong>{cam.name.split('—')[0].trim()}</strong></td>
                    <td>
                      <span className="zone-tag">{cam.zone}</span>
                    </td>
                    <td className="mono text-muted" style={{ fontSize: 11 }}>
                      {cam.lat.toFixed(4)}°N, {cam.lon.toFixed(4)}°E
                    </td>
                    <td>
                      <button 
                        className="btn-dev-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          onInspect({ title: `Node Telemetry: ${id}`, data: { id, ...cam } });
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
              <span className="schematic-status">● 9 SENSORS OPERATIONAL</span>
            </div>
            <div className="schematic-nodes">
              {cameraList.map(([id, cam]) => (
                <div 
                  key={id} 
                  className={`schematic-node-card ${selectedCam === id ? 'node-active' : ''}`}
                  onClick={() => setSelectedCam(id)}
                >
                  <div className="node-id-bar">
                    <span className="mono bold">{id}</span>
                    <span className="node-status-dot" />
                  </div>
                  <div className="node-name">{cam.name.split('—')[0].trim()}</div>
                  <div className="node-zone">{cam.zone}</div>
                  <div className="node-coords">{cam.lat.toFixed(4)}°N, {cam.lon.toFixed(4)}°E</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
