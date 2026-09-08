import { useEffect, useRef } from 'react';
import L from 'leaflet';

export default function CityTrafficMap({
  cameras = [],
  corridors = [],
  showHeatmap = true,
  showCorridors = true,
  onSelectNode = () => {},
}) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const layerGroupRef = useRef(null);

  // Initialize map once
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: [28.6139, 77.2090],
      zoom: 11,
      zoomControl: true,
    });

    // CartoDB Voyager map tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    const layerGroup = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;
    layerGroupRef.current = layerGroup;

    setTimeout(() => map.invalidateSize(), 200);

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update map layers on data change
  useEffect(() => {
    const map = mapInstanceRef.current;
    const layerGroup = layerGroupRef.current;
    if (!map || !layerGroup) return;

    layerGroup.clearLayers();

    // 1. Draw Road Corridors (Speed / Congestion color-coded)
    if (showCorridors && corridors && corridors.length > 0) {
      corridors.forEach(c => {
        if (!c.coordinates || c.coordinates.length < 2) return;

        const polyline = L.polyline(c.coordinates, {
          color: c.status_color || '#10b981',
          weight: 5,
          opacity: 0.85,
          lineCap: 'round',
          lineJoin: 'round',
        });

        const statusBadge = c.speed_status === 'FREE_FLOW'
          ? '<span style="color:#059669;font-weight:bold;">🟢 Free Flow</span>'
          : c.speed_status === 'MODERATE'
          ? '<span style="color:#d97706;font-weight:bold;">🟡 Moderate Congestion</span>'
          : '<span style="color:#dc2626;font-weight:bold;">🔴 Heavy Congestion</span>';

        const popupHtml = `
          <div class="map-popup-card">
            <div class="popup-title">
              <strong>${c.name}</strong>
            </div>
            <div class="popup-sub mono text-muted">${c.segment_id} &bull; ${c.zone} &bull; ${c.distance_km} km</div>
            <div class="popup-row">
              <span>Observed Speed:</span>
              <strong style="color:${c.status_color}; font-size:13px;">${c.avg_speed_kmph} km/h</strong>
            </div>
            <div class="popup-row">
              <span>Corridor Speed Limit:</span>
              <span>${c.speed_limit_kmph} km/h</span>
            </div>
            <div class="popup-row">
              <span>Traffic Condition:</span>
              <span>${statusBadge}</span>
            </div>
            <div class="popup-row">
              <span>Traffic Volume:</span>
              <strong class="mono">${c.volume ? c.volume.toLocaleString() : '—'} vehicles</strong>
            </div>
          </div>
        `;

        polyline.bindPopup(popupHtml, { maxWidth: 300 });
        polyline.bindTooltip(`<strong>${c.name}</strong>: ${c.avg_speed_kmph} km/h (${c.speed_status})`, { sticky: true });
        layerGroup.addLayer(polyline);
      });
    }

    // 2. Draw Heatmap Radiance Circles (Traffic Density)
    if (showHeatmap && cameras && cameras.length > 0) {
      cameras.forEach(cam => {
        if (cam.is_offline) return; // Skip heat for offline cameras

        const vol = cam.vehicle_volume || 0;
        const radius = Math.max(18, Math.min(55, Math.round(Math.sqrt(vol) * 0.5)));
        const heatColor = vol > 12000 ? '#ef4444' : vol > 6000 ? '#f59e0b' : '#06b6d4';

        const circle = L.circleMarker([cam.lat, cam.lon], {
          radius: radius,
          fillColor: heatColor,
          fillOpacity: 0.25,
          color: heatColor,
          weight: 1.5,
          opacity: 0.5,
        });
        layerGroup.addLayer(circle);
      });
    }

    // 3. Draw Camera Nodes Markers (Distinguishing Online from Offline)
    if (cameras && cameras.length > 0) {
      cameras.forEach(cam => {
        const isOffline = cam.is_offline;
        const iconHtml = isOffline
          ? `<div class="cam-marker-box marker-offline" title="Sensor Offline: Data Incomplete">
               <span>⚠️</span>
             </div>`
          : `<div class="cam-marker-box marker-online" title="${cam.name}: ${cam.vehicle_volume?.toLocaleString()} veh">
               <span>📷</span>
             </div>`;

        const customIcon = L.divIcon({
          html: iconHtml,
          className: 'custom-cam-marker-div',
          iconSize: [28, 28],
          iconAnchor: [14, 14],
          popupAnchor: [0, -14],
        });

        const marker = L.marker([cam.lat, cam.lon], { icon: customIcon });

        const popupContent = isOffline ? `
          <div class="map-popup-card">
            <div class="popup-title" style="color:#dc2626;">
              <strong>⚠️ SENSOR OFFLINE (OUTAGE)</strong>
            </div>
            <div class="popup-sub mono text-muted">${cam.camera_id} &bull; ${cam.name} &bull; ${cam.zone}</div>
            <div style="background:#fee2e2; border-left:3px solid #dc2626; padding:8px; border-radius:4px; font-size:11px; margin:8px 0; color:#991b1b;">
              <strong>CRITICAL SENSOR NOTICE:</strong><br/>
              This camera experienced a hardware/telemetry outage. Sighting data is incomplete for this time window.
              <br/><br/>
              <em>⚠️ Note: This does NOT indicate zero traffic on this road segment.</em>
            </div>
            <div class="popup-row">
              <span>Operational Health:</span>
              <strong style="color:#dc2626;">OFFLINE (0 READS INGESTED)</strong>
            </div>
          </div>
        ` : `
          <div class="map-popup-card">
            <div class="popup-title">
              <strong>${cam.name}</strong>
            </div>
            <div class="popup-sub mono text-muted">${cam.camera_id} &bull; ${cam.zone}</div>
            <div class="popup-row">
              <span>Vehicle Volume:</span>
              <strong class="mono" style="font-size:13px; color:#0284c7;">${cam.vehicle_volume?.toLocaleString()} veh</strong>
            </div>
            <div class="popup-row">
              <span>Mean Speed:</span>
              <strong>${cam.avg_speed_kmph} km/h</strong>
            </div>
            <div class="popup-row">
              <span>Congestion Index:</span>
              <span class="mono">${(cam.congestion_index * 100).toFixed(0)}%</span>
            </div>
            <div class="popup-row">
              <span>Sensor Status:</span>
              <span style="color:#059669; font-weight:bold;">● ONLINE (Active Sighting Stream)</span>
            </div>
          </div>
        `;

        marker.bindPopup(popupContent, { maxWidth: 320 });
        marker.on('click', () => onSelectNode(cam));
        layerGroup.addLayer(marker);
      });
    }
  }, [cameras, corridors, showHeatmap, showCorridors]);

  return (
    <div className="city-gis-map-wrapper">
      <div ref={mapContainerRef} className="city-leaflet-container" />
      <div className="city-map-legend">
        <div className="legend-group">
          <span className="legend-label">Road Speeds:</span>
          <span className="legend-badge badge-free">🟢 Free Flow (&gt;45 km/h)</span>
          <span className="legend-badge badge-mod">🟡 Moderate (25–45 km/h)</span>
          <span className="legend-badge badge-cong">🔴 Congested (&lt;25 km/h)</span>
        </div>
        <div className="legend-group">
          <span className="legend-label">Sensors:</span>
          <span className="legend-badge badge-online">📷 Online Sensor</span>
          <span className="legend-badge badge-offline">⚠️ Sensor Offline (Incomplete Data)</span>
        </div>
      </div>
    </div>
  );
}
