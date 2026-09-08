import React, { useState } from 'react';
import { useWebSocket } from '../lib/ws';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  
  const { sendMessage, isConnected, error, setError, notice, serverConnected } = useWebSocket();

  const handleLogin = (e) => {
    e.preventDefault();
    if (!username || !password) return;
    sendMessage({ type: "LOGIN", username, password });
  };

  const handleSignup = (e) => {
    e.preventDefault();
    if (!username || !password) return;
    sendMessage({ type: "SIGNUP", username, password });
  };

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="brand-mark" aria-hidden="true">C</div>
        <div className="page-kicker">Secure rooms. Simple chat.</div>
        <h2 id="auth-title">Welcome to the Chat</h2>
        <p className="page-subtitle">Sign in or create an account to join a room.</p>

        {notice && <p className="notice notice--success" role="status">{notice}</p>}
        {!serverConnected && isConnected && (
          <p className="notice notice--info">Login or signup will connect to the chat server.</p>
        )}
      
        {!isConnected && (
          <div className="notice notice--warning">
            Connecting to server...
          </div>
        )}

        {error && (
          <div className="notice notice--error">
            <span>{error}</span>
            <button className="icon-button" type="button" onClick={() => setError(null)} aria-label="Dismiss error">x</button>
          </div>
        )}
      
        <form className="stacked-form">
          <div className="field">
            <label>Username</label>
            <input 
              type="text"
              placeholder="Username" 
              value={username} 
              onChange={(e) => setUsername(e.target.value)} 
            />
          </div>
          <div className="field">
            <label>Password</label>
            <input 
              type="password" 
              placeholder="Password" 
              value={password} 
              onChange={(e) => setPassword(e.target.value)} 
            />
          </div>
        
          <div className="button-row">
            <button className="button button--primary" type="button" onClick={handleLogin} disabled={!isConnected}>
              Login
            </button>
            <button className="button button--secondary" type="button" onClick={handleSignup} disabled={!isConnected}>
              Sign Up
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
