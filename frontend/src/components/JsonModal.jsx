import { useState } from 'react';

export default function JsonModal({ title, data, onClose }) {
  const [copied, setCopied] = useState(false);

  if (!data) return null;

  const jsonStr = JSON.stringify(data, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonStr);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <span className="terminal-prompt">$</span>
            <span className="modal-title">{title || 'PAYLOAD_INSPECTOR'}</span>
          </div>
          <div className="modal-actions">
            <button className="btn-dev btn-copy" onClick={handleCopy}>
              {copied ? 'COPIED_TO_CLIPBOARD' : 'COPY_RAW_JSON'}
            </button>
            <button className="btn-dev btn-close" onClick={onClose}>
              ESC [X]
            </button>
          </div>
        </div>
        <div className="modal-body">
          <pre className="dev-json-viewer">
            <code>{jsonStr}</code>
          </pre>
        </div>
        <div className="modal-footer">
          <span className="dev-status-tag">BYTES: {new Blob([jsonStr]).size}</span>
          <span className="dev-status-tag">TYPE: application/json</span>
          <span className="dev-status-tag">STATUS: 200 OK</span>
        </div>
      </div>
    </div>
  );
}
