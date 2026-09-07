export class MockWebSocket {
  constructor() {
    this.readyState = 1; // 1 is WebSocket.OPEN
    this.onmessage = null;
    this.onopen = null;
    this.onclose = null;
    this.onerror = null;
    
    // We need a place to remember the user's name for echoes
    this.mockUsername = 'User';

    // Simulate connection delay
    setTimeout(() => {
      if (this.onopen) this.onopen();
      
      // The protocol doesn't explicitly require CONNECTED immediately without auth, 
      // but it's good practice. The mock will just wait for SIGNIN.
    }, 500);
  }

  triggerMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) });
    }
  }

  close() {
    this.readyState = 3; // CLOSED
    if (this.onclose) this.onclose();
  }

  send(dataString) {
    const data = JSON.parse(dataString);
    
    // Simulate network latency (300ms)
    setTimeout(() => {
      switch (data.type) {
        case 'LOGIN':
        case 'SIGNUP':
          if (data.username && data.password) {
            this.mockUsername = data.username;
            this.triggerMessage({ type: data.type === 'LOGIN' ? 'LOGIN_RESULT' : 'SIGNUP_RESULT', success: true });
          } else {
            this.triggerMessage({ type: 'ERROR', reason: 'Invalid credentials provided to mock server.' });
          }
          break;
        case 'LOGOUT':
          this.triggerMessage({ type: 'LOGOUT_RESULT', success: true });
          break;
        case 'LIST_ROOMS':
          this.triggerMessage({
            type: 'ROOMS_LIST',
            rooms: [
              { id: 1, name: 'General Chat' },
              { id: 2, name: 'Random' },
              { id: 3, name: 'Help & Support' }
            ]
          });
          break;
        case 'JOIN_ROOM':
          this.triggerMessage({ type: 'JOIN_ROOM_RESULT', success: true, room_id: data.room_id });
          // Add a fake welcome message from the mock server shortly after joining
          setTimeout(() => {
            this.triggerMessage({
              type: 'MESSAGE_RECEIVED',
              room_id: data.room_id,
              sender: 'System',
              text: `Welcome to room ${data.room_id}!`
            });
          }, 300);
          break;
        case 'LEAVE_ROOM':
          this.triggerMessage({ type: 'LEAVE_ROOM_RESULT', success: true, room_id: data.room_id });
          break;
        case 'SEND_MESSAGE':
          // Echo the message back to the UI so it shows up in chat
          this.triggerMessage({
            type: 'MESSAGE_RECEIVED',
            room_id: data.room_id,
            sender: this.mockUsername,
            text: data.text
          });
          
          // Easter egg: If you say 'hello', MockBot replies!
          if (data.text.toLowerCase().includes('hello')) {
            setTimeout(() => {
              this.triggerMessage({
                type: 'MESSAGE_RECEIVED',
                room_id: data.room_id,
                sender: 'MockBot',
                text: 'Hi there! I am a fake bot.'
              });
            }, 1000);
          }
          break;
        default:
          console.warn('Mock server received unknown message:', data);
      }
    }, 300);
  }
}
