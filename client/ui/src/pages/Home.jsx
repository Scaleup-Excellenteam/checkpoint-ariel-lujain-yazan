import React, { useEffect, useState } from 'react';
import { useWebSocket } from '../lib/ws';
import Room from './Room';

export default function Home() {
  const { user, rooms, activeRoom, sendMessage, error } = useWebSocket();

  const [roomName, setRoomName] = useState('');

  const createRoom = (event) => {
    event.preventDefault();
    if (!roomName.trim()) return;
    sendMessage({ type: 'CREATE_ROOM', name: roomName.trim() });
    setRoomName('');
  };

  // Fetch rooms when the Home component mounts
  useEffect(() => {
    sendMessage({ type: "LIST_ROOMS" });
  }, [sendMessage]);

  const handleLogout = () => {
    sendMessage({ type: "LOGOUT" });
  };

  const joinRoom = (roomId) => {
    sendMessage({ type: "JOIN_ROOM", room_id: roomId });
  };

  // If the user has an active room, render the Room view instead!
  if (activeRoom) {
    return <Room />;
  }

  // Otherwise, show the dashboard with the room list
  return (
    <main className="rooms-page">
      <header className="rooms-header">
        <div>
          <div className="page-kicker">Rooms</div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">Welcome, <strong>{user?.username}</strong>!</p>
        </div>
        <button className="button button--ghost" onClick={handleLogout}>
          Logout
        </button>
      </header>
      
      <section className="rooms-grid">
        <div className="panel panel--rooms">
          <div className="section-header">
            <div>
              <h2>Available Rooms</h2>
              <p>Pick a conversation space and jump in.</p>
            </div>
            <button className="button button--secondary button--compact" onClick={() => sendMessage({ type: 'LIST_ROOMS' })}>Refresh Rooms</button>
          </div>
          {error && <p className="notice notice--error" role="alert">{error}</p>}

          {rooms.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state__icon" aria-hidden="true">#</div>
              <p>No rooms available currently.</p>
            </div>
          ) : (
            <ul className="room-list">
              {rooms.map(room => (
                <li key={room.id} className="room-card">
                  <div className="room-card__content">
                    <span className="room-avatar" aria-hidden="true">{room.name?.charAt(0)?.toUpperCase() || '#'}</span>
                    <span>
                      <span className="room-name">{room.name}</span>
                      <small>(ID: {room.id})</small>
                    </span>
                  </div>
                  <button className="button button--primary button--compact" onClick={() => joinRoom(room.id)}>
                    Join Room
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <aside className="panel panel--create">
          <div className="section-header section-header--stacked">
            <h2>Create new room</h2>
            <p>Start a clean space for a new conversation.</p>
          </div>
          <form className="create-room-form" onSubmit={createRoom}>
            <label className="field">Room name <input value={roomName} maxLength={50}
              onChange={event => setRoomName(event.target.value)} required /></label>
            <button className="button button--primary" type="submit">Create Room</button>
          </form>
        </aside>
      </section>
    </main>
  );
}
