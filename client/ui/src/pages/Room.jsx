import React, { useState } from 'react';
import { useWebSocket } from '../lib/ws';

export default function Room() {
  const [text, setText] = useState('');
  const { messages, sendMessage, activeRoom } = useWebSocket();

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
    <div style={{ maxWidth: '600px', margin: '0 auto', padding: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2>Room: {activeRoom}</h2>
      </div>

      {/* Replicating the old vanilla structure here */}
      <section id="chat">
        <button id="disconnect-button" className="chat-button" onClick={handleLeave} style={{ marginBottom: '1rem' }}>
          Leave Room
        </button>

        <div id="messages" style={{ height: '300px', overflowY: 'auto', border: '1px solid #ccc', padding: '1rem', marginBottom: '1rem' }}>
          {messages.map((msg, idx) => (
            <div key={idx} style={{ marginBottom: '0.5rem' }}>
              <strong>{msg.sender || 'System'}:</strong> {msg.text}
            </div>
          ))}
        </div>

        <form id="message-form" onSubmit={handleSend} style={{ display: 'flex', gap: '0.5rem' }}>
          <input 
            id="message-input" 
            type="text" 
            placeholder="Write a message..." 
            autoComplete="off"
            value={text}
            onChange={(e) => setText(e.target.value)}
            style={{ flex: 1, padding: '0.5rem' }}
          />
          <button type="submit" style={{ padding: '0.5rem 1rem' }}>Send</button>
        </form>
      </section>
    </div>
  );
}
