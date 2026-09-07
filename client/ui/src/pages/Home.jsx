import React, { useEffect } from 'react';
import { useWebSocket } from '../lib/ws';
import Room from './Room';

export default function Home() {
  const { user, rooms, activeRoom, sendMessage } = useWebSocket();

  // Fetch rooms when the Home component mounts
  useEffect(() => {
    sendMessage({ type: "GET_ROOMS" });
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
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Dashboard</h1>
        <button onClick={handleLogout} style={{ padding: '0.5rem 1rem' }}>
          Logout
        </button>
      </div>
      <p>Welcome, <strong>{user?.username}</strong>!</p>
      
      <div style={{ marginTop: '2rem' }}>
        <h2>Available Rooms</h2>
        {rooms.length === 0 ? (
          <p>No rooms available currently.</p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {rooms.map(room => (
              <li key={room.id} style={{ 
                margin: '1rem 0', 
                padding: '1rem', 
                border: '1px solid #ddd', 
                borderRadius: '8px',
                display: 'flex', 
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <span style={{ fontSize: '1.2rem' }}>{room.name} <small style={{ color: '#666' }}>(ID: {room.id})</small></span>
                <button onClick={() => joinRoom(room.id)} style={{ padding: '0.5rem 1.5rem', cursor: 'pointer' }}>
                  Join Room
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
