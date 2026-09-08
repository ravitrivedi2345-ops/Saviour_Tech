const API = 'http://localhost:8000';

// In-memory request log for the Developer Console Drawer
export const requestLogs = [];
const logListeners = new Set();

export function subscribeLogs(fn) {
  logListeners.add(fn);
  return () => logListeners.delete(fn);
}

export function getStoredToken() {
  return localStorage.getItem('anpr_access_token');
}

function authHeaders(extra = {}) {
  const token = getStoredToken();
  const headers = { ...extra };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function requestWithTelemetry(url, options = {}) {
  const method = options.method || 'GET';
  const start = performance.now();
  const timestamp = new Date().toISOString().split('T')[1].slice(0, 8);

  const headers = authHeaders(options.headers || {});
  const fetchOptions = { ...options, headers };

  try {
    const res = await fetch(url, fetchOptions);
    const duration = Math.round(performance.now() - start);
    const entry = {
      id: Math.random().toString(36).slice(2, 9),
      method,
      url: url.replace(API, ''),
      status: res.status,
      duration,
      timestamp,
      ok: res.ok,
    };
    requestLogs.unshift(entry);
    if (requestLogs.length > 50) requestLogs.pop();
    logListeners.forEach(fn => fn([...requestLogs]));

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return await res.json();
  } catch (err) {
    const duration = Math.round(performance.now() - start);
    const entry = {
      id: Math.random().toString(36).slice(2, 9),
      method,
      url: url.replace(API, ''),
      status: 'ERR',
      duration,
      timestamp,
      ok: false,
      error: err.message,
    };
    requestLogs.unshift(entry);
    if (requestLogs.length > 50) requestLogs.pop();
    logListeners.forEach(fn => fn([...requestLogs]));
    throw err;
  }
}

export async function simulate(count = 200) {
  return requestWithTelemetry(`${API}/simulate?count=${count}`, { method: 'POST' });
}

export async function getDetections(limit = 100) {
  return requestWithTelemetry(`${API}/detections?limit=${limit}`);
}

export async function getTrajectory(plate) {
  return requestWithTelemetry(`${API}/trajectory?plate=${encodeURIComponent(plate)}`);
}

export async function queryTrajectory({
  plate,
  start = '',
  end = '',
  minConfidence = 0.0,
  page = 1,
  limit = 50,
  gapThresholdMin = 30.0,
  deduplicate = true,
}) {
  const params = new URLSearchParams({
    plate,
    min_confidence: minConfidence,
    page,
    limit,
    gap_threshold_min: gapThresholdMin,
    deduplicate: deduplicate ? 'true' : 'false',
  });
  if (start) params.append('start', start);
  if (end) params.append('end', end);

  return requestWithTelemetry(`${API}/trajectory?${params.toString()}`);
}

export function getTrajectoryCsvUrl({ plate, start = '', end = '', minConfidence = 0.0 }) {
  const params = new URLSearchParams({ plate, min_confidence: minConfidence });
  if (start) params.append('start', start);
  if (end) params.append('end', end);
  return `${API}/trajectory/export/csv?${params.toString()}`;
}

export function getTrajectoryReportUrl({ plate, start = '', end = '', minConfidence = 0.0 }) {
  const params = new URLSearchParams({ plate, min_confidence: minConfidence });
  if (start) params.append('start', start);
  if (end) params.append('end', end);
  return `${API}/trajectory/export/pdf?${params.toString()}`;
}

// ─── Component 3: City Traffic Analytics API ─────────────────────────────────

export async function getCityHeatmap({ date = '', hourRange = 'all', zone = '' } = {}) {
  const params = new URLSearchParams({ hour_range: hourRange });
  if (date) params.append('date', date);
  if (zone && zone !== 'All Zones') params.append('zone', zone);
  return requestWithTelemetry(`${API}/analytics/heatmap?${params.toString()}`);
}

export async function getSegmentSpeeds({ date = '', hourRange = 'all', zone = '', segmentId = '' } = {}) {
  const params = new URLSearchParams({ hour_range: hourRange });
  if (date) params.append('date', date);
  if (zone && zone !== 'All Zones') params.append('zone', zone);
  if (segmentId) params.append('segment_id', segmentId);
  return requestWithTelemetry(`${API}/analytics/speed?${params.toString()}`);
}

export async function getRouteDensity({ zone = '', period = 'today' } = {}) {
  const params = new URLSearchParams({ period });
  if (zone && zone !== 'All Zones') params.append('zone', zone);
  return requestWithTelemetry(`${API}/analytics/density?${params.toString()}`);
}

export async function getTrafficTrends({ compare = 'today_vs_last_week', metric = 'volume' } = {}) {
  const params = new URLSearchParams({ compare, metric });
  return requestWithTelemetry(`${API}/analytics/trends?${params.toString()}`);
}

export function getCityAnalyticsCsvUrl({ date = '', hourRange = 'all', zone = '' } = {}) {
  const params = new URLSearchParams({ hour_range: hourRange });
  if (date) params.append('date', date);
  if (zone && zone !== 'All Zones') params.append('zone', zone);
  return `${API}/analytics/export/csv?${params.toString()}`;
}

export function getCityAnalyticsReportUrl({ date = '', hourRange = 'all', zone = '' } = {}) {
  const params = new URLSearchParams({ hour_range: hourRange });
  if (date) params.append('date', date);
  if (zone && zone !== 'All Zones') params.append('zone', zone);
  return `${API}/analytics/export/pdf?${params.toString()}`;
}

export async function getCongestion() {
  return requestWithTelemetry(`${API}/analytics/congestion`);
}

export async function getSpeeds() {
  return requestWithTelemetry(`${API}/analytics/speeds`);
}

export async function getAlerts() {
  return requestWithTelemetry(`${API}/alerts`);
}

// ─── Component 4: Real-Time Alert System API ─────────────────────────────────

export async function getAlertsPaginated({
  status = '',
  alertType = '',
  priority = '',
  plate = '',
  dateFrom = '',
  dateTo = '',
  page = 1,
  limit = 50,
} = {}) {
  const params = new URLSearchParams({ page, limit });
  if (status && status !== 'ALL') params.append('status', status);
  if (alertType && alertType !== 'ALL') params.append('alert_type', alertType);
  if (priority && priority !== 'ALL') params.append('priority', priority);
  if (plate) params.append('plate', plate);
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  return requestWithTelemetry(`${API}/alerts?${params.toString()}`);
}

export async function getAlertDetail(alertId) {
  return requestWithTelemetry(`${API}/alerts/${encodeURIComponent(alertId)}`);
}

export async function updateAlertStatus(alertId, { status, reviewedBy = 'operator', notes = '' }) {
  return requestWithTelemetry(`${API}/alerts/${encodeURIComponent(alertId)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, reviewed_by: reviewedBy, notes }),
  });
}

export async function getAlertAudit(alertId) {
  return requestWithTelemetry(`${API}/alerts/${encodeURIComponent(alertId)}/audit`);
}

export async function getAlertStats() {
  return requestWithTelemetry(`${API}/alerts/stats`);
}

export async function getBlacklist({ isActive = true, priority = '', search = '' } = {}) {
  const params = new URLSearchParams();
  if (isActive !== null && isActive !== undefined) params.append('is_active', isActive);
  if (priority && priority !== 'ALL') params.append('priority', priority);
  if (search) params.append('search', search);
  return requestWithTelemetry(`${API}/blacklist?${params.toString()}`);
}

export async function addToBlacklist({ plateNumber, reason, priority = 'HIGH', addedBy = 'operator' }) {
  return requestWithTelemetry(`${API}/blacklist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      plate_number: plateNumber,
      reason,
      priority,
      added_by: addedBy,
    }),
  });
}

