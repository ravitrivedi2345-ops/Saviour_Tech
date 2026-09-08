import { useState } from 'react';

export default function StudentGuideBanner({ onTryDemo }) {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="student-guide-card">
      <div className="guide-header" onClick={() => setIsOpen(!isOpen)}>
        <div className="guide-header-left">
          <span className="guide-icon">💡</span>
          <div>
            <div className="guide-title">
              How This System Works — Quick Student &amp; Evaluator Guide
            </div>
            <div className="guide-subtitle">
              Learn how AI tracks vehicles across city cameras without relying on perfect data or violating privacy.
            </div>
          </div>
        </div>
        <button className="guide-toggle-btn">
          {isOpen ? 'Hide Guide ▲' : 'Show Guide ▼'}
        </button>
      </div>

      {isOpen && (
        <div className="guide-body">
          <div className="guide-steps-grid">
            <div className="guide-step">
              <div className="step-num">Step 1</div>
              <div className="step-title">Cameras Read Plates with Noise</div>
              <div className="step-desc">
                9 cameras around Delhi scan cars. But real cameras make mistakes (~15% typo rate, swapping <strong>0 ↔ O</strong> or <strong>8 ↔ B</strong>).
              </div>
            </div>

            <div className="guide-step">
              <div className="step-num">Step 2</div>
              <div className="step-title">AI Fuzzy Matching</div>
              <div className="step-desc">
                Instead of failing on typos, our Levenshtein algorithm automatically groups noisy reads (e.g. <code>DLO1A81234</code>) into the correct vehicle path.
              </div>
            </div>

            <div className="guide-step">
              <div className="step-num">Step 3</div>
              <div className="step-title">Physics &amp; Speed Sanity Check</div>
              <div className="step-desc">
                If a car appears at Connaught Place and Noida 2 minutes later, that requires 300+ km/h! The AI flags this as an impossible <strong>GAP</strong>.
              </div>
            </div>

            <div className="guide-step">
              <div className="step-num">Step 4</div>
              <div className="step-title">Privacy Protection</div>
              <div className="step-desc">
                Traffic planners only see anonymous car paths. Owner personal info is strictly isolated in the Police Vault.
              </div>
            </div>
          </div>

          <div className="guide-demo-actions">
            <span className="demo-actions-label">Try 1-Click Interactive Demos:</span>
            <button
              className="btn-demo-pill highlight"
              onClick={() => onTryDemo('DL01AB1234')}
            >
              🚗 Track Wanted Car (DL01AB1234)
            </button>
            <button
              className="btn-demo-pill"
              onClick={() => onTryDemo('DLO1A81234')}
            >
              🔍 Test Typo / Noise Match (DLO1A81234)
            </button>
            <button
              className="btn-demo-pill"
              onClick={() => onTryDemo('MH12XY5678')}
            >
              ⚡ Track Inter-State Vehicle (MH12XY5678)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
