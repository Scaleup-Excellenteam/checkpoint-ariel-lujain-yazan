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
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <h3>{error || "Connecting to bridge..."}</h3>
      </div>
    );
  }

  return (
    <>
      <SecurityFeedback
        feedback={securityFeedback}
        onDismiss={dismissSecurityFeedback}
      />
      {user ? <Home /> : <Login />}
    </>
  );
}

export default App;