export async function updateBlacklistEntry(plate, { reason, priority, isActive }) {
  const body = {};
  if (reason !== undefined) body.reason = reason;
  if (priority !== undefined) body.priority = priority;
  if (isActive !== undefined) body.is_active = isActive;
  return requestWithTelemetry(`${API}/blacklist/${encodeURIComponent(plate)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function removeFromBlacklist(plate) {
  return requestWithTelemetry(`${API}/blacklist/${encodeURIComponent(plate)}`, {
    method: 'DELETE',
  });
}

export async function getAlertConfig() {
  return requestWithTelemetry(`${API}/alerts/config`);
}

export async function updateAlertConfig(updates, updatedBy = 'admin') {
  return requestWithTelemetry(`${API}/alerts/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates, updated_by: updatedBy }),
  });
}

export async function getQueueStatus() {
  return requestWithTelemetry(`${API}/alerts/queue-status`);
}

/**
 * Creates an auto-reconnecting WebSocket connection to the alert stream.
 */
export function createAlertsWebSocket(onMessage, onOpen, onClose, onError) {
  const wsUrl = 'ws://localhost:8000/ws/alerts';
  let ws = null;
  let retryTimeout = null;
  let isClosedExplicitly = false;

  function connect() {
    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = (e) => {
        if (onOpen) onOpen(e);
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (onMessage) onMessage(data);
        } catch (err) {
          console.error('[WebSocket] Message parse error:', err);
        }
      };

      ws.onclose = (e) => {
        if (onClose) onClose(e);
        if (!isClosedExplicitly) {
          // Reconnect after 3s
          retryTimeout = setTimeout(connect, 3000);
        }
      };

      ws.onerror = (e) => {
        if (onError) onError(e);
      };
    } catch (err) {
      console.error('[WebSocket] Connection failed:', err);
      if (!isClosedExplicitly) {
        retryTimeout = setTimeout(connect, 3000);
      }
    }
  }

  connect();

  return {
    send: (msg) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }
    },
    close: () => {
      isClosedExplicitly = true;
      if (retryTimeout) clearTimeout(retryTimeout);
      if (ws) ws.close();
    },
  };
}

