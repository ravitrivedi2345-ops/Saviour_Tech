import { useState } from 'react';

export default function ComparativeTrendChart({ trendsData = null, onToggleMetric = () => {}, currentMetric = 'volume' }) {
  const [hoverIndex, setHoverIndex] = useState(null);

  if (!trendsData || !trendsData.hours || trendsData.hours.length === 0) {
    return (
      <div className="chart-empty-box">
        <span>Loading comparative traffic flow trends...</span>
      </div>
    );
  }

  const hours = trendsData.hours;
  const curr = trendsData.current_period.data;
  const prior = trendsData.prior_period.data;
  const maxVal = Math.max(...curr, ...prior, 100);

  // SVG dimensions
  const svgWidth = 720;
  const svgHeight = 220;
  const padLeft = 45;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 35;
  const chartW = svgWidth - padLeft - padRight;
  const chartH = svgHeight - padTop - padBottom;

  function getX(i) {
    return padLeft + (i / (hours.length - 1)) * chartW;
  }

  function getY(val) {
    return padTop + chartH - (val / maxVal) * chartH;
  }

  // Generate SVG path string
  const currPoints = curr.map((v, i) => `${getX(i)},${getY(v)}`).join(' ');
  const priorPoints = prior.map((v, i) => `${getX(i)},${getY(v)}`).join(' ');

  // Morning (idx 8 to 11) & Evening (idx 17 to 21) rush boxes
  const mStart = getX(8);
  const mEnd = getX(11);
  const eStart = getX(17);
  const eEnd = getX(21);

  const isSpeed = currentMetric === 'speed';
  const unitStr = isSpeed ? 'km/h' : 'veh';

  return (
    <div className="trend-chart-card">
      <div className="trend-chart-header">
        <div className="trend-title-block">
          <span className="trend-main-title">📈 24-Hour Comparative Flow Trends</span>
          <span className="trend-sub-title">
            Comparing <strong>{trendsData.current_period.label}</strong> vs. <strong>{trendsData.prior_period.label}</strong>
          </span>
        </div>

        <div className="trend-actions">
          <div className="metric-toggle-pills">
            <button
              type="button"
              className={`pill-btn ${currentMetric === 'volume' ? 'active' : ''}`}
              onClick={() => onToggleMetric('volume')}
            >
              🚗 Volume (veh/hr)
            </button>
            <button
              type="button"
              className={`pill-btn ${currentMetric === 'speed' ? 'active' : ''}`}
              onClick={() => onToggleMetric('speed')}
            >
              ⚡ Speed (km/h)
            </button>
          </div>
        </div>
      </div>

      {/* KPI Delta Bar */}
      <div className="trend-kpi-summary">
        <div className="trend-kpi-item">
          <span className="kpi-micro-label">Current Period Total</span>
          <span className="kpi-val mono">
            {isSpeed
              ? `${(trendsData.current_period.total / 24).toFixed(1)} km/h`
              : `${trendsData.current_period.total.toLocaleString()} veh`}
          </span>
        </div>
        <div className="trend-kpi-item">
          <span className="kpi-micro-label">Prior Period Total</span>
          <span className="kpi-val mono text-muted">
            {isSpeed
              ? `${(trendsData.prior_period.total / 24).toFixed(1)} km/h`
              : `${trendsData.prior_period.total.toLocaleString()} veh`}
          </span>
        </div>
        <div className="trend-kpi-item">
          <span className="kpi-micro-label">Period Variance</span>
          <span
            className="kpi-val mono"
            style={{ color: trendsData.delta_pct >= 0 ? '#10b981' : '#f59e0b' }}
          >
            {trendsData.delta_pct >= 0 ? `+${trendsData.delta_pct}%` : `${trendsData.delta_pct}%`}
          </span>
        </div>
        <div className="trend-kpi-item">
          <span className="kpi-micro-label">Peak Congestion Hour</span>
          <span className="kpi-val mono highlight-cyan">
            {trendsData.peak_hour} ({trendsData.peak_value?.toLocaleString()} {unitStr})
          </span>
        </div>
      </div>

      {/* Responsive SVG Chart */}
      <div className="svg-chart-container">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="trend-svg"
          onMouseLeave={() => setHoverIndex(null)}
        >
          {/* Shaded Rush Hour Bands */}
          <rect
            x={mStart}
            y={padTop}
            width={mEnd - mStart}
            height={chartH}
            fill="rgba(59, 130, 246, 0.08)"
          />
          <text x={(mStart + mEnd) / 2} y={padTop + 14} textAnchor="middle" fill="#60a5fa" fontSize="9" fontWeight="bold">
            MORNING RUSH (08:00 - 11:00)
          </text>

          <rect
            x={eStart}
            y={padTop}
            width={eEnd - eStart}
            height={chartH}
            fill="rgba(245, 158, 11, 0.08)"
          />
          <text x={(eStart + eEnd) / 2} y={padTop + 14} textAnchor="middle" fill="#f59e0b" fontSize="9" fontWeight="bold">
            EVENING RUSH (17:00 - 21:00)
          </text>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
            const y = padTop + chartH - ratio * chartH;
            const valLabel = Math.round(ratio * maxVal);
            return (
              <g key={idx}>
                <line x1={padLeft} y1={y} x2={padLeft + chartW} y2={y} stroke="rgba(255, 255, 255, 0.06)" />
                <text x={padLeft - 6} y={y + 3} textAnchor="end" fill="#64748b" fontSize="9" fontFamily="monospace">
                  {valLabel >= 1000 ? `${(valLabel / 1000).toFixed(0)}k` : valLabel}
                </text>
              </g>
            );
          })}

          {/* Prior Period Line (Dashed Amber) */}
          <polyline
            fill="none"
            stroke="#94a3b8"
            strokeWidth="2"
            strokeDasharray="4 4"
            points={priorPoints}
          />

          {/* Current Period Line (Solid Vibrant Cyan) */}
          <polyline
            fill="none"
            stroke="#06b6d4"
            strokeWidth="2.5"
            points={currPoints}
          />

          {/* Data Points and Interaction Circles */}
          {hours.map((hrStr, i) => {
            const cx = getX(i);
            const cyCurr = getY(curr[i]);
            const cyPrior = getY(prior[i]);
            const isHovered = hoverIndex === i;

            return (
              <g key={i}>
                {/* X-axis time label (every 3 hours) */}
                {i % 3 === 0 && (
                  <text x={cx} y={svgHeight - 10} textAnchor="middle" fill="#94a3b8" fontSize="9" fontFamily="monospace">
                    {hrStr}
                  </text>
                )}

                {/* Point dot on current line */}
                <circle
                  cx={cx}
                  cy={cyCurr}
                  r={isHovered ? 5 : 2.5}
                  fill={isHovered ? '#38bdf8' : '#06b6d4'}
                  stroke="#0f172a"
                  strokeWidth="1.5"
                />

                {/* Invisible hover trigger bar */}
                <rect
                  x={cx - (chartW / hours.length) / 2}
                  y={padTop}
                  width={chartW / hours.length}
                  height={chartH}
                  fill="transparent"
                  onMouseEnter={() => setHoverIndex(i)}
                />
              </g>
            );
          })}

          {/* Hover Vertical Guide & Tooltip */}
          {hoverIndex !== null && (
            <g>
              <line
                x1={getX(hoverIndex)}
                y1={padTop}
                x2={getX(hoverIndex)}
                y2={padTop + chartH}
                stroke="rgba(255, 255, 255, 0.4)"
                strokeDasharray="2 2"
              />
              <circle cx={getX(hoverIndex)} cy={getY(curr[hoverIndex])} r={5} fill="#06b6d4" stroke="#fff" strokeWidth="2" />
              <circle cx={getX(hoverIndex)} cy={getY(prior[hoverIndex])} r={5} fill="#94a3b8" stroke="#fff" strokeWidth="2" />
            </g>
          )}
        </svg>

        {/* Floating Tooltip Box */}
        {hoverIndex !== null && (
          <div
            className="chart-hover-tooltip"
            style={{
              left: `${(getX(hoverIndex) / svgWidth) * 100}%`,
            }}
          >
            <div className="tooltip-title mono">{hours[hoverIndex]} Commute Slot</div>
            <div className="tooltip-val" style={{ color: '#06b6d4' }}>
              ● Today: <strong>{curr[hoverIndex]?.toLocaleString()} {unitStr}</strong>
            </div>
            <div className="tooltip-val" style={{ color: '#94a3b8' }}>
              --- Last Week: <strong>{prior[hoverIndex]?.toLocaleString()} {unitStr}</strong>
            </div>
            <div className="tooltip-delta mono" style={{ fontSize: 10, marginTop: 3 }}>
              Variance: {curr[hoverIndex] >= prior[hoverIndex] ? '+' : ''}
              {(((curr[hoverIndex] - prior[hoverIndex]) / Math.max(1, prior[hoverIndex])) * 100).toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      <div className="chart-legend-row">
        <div className="legend-entry">
          <span className="legend-swatch swatch-current" />
          <span>Current Period (Today)</span>
        </div>
        <div className="legend-entry">
          <span className="legend-swatch swatch-prior" />
          <span>Prior Period (Last Week — Same Day)</span>
        </div>
      </div>
    </div>
  );
}
