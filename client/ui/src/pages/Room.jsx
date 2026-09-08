import React, { useState } from 'react';
import { useWebSocket } from '../lib/ws';

export default function Room() {
  const [text, setText] = useState('');
  const { messages, sendMessage, activeRoom, error, user } = useWebSocket();

  const handleLeave = () => {
    sendMessage({ type: "LEAVE_ROOM", room_id: activeRoom });
  };

  const handleSend = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    sendMessage({ type: "SEND_MESSAGE", room_id: activeRoom, text });
    setText('');
  };

  return (
    <main className="chat-page">
      <section className="chat-shell" aria-labelledby="room-title">
        <header className="chat-header">
          <div>
            <div className="page-kicker">Live chat</div>
            <h2 id="room-title">Room: {activeRoom}</h2>
          </div>
          <button id="disconnect-button" className="button button--ghost button--compact chat-button" onClick={handleLeave}>
            Leave Room
          </button>
        </header>

        {error && <p className="notice notice--error" role="alert">{error}</p>}

        <section id="chat" className="chat-panel">
          <div id="messages" className="messages">
            {messages.filter(msg => msg.room_id === activeRoom).map((msg, idx) => (
              <div
                key={msg.id ?? `${msg.created_at ?? 'live'}-${idx}`}
                className={`message-row ${msg.sender === user?.username ? 'message-row--mine' : 'message-row--theirs'}`}
              >
                <div className="message-bubble">
                  <strong>{msg.sender || 'System'}:</strong> {msg.text}
                </div>
              </div>
            ))}
          </div>

          <form id="message-form" className="message-form" onSubmit={handleSend}>
            <input 
              id="message-input" 
              type="text" 
              placeholder="Write a message..." 
              autoComplete="off"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button className="button button--primary button--send" type="submit">Send</button>
          </form>
        </section>
      </section>
    </main>
  );
}