export async function getSummary() {
  return requestWithTelemetry(`${API}/summary`);
}

export async function getCameras() {
  return requestWithTelemetry(`${API}/cameras`);
}

export async function getIdentity(plate) {
  return requestWithTelemetry(`${API}/enforcement/identity/${encodeURIComponent(plate)}`);
}

// ─── Component 1: High-Precision OCR Service (Port 8001) ───
const OCR_API = 'http://localhost:8001';

export async function getOcrHealth() {
  const res = await fetch(`${OCR_API}/api/v1/health`);
  if (!res.ok) throw new Error('OCR service unreachable');
  return res.json();
}

export async function getOcrMetrics() {
  const res = await fetch(`${OCR_API}/api/v1/metrics`);
  if (!res.ok) throw new Error('Failed to fetch OCR metrics');
  return res.json();
}

export async function detectPlateBase64(imageBase64, cameraId = 'CAM_01', metadataHint = null) {
  const res = await fetch(`${OCR_API}/api/v1/detect/base64`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image_base64: imageBase64,
      camera_id: cameraId,
      metadata_hint: metadataHint,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export async function getOcrDetections(limit = 20) {
  const res = await fetch(`${OCR_API}/api/v1/detections?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch OCR detections');
  return res.json();
}

// ─── Authentication & RBAC API ────────────────────────────────────────────────

export async function login(username, password) {
  return requestWithTelemetry(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
}

export async function refreshToken(refreshTokenValue) {
  return requestWithTelemetry(`${API}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshTokenValue }),
  });
}

export async function logout() {
  return requestWithTelemetry(`${API}/auth/logout`, { method: 'POST' });
}

export async function getMe() {
  return requestWithTelemetry(`${API}/auth/me`);
}

