import React, { createContext, useContext, useCallback, useEffect, useRef, useState } from 'react';

const WebSocketContext = createContext(null);

export const useWebSocket = () => {
  return useContext(WebSocketContext);
};

export const WebSocketProvider = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [serverConnected, setServerConnected] = useState(false);
  const [notice, setNotice] = useState(null);
  const [user, setUser] = useState(null);
  const [rooms, setRooms] = useState([]);
  const [activeRoom, setActiveRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState(null);
  const [securityFeedback, setSecurityFeedback] = useState(null);
  const ws = useRef(null);
  const usernameRef = useRef(null);

  function handleMessage(message) {
    switch (message.type) {
      case 'CONNECTED':
        setServerConnected(true);
        if (message.logged_in) {
          setUser({ username: message.username });
        }
        break;
      case 'DISCONNECTED':
        setServerConnected(false);
        setUser(null);
        setActiveRoom(null);
        setMessages([]);
        break;
      case 'SECURITY_FEEDBACK':
        setError(null);
        setSecurityFeedback(message);
        break;
      case 'SIGNUP_RESULT':
        if (message.success) {
          setError(null);
          setNotice("Account created. You can now log in.");
        }
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
      case 'CREATE_ROOM_RESULT':
        if (message.success) {
          setError(null);
          setRooms((prev) => [...prev.filter(room => room.id !== message.room.id), message.room]);
        } else {
          setError(message.reason);
        }
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
        setSecurityFeedback(null);
        setError(message.reason);
        break;
      default:
        console.warn("Unhandled message type:", message.type);
    }
  };

  useEffect(() => {
    let disposed = false;
    let socket;
    // Check environment variable
    const useMocks = import.meta.env.VITE_USE_MOCKS === 'true';

    if (useMocks) {
      console.log("🟢 Using MOCK WebSocket Server");
      import('./MockWebSocket').then(({ MockWebSocket }) => {
        if (disposed) return;
        socket = new MockWebSocket();
        ws.current = socket;
        setupWebSocket(socket);
      });
    } else {
      console.log("🔵 Using REAL WebSocket Server");
      socket = new WebSocket(import.meta.env.VITE_BRIDGE_URL || 'ws://127.0.0.1:9001/ws');
      ws.current = socket;
      setupWebSocket(socket);
    }

    function setupWebSocket(socket) {
      socket.onopen = () => {
        if (disposed) return;
        setIsConnected(true);
        setError(null);
        socket.send(JSON.stringify({ type: 'CONNECT' }));
      };

      socket.onclose = () => {
        if (disposed) return;
        setIsConnected(false);
        setServerConnected(false);
        setUser(null);
      };

      socket.onerror = () => {
        if (!disposed) {
          setSecurityFeedback(null);
          setError("Cannot connect to the bridge. Check its address and allowed UI origin.");
        }
      };

      socket.onmessage = (event) => {
        if (disposed) return;
        try {
          const data = JSON.parse(event.data);
          handleMessage(data);
        } catch (err) {
          console.error("Failed to parse websocket message", err);
        }
      };
    }

    return () => {
      disposed = true;
      socket?.close();
    };
  }, []);

  const sendMessage = useCallback((payload) => {
    setError(null);
    setNotice(null);
    setSecurityFeedback(null);
    if (payload.type === 'LOGIN' || payload.type === 'SIGNUP') {
      usernameRef.current = payload.username;
    }
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    } else {
      console.error("WebSocket is not connected");
      setError("Not connected to server");
    }
  }, []);

  const value = {
    isConnected,
    serverConnected,
    notice,
    user,
    rooms,
    activeRoom,
    messages,
    error,
    securityFeedback,
    sendMessage,
    setError, // allow components to clear errors if needed
    dismissSecurityFeedback: () => setSecurityFeedback(null),
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};
