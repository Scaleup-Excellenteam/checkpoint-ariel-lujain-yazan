import React from 'react';
import { useWebSocket } from './lib/ws';
import Login from './pages/Login';
import Home from './pages/Home';

function App() {
  const { user, isConnected, error } = useWebSocket();

  if (!isConnected) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <h3>{error || "Connecting to bridge..."}</h3>
      </div>
    );
  }

  // If there's no user, show the Login page
  if (!user) {
    return <Login />;
  }

  // Otherwise, show the Home dashboard!
  return <Home />;
}

export default App;
