import React from 'react';
import { useWebSocket } from './lib/ws';
import Login from './pages/Login';
import Home from './pages/Home';
import SecurityFeedback from './components/SecurityFeedback';

function App() {
  const {
    user,
    isConnected,
    error,
    securityFeedback,
    dismissSecurityFeedback,
  } = useWebSocket();

  if (!isConnected) {
    return (
      <div className="app-shell app-shell--center">
        <div className="status-panel">
          <span className="status-dot" aria-hidden="true" />
          <h3>{error || "Connecting to bridge..."}</h3>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <SecurityFeedback
        feedback={securityFeedback}
        onDismiss={dismissSecurityFeedback}
      />
      {user ? <Home /> : <Login />}
    </div>
  );
}

export default App;