export async function getAuditLogs({ action = '', username = '', limit = 50 } = {}) {
  const params = new URLSearchParams({ limit });
  if (action) params.append('action', action);
  if (username) params.append('username', username);
  return requestWithTelemetry(`${API}/auth/audit-logs?${params.toString()}`);
}

// ─── Video Upload & Processing API ────────────────────────────────────────────

export async function uploadVideo(file, cameraId = 'CAM-01') {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('camera_id', cameraId);

  const token = getStoredToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const start = performance.now();
  const res = await fetch(`${API}/video/upload`, {
    method: 'POST',
    headers,
    body: formData,
  });

  const duration = Math.round(performance.now() - start);
  const entry = {
    id: Math.random().toString(36).slice(2, 9),
    method: 'POST',
    url: '/video/upload',
    status: res.status,
    duration,
    timestamp: new Date().toISOString().split('T')[1].slice(0, 8),
    ok: res.ok,
  };
  requestLogs.unshift(entry);
  if (requestLogs.length > 50) requestLogs.pop();
  logListeners.forEach(fn => fn([...requestLogs]));

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export async function getVideoStatus(taskId) {
  return requestWithTelemetry(`${API}/video/status/${encodeURIComponent(taskId)}`);
}

export async function getVideoTasks() {
  return requestWithTelemetry(`${API}/video/tasks`);
}

export function createVideoProcessWebSocket(taskId, onMessage, onOpen, onClose, onError) {
  const wsUrl = `ws://localhost:8000/ws/video-process/${encodeURIComponent(taskId)}`;
  let ws = null;
  let retryTimeout = null;
  let isClosedExplicitly = false;

  function connect() {
    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = (e) => { if (onOpen) onOpen(e); };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (onMessage) onMessage(data);
        } catch (err) {
          console.error('[Video WS] Parse error:', err);
        }
      };

      ws.onclose = (e) => {
        if (onClose) onClose(e);
        if (!isClosedExplicitly) retryTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = (e) => { if (onError) onError(e); };
    } catch (err) {
      if (!isClosedExplicitly) retryTimeout = setTimeout(connect, 3000);
    }
  }

  connect();

  return {
    send: (msg) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }
    },
    close: () => {
      isClosedExplicitly = true;
      if (retryTimeout) clearTimeout(retryTimeout);
      if (ws) ws.close();
    },
  };
}

// ─── Live Traffic WebSocket ───────────────────────────────────────────────────

export function createLiveTrafficWebSocket(onMessage, onOpen, onClose, onError) {
  const wsUrl = 'ws://localhost:8000/ws/live-traffic';
  let ws = null;
  let retryTimeout = null;
  let isClosedExplicitly = false;

  function connect() {
    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = (e) => { if (onOpen) onOpen(e); };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (onMessage) onMessage(data);
        } catch (err) {
          console.error('[Live Traffic WS] Parse error:', err);
        }
      };

      ws.onclose = (e) => {
        if (onClose) onClose(e);
        if (!isClosedExplicitly) retryTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = (e) => { if (onError) onError(e); };
    } catch (err) {
      if (!isClosedExplicitly) retryTimeout = setTimeout(connect, 3000);
    }
  }

  connect();

  return {
    send: (msg) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }
    },
    close: () => {
      isClosedExplicitly = true;
      if (retryTimeout) clearTimeout(retryTimeout);
      if (ws) ws.close();
    },
  };
}

// ─── OSRM Road Routing API ────────────────────────────────────────────────────

export async function getCorridorPath({ startCam = '', endCam = '', originLat, originLng, destLat, destLng } = {}) {
  const params = new URLSearchParams();
  if (startCam) params.append('start_cam', startCam);
  if (endCam) params.append('end_cam', endCam);
  if (originLat != null) params.append('origin_lat', originLat);
  if (originLng != null) params.append('origin_lng', originLng);
  if (destLat != null) params.append('dest_lat', destLat);
  if (destLng != null) params.append('dest_lng', destLng);
  return requestWithTelemetry(`${API}/routing/corridor-path?${params.toString()}`);
}

