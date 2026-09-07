import React, { useState } from 'react';
import { useWebSocket } from '../lib/ws';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  
  const { sendMessage, isConnected, error, setError } = useWebSocket();

  const handleLogin = (e) => {
    e.preventDefault();
    if (!username || !password) return;
    sendMessage({ type: "SIGNIN", username, password });
  };

  const handleSignup = (e) => {
    e.preventDefault();
    if (!username || !password) return;
    sendMessage({ type: "SIGNUP", username, password });
  };

  return (
    <div style={{ maxWidth: '400px', margin: '0 auto', padding: '2rem' }}>
      <h2>Welcome to the Chat</h2>
      
      {!isConnected && (
        <div style={{ marginBottom: '1rem', color: 'orange' }}>
          Connecting to server...
        </div>
      )}

      {error && (
        <div style={{ marginBottom: '1rem', color: 'red', border: '1px solid red', padding: '0.5rem' }}>
          {error}
          <button style={{ float: 'right' }} onClick={() => setError(null)}>x</button>
        </div>
      )}
      
      <form style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem' }}>Username</label>
          <input 
            type="text"
            style={{ width: '100%', padding: '0.5rem', boxSizing: 'border-box' }}
            placeholder="Username" 
            value={username} 
            onChange={(e) => setUsername(e.target.value)} 
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem' }}>Password</label>
          <input 
            type="password" 
            style={{ width: '100%', padding: '0.5rem', boxSizing: 'border-box' }}
            placeholder="Password" 
            value={password} 
            onChange={(e) => setPassword(e.target.value)} 
          />
        </div>
        
        <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
          <button type="button" onClick={handleLogin} disabled={!isConnected} style={{ flex: 1, padding: '0.5rem' }}>
            Login
          </button>
          <button type="button" onClick={handleSignup} disabled={!isConnected} style={{ flex: 1, padding: '0.5rem' }}>
            Sign Up
          </button>
        </div>
      </form>
    </div>
  );
}
