import React, { createContext, useContext, useEffect, useRef, useState } from 'react';

const WebSocketContext = createContext(null);

export const useWebSocket = () => {
  return useContext(WebSocketContext);
};

export const WebSocketProvider = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [user, setUser] = useState(null);
  const [rooms, setRooms] = useState([]);
  const [activeRoom, setActiveRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const usernameRef = useRef(null);

  useEffect(() => {
    // Check environment variable
    const useMocks = import.meta.env.VITE_USE_MOCKS === 'true';

    if (useMocks) {
      console.log("🟢 Using MOCK WebSocket Server");
      import('./MockWebSocket').then(({ MockWebSocket }) => {
        ws.current = new MockWebSocket();
        setupWebSocket(ws.current);
      });
    } else {
      console.log("🔵 Using REAL WebSocket Server");
      ws.current = new WebSocket('ws://127.0.0.1:9001/ws');
      setupWebSocket(ws.current);
    }

    function setupWebSocket(socket) {
      socket.onopen = () => {
        setIsConnected(true);
        setError(null);
        socket.send(JSON.stringify({ type: 'CONNECT' }));
      };

      socket.onclose = () => {
        setIsConnected(false);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleMessage(data);
        } catch (err) {
          console.error("Failed to parse websocket message", err);
        }
      };
    }

    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  const handleMessage = (message) => {
    switch (message.type) {
      case 'CONNECTED':
        if (message.logged_in) {
          setUser({ username: message.username });
        }
        break;
      case 'DISCONNECTED':
        setUser(null);
        break;
      case 'SIGNUP_RESULT':
        if (message.success) setError(null);
        else setError(message.reason);
        break;
      case 'LOGIN_RESULT':
        if (message.success) {
          setUser({ username: usernameRef.current || 'User' });
          setError(null);
        } else {
          setError(message.reason);
        }
        break;
      case 'LOGOUT_RESULT':
        if (message.success) {
          setUser(null);
          setRooms([]);
          setActiveRoom(null);
          setMessages([]);
        } else {
          setError(message.reason);
        }
        break;
      case 'ROOMS_LIST':
        setRooms(message.rooms || []);
        break;
      case 'JOIN_ROOM_RESULT':
        if (message.success) {
          setActiveRoom(message.room_id);
          setMessages([]);
        } else {
          setError(message.reason);
        }
        break;
      case 'LEAVE_ROOM_RESULT':
        if (message.success) {
          setActiveRoom(null);
          setMessages([]);
        } else {
          setError(message.reason);
        }
        break;
      case 'MESSAGE_RECEIVED':
        setMessages((prev) => [...prev, message]);
        break;
      case 'ERROR':
        setError(message.reason);
        break;
      default:
        console.warn("Unhandled message type:", message.type);
    }
  };

  const sendMessage = (payload) => {
    if (payload.type === 'LOGIN' || payload.type === 'SIGNUP') {
      usernameRef.current = payload.username;
    }
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    } else {
      console.error("WebSocket is not connected");
      setError("Not connected to server");
    }
  };

  const value = {
    isConnected,
    user,
    rooms,
    activeRoom,
    messages,
    error,
    sendMessage,
    setError // allow components to clear errors if needed
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};
