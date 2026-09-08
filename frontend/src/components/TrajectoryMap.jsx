import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { fmtDateTime } from '../utils';

export default function TrajectoryMap({
  waypoints = [],
  segments = [],
  activeWaypointId = null,
  onSelectWaypoint = () => {},
  showLiveHeatmap = false,
  heatmapData = [],
  showLiveCameras = false,
  cameraNodes = [],
  onSelectPlate = () => {},
}) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const trajectoryLayerRef = useRef(null);
  const heatmapLayerRef = useRef(null);
  const cameraLayerRef = useRef(null);
  const markersMapRef = useRef(new Map());

  // Initialize Leaflet map instance
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: [28.6139, 77.2090],
      zoom: 11,
      zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    heatmapLayerRef.current = L.layerGroup().addTo(map);
    cameraLayerRef.current = L.layerGroup().addTo(map);
    trajectoryLayerRef.current = L.layerGroup().addTo(map);

    mapInstanceRef.current = map;
    setTimeout(() => map.invalidateSize(), 200);

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // ── Render Heatmap Circles ──
  useEffect(() => {
    const heatLayer = heatmapLayerRef.current;
    if (!heatLayer) return;
    heatLayer.clearLayers();

    if (!showLiveHeatmap || !heatmapData || heatmapData.length === 0) return;

    heatmapData.forEach((point) => {
      const lat = point.lat;
      const lng = point.lng || point.lon;
      if (!lat || !lng) return;

      const intensity = point.intensity ?? point.congestion_score ?? 0.35;
      const radius = 300 + intensity * 900;
      const color = intensity > 0.65 ? '#ef4444' : intensity > 0.4 ? '#f59e0b' : '#10b981';

      const circle = L.circle([lat, lng], {
        radius,
        stroke: false,
        fillColor: color,
        fillOpacity: 0.22,
      });

      circle.bindTooltip(
        `<div style="font-size:11px;">` +
        `<strong>${point.camera_id || 'Node'} - Congestion</strong><br/>` +
        `Level: <strong>${point.congestion_level || (intensity > 0.6 ? 'Heavy' : intensity > 0.3 ? 'Moderate' : 'Smooth')}</strong> (${Math.round(intensity * 100)}%)<br/>` +
        `Avg Speed: ${point.avg_speed_kmh || '48.0'} km/h` +
        `</div>`,
        { sticky: true }
      );

      heatLayer.addLayer(circle);
    });
  }, [showLiveHeatmap, heatmapData]);

  // ── Render Live Camera Nodes ──
  useEffect(() => {
    const camLayer = cameraLayerRef.current;
    if (!camLayer) return;
    camLayer.clearLayers();

    if (!showLiveCameras || !cameraNodes || cameraNodes.length === 0) return;

    cameraNodes.forEach((cam) => {
      const lat = cam.lat;
      const lng = cam.lng || cam.lon;
      if (!lat || !lng) return;

      const marker = L.circleMarker([lat, lng], {
        radius: 7,
        weight: 2,
        color: '#00f0ff',
        fillColor: '#0b111d',
        fillOpacity: 0.9,
      });

      marker.bindPopup(
        `<div class="map-popup-card">` +
        `<div class="popup-title"><strong>${cam.name || cam.camera_id}</strong></div>` +
        `<div class="popup-sub mono text-muted">ID: ${cam.camera_id} · Corridor: ${cam.corridor || 'Delhi Arterial'}</div>` +
        `<div style="margin-top:6px;font-size:11px;color:#38bdf8;">● Live Stream Active</div>` +
        `</div>`
      );

      camLayer.addLayer(marker);
    });
  }, [showLiveCameras, cameraNodes]);

  // ── Render Trajectory Segments & Waypoints ──
  useEffect(() => {
    const trajLayer = trajectoryLayerRef.current;
    const map = mapInstanceRef.current;
    if (!trajLayer || !map) return;

    trajLayer.clearLayers();
    markersMapRef.current.clear();

    if (!waypoints || waypoints.length === 0) return;

    const latLngs = [];

    // 1. Draw Road Segments (Solid = observed, Dashed = gaps)
    if (segments && segments.length > 0) {
      segments.forEach((seg) => {
        if (seg.type === 'continuous' && seg.coordinates && seg.coordinates.length > 1) {
          const polyline = L.polyline(seg.coordinates, {
            color: '#00f0ff',
            weight: 4.5,
            opacity: 0.95,
            lineJoin: 'round',
          });
          polyline.bindTooltip(
            `<strong>Observed Route Segment (OSM Road Snapped)</strong><br/>${seg.stops ? seg.stops.length : 0} consecutive sightings`,
            { sticky: true }
          );
          trajLayer.addLayer(polyline);
        } else if (seg.type === 'gap' && seg.coordinates && seg.coordinates.length === 2) {
          const gapLine = L.polyline(seg.coordinates, {
            color: '#f59e0b',
            weight: 3.5,
            dashArray: '8, 8',
            opacity: 0.85,
          });
          gapLine.bindTooltip(
            `<div style="font-size:12px;"><strong>⚠️ UNCOVERED GAP (${seg.gap_duration || ''})</strong><br/>` +
            `From: ${seg.from_stop}<br/>` +
            `To: ${seg.to_stop}<br/>` +
            `Distance: ${seg.distance_km} km &bull; Implied Speed: ${seg.implied_speed_kmph} km/h<br/>` +
            `<em style="color:#b45309;">${seg.reason || 'Unmonitored road segment'}</em></div>`,
            { sticky: true }
          );
          trajLayer.addLayer(gapLine);
        }
      });
    } else if (waypoints.length > 1) {
      const pts = waypoints.map(w => [w.lat, w.lon]);
      const polyline = L.polyline(pts, {
        color: '#00f0ff',
        weight: 4,
        opacity: 0.9,
      });
      trajLayer.addLayer(polyline);
    }

    // 2. Draw Numbered Waypoint Markers
    waypoints.forEach((wp, index) => {
      const isFirst = index === 0;
      const isLast = index === waypoints.length - 1;
      const isGap = wp.is_gap;
      latLngs.push([wp.lat, wp.lon]);

      let badgeClass = 'traj-map-pin';
      if (isFirst) badgeClass += ' pin-first';
      else if (isLast) badgeClass += ' pin-last';
      else if (isGap) badgeClass += ' pin-gap';

      const iconHtml = `
        <div class="${badgeClass}">
          <span>${wp.sequence || index + 1}</span>
        </div>
      `;

      const customIcon = L.divIcon({
        html: iconHtml,
        className: 'custom-div-icon',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
      });

      const marker = L.marker([wp.lat, wp.lon], { icon: customIcon });

      const popupHtml = `
        <div class="map-popup-card">
          <div class="popup-title">
            <span class="popup-seq">#${wp.sequence || index + 1}</span>
            <strong>${wp.camera_name}</strong>
          </div>
          <div class="popup-sub mono text-muted">ID: ${wp.camera_id} &bull; ${wp.lat.toFixed(4)}, ${wp.lon.toFixed(4)}</div>
          
          <div class="popup-row">
            <span>🕒 Sighting:</span>
            <strong>${fmtDateTime(wp.timestamp)}</strong>
          </div>

          <div class="popup-row">
            <span>🎯 Confidence:</span>
            <span class="conf-badge-sm">${(wp.confidence * 100).toFixed(1)}%</span>
          </div>

          ${wp.distance_km > 0 ? `
            <div class="popup-row">
              <span>📏 Hop Distance:</span>
              <strong>${wp.distance_km} km</strong>
            </div>
            <div class="popup-row">
              <span>⚡ Speed:</span>
              <strong>${wp.speed_kmph} km/h (${wp.formatted_delta || ''})</strong>
            </div>
          ` : ''}

          ${wp.burst_count > 1 ? `
            <div class="popup-badge-burst">
              📸 ${wp.burst_count} raw frames collapsed (Burst deduplicated)
            </div>
          ` : ''}

          ${isGap ? `
            <div class="popup-badge-gap">
              ⚠️ ${wp.gap_reason || 'Coverage Gap Detected'}
            </div>
          ` : ''}
        </div>
      `;

      marker.bindPopup(popupHtml, { maxWidth: 300 });
      marker.on('click', () => {
        onSelectWaypoint(wp);
      });

      trajLayer.addLayer(marker);
      markersMapRef.current.set(wp.id || `wp_${index}`, marker);
    });

    if (latLngs.length > 0) {
      try {
        const bounds = L.latLngBounds(latLngs);
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
      } catch (err) {
        console.warn('Could not fit map bounds:', err);
      }
    }
  }, [waypoints, segments]);

  // Center on active waypoint
  useEffect(() => {
    if (!activeWaypointId || !mapInstanceRef.current) return;
    const marker = markersMapRef.current.get(activeWaypointId);
    if (marker) {
      const map = mapInstanceRef.current;
      map.flyTo(marker.getLatLng(), 14, { duration: 0.8 });
      marker.openPopup();
    }
  }, [activeWaypointId]);

  return (
    <div className="trajectory-map-wrapper">
      <div ref={mapContainerRef} className="trajectory-leaflet-container" />
      <div className="map-legend-bar">
        <div className="legend-item">
          <span className="legend-line solid-line" />
          <span>Observed Transit (OSM Delhi Road)</span>
        </div>
        <div className="legend-item">
          <span className="legend-line dashed-line" />
          <span>Coverage Gap (&gt;80km/h or blindspot)</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-departure" />
          <span>Departure (1)</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-arrival" />
          <span>Latest Sighting</span>
        </div>
        {showLiveHeatmap && (
          <div className="legend-item">
            <span className="legend-dot" style={{ background: '#ef4444' }} />
            <span>Heavy Congestion</span>
          </div>
        )}
      </div>
    </div>
  );
}
