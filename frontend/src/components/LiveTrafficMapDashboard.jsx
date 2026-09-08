import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { createLiveTrafficWebSocket } from '../api';

const DELHI_CENTER = [28.6139, 77.2090];

export default function LiveTrafficMapDashboard() {
  const mapElement = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef(new Map());
  const heatmapRef = useRef(new Map());
  const [connected, setConnected] = useState(false);
  const [cameraStats, setCameraStats] = useState({});
  const [detections, setDetections] = useState([]);
  const [heatmap, setHeatmap] = useState([]);

  function updateCameraMarker(camera) {
    const map = mapRef.current;
    if (!map || !camera?.lat || !(camera.lng || camera.lon)) return;
    const lng = camera.lng || camera.lon;
    const marker = markersRef.current.get(camera.camera_id) || L.circleMarker([camera.lat, lng], {
      radius: 8,
      weight: 2,
      color: '#f4b942',
      fillColor: '#f4b942',
      fillOpacity: 0.9,
    }).addTo(map);
    marker.bindTooltip(camera.name || camera.camera_id);
    marker.setLatLng([camera.lat, lng]);
    markersRef.current.set(camera.camera_id, marker);
  }

  function updateHeatCircle(point) {
    const map = mapRef.current;
    if (!map || !point?.lat || !(point.lng || point.lon)) return;
    const lng = point.lng || point.lon;
    const intensity = point.intensity ?? point.congestion_score ?? 0.2;
    const circle = heatmapRef.current.get(point.camera_id) || L.circle([point.lat, lng], {
      stroke: false,
      fillOpacity: 0.18,
    }).addTo(map);
    circle.setLatLng([point.lat, lng]);
    circle.setRadius(250 + intensity * 850);
    circle.setStyle({ fillColor: intensity > 0.65 ? '#e45756' : intensity > 0.4 ? '#f4b942' : '#2fbf71' });
    heatmapRef.current.set(point.camera_id, circle);
  }

  useEffect(() => {
    if (!mapElement.current || mapRef.current) return undefined;
    const map = L.map(mapElement.current, { zoomControl: true }).setView(DELHI_CENTER, 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const socket = createLiveTrafficWebSocket(
      (message) => {
        if (message.type === 'SNAPSHOT') {
          setCameraStats(message.camera_stats || {});
          setHeatmap(Object.values(message.camera_stats || {}).map((stat, index) => ({ ...stat, index })));
          message.camera_nodes?.forEach(updateCameraMarker);
        }
        if (message.type === 'LIVE_DETECTION') {
          setDetections((current) => [message.detection, ...current].slice(0, 12));
          updateCameraMarker(message.detection);
        }
        if (message.type === 'CONGESTION_HEATMAP_UPDATE') {
          setCameraStats(message.camera_stats || {});
          setHeatmap(message.heatmap || []);
        }
      },
      () => setConnected(true),
      () => setConnected(false),
      () => setConnected(false),
    );
    return () => socket.close();
  }, []);

  useEffect(() => {
    heatmap.forEach((point) => {
      const node = point.camera_id ? point : null;
      if (node) updateHeatCircle(node);
    });
  }, [heatmap]);

  const stats = Object.values(cameraStats);
  const averageCongestion = stats.length ? stats.reduce((sum, stat) => sum + (stat.congestion_score || 0), 0) / stats.length : 0;

  return (
    <section className="live-traffic-dashboard">
      <div className="extension-heading">
        <div>
          <span className="eyebrow">REAL-TIME OPERATIONS</span>
          <h2>Delhi NCR live traffic</h2>
        </div>
        <span className={`connection-pill ${connected ? 'online' : ''}`}><span />{connected ? 'STREAM CONNECTED' : 'CONNECTING'}</span>
      </div>
      <div className="live-traffic-kpis">
        <div><span>CAMERAS REPORTING</span><strong>{stats.length}</strong></div>
        <div><span>AVG CONGESTION</span><strong>{Math.round(averageCongestion * 100)}%</strong></div>
        <div><span>RECENT DETECTIONS</span><strong>{detections.length}</strong></div>
      </div>
      <div className="live-traffic-layout">
        <div ref={mapElement} className="live-traffic-map" />
        <aside className="live-detection-feed">
          <div className="feed-title"><span>INCOMING DETECTIONS</span><span className="mono">LIVE</span></div>
          {detections.length === 0 && <p className="empty-feed">Waiting for camera events...</p>}
          {detections.map((detection, index) => (
            <div className="live-detection-row" key={`${detection.camera_id}-${detection.plate_number}-${index}`}>
              <div><strong className="mono">{detection.plate_number}</strong><span>{detection.camera_id} · {detection.corridor}</span></div>
              <span className={detection.is_flagged ? 'flagged-badge' : 'confidence-badge'}>{detection.is_flagged ? 'FLAGGED' : `${Math.round(detection.confidence * 100)}%`}</span>
            </div>
          ))}
        </aside>
      </div>
    </section>
  );
}
