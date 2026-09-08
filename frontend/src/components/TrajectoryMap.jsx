import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { fmtDateTime } from '../utils';

export default function TrajectoryMap({
  waypoints = [],
  segments = [],
  activeWaypointId = null,
  onSelectWaypoint = () => {},
}) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const layerGroupRef = useRef(null);
  const markersMapRef = useRef(new Map());

  // Initialize map once
  useEffect(() => {
    if (!mapContainerRef.current) return;

    // Default center on Delhi NCR
    const map = L.map(mapContainerRef.current, {
      center: [28.6139, 77.2090],
      zoom: 11,
      zoomControl: true,
    });

    // CartoDB Voyager sleek map tiles with clear road labels
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    const layerGroup = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;
    layerGroupRef.current = layerGroup;

    // Invalidate size to ensure tiles fill container
    setTimeout(() => map.invalidateSize(), 200);

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update markers and polyline segments when waypoints or segments change
  useEffect(() => {
    const map = mapInstanceRef.current;
    const layerGroup = layerGroupRef.current;
    if (!map || !layerGroup) return;

    layerGroup.clearLayers();
    markersMapRef.current.clear();

    if (!waypoints || waypoints.length === 0) return;

    const latLngs = [];

    // 1. Draw Path Segments (Solid for continuous, Dashed for gaps)
    if (segments && segments.length > 0) {
      segments.forEach((seg, idx) => {
        if (seg.type === 'continuous' && seg.coordinates && seg.coordinates.length > 1) {
          const polyline = L.polyline(seg.coordinates, {
            color: '#0284c7', // vibrant cyan/blue
            weight: 4,
            opacity: 0.9,
            lineJoin: 'round',
          });
          polyline.bindTooltip(
            `<strong>Observed Route Segment</strong><br/>${seg.stops ? seg.stops.length : 0} consecutive sightings`,
            { sticky: true }
          );
          layerGroup.addLayer(polyline);
        } else if (seg.type === 'gap' && seg.coordinates && seg.coordinates.length === 2) {
          // Explicit Coverage Gap: Dashed line indicating lack of camera sightings
          const gapLine = L.polyline(seg.coordinates, {
            color: '#d97706', // amber/orange
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
          layerGroup.addLayer(gapLine);
        }
      });
    } else if (waypoints.length > 1) {
      // Fallback: connect consecutive points if segments not passed
      const pts = waypoints.map(w => [w.lat, w.lon]);
      const polyline = L.polyline(pts, {
        color: '#0284c7',
        weight: 4,
        opacity: 0.9,
      });
      layerGroup.addLayer(polyline);
    }

    // 2. Draw Numbered Waypoint Markers
    waypoints.forEach((wp, index) => {
      const isFirst = index === 0;
      const isLast = index === waypoints.length - 1;
      const isGap = wp.is_gap;
      latLngs.push([wp.lat, wp.lon]);

      // Determine badge color
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

      // Build Rich Interactive Popup
      const popupHtml = `
        <div class="map-popup-card">
          <div class="popup-title">
            <span class="popup-seq">#${wp.sequence || index + 1}</span>
            <strong>${wp.camera_name}</strong>
          </div>
          <div class="popup-sub mono text-muted">ID: ${wp.camera_id} &bull; ${wp.lat.toFixed(4)}, ${wp.lon.toFixed(4)}</div>
          
          <div class="popup-row">
            <span>🕒 Timestamp:</span>
            <strong>${fmtDateTime(wp.timestamp)}</strong>
          </div>

          <div class="popup-row">
            <span>🎯 OCR Confidence:</span>
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
              📸 ${wp.burst_count} raw video frames collapsed (Deduplicated)
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

      layerGroup.addLayer(marker);
      markersMapRef.current.set(wp.id || `wp_${index}`, marker);
    });

    // 3. Fit bounds to all waypoints
    if (latLngs.length > 0) {
      try {
        const bounds = L.latLngBounds(latLngs);
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
      } catch (err) {
        console.warn('Could not fit map bounds:', err);
      }
    }
  }, [waypoints, segments]);

  // Center on active waypoint if user clicks from timeline
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
          <span>Observed Transit (Continuous Tracking)</span>
        </div>
        <div className="legend-item">
          <span className="legend-line dashed-line" />
          <span>Coverage Gap / Unobserved Transit (&gt;30 min or blindspot)</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-departure" />
          <span>Departure (1)</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-arrival" />
          <span>Latest Sighting</span>
        </div>
      </div>
    </div>
  );
}
