import React from 'react';

export default function SecurityFeedback({ feedback, onDismiss }) {
  if (!feedback) return null;

  return (
    <aside className="security-feedback" role="alert" aria-live="assertive">
      <div>
        <strong>Action blocked</strong>
        <p>{feedback.message}</p>
        {feedback.reason !== 'UNKNOWN_SECURITY_REASON' && (
          <small>Reason: {feedback.reason}</small>
        )}
        {Number.isInteger(feedback.retry_after_seconds) && (
          <p>Try again in {feedback.retry_after_seconds} seconds.</p>
        )}
        {Number.isInteger(feedback.room_id) && (
          <small>Room: {feedback.room_id}</small>
        )}
      </div>
      <button type="button" onClick={onDismiss} aria-label="Dismiss security feedback">
        ×
      </button>
    </aside>
  );
}
