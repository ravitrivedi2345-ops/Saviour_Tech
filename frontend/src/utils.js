// Utility helpers shared across components

/**
 * Format an ISO timestamp to a readable local time string.
 */
export function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return iso;
  }
}

/**
 * Format an ISO timestamp to date + time.
 */
export function fmtDateTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return iso;
  }
}

/**
 * Return CSS class for a confidence score.
 */
export function confClass(score) {
  if (score >= 0.85) return 'conf-high';
  if (score >= 0.72) return 'conf-med';
  return 'conf-low';
}

/**
 * Clamp a number between min and max.
 */
export function clamp(val, min, max) {
  return Math.min(Math.max(val, min), max);
}

/**
 * Return a vehicle type emoji.
 */
export function vtypeIcon(vtype) {
  const map = {
    'Car': '🚗',
    'Motorcycle': '🏍️',
    'Truck': '🚛',
    'Auto-Rickshaw': '🛺',
    'Bus': '🚌',
  };
  return map[vtype] || '🚗';
}
