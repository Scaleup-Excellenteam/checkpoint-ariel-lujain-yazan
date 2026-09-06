# Client UI Protocol

This document defines the communication protocol between the UI and the Python client backend.

The UI communicates with the Python backend through a local WebSocket connection.

## Local WebSocket

```text
ws://127.0.0.1:9001/ws
```

The UI does not communicate directly with the remote server.

The communication flow is:

```text
UI
↓
bridge.py
↓
client.py
↓
Server
```

---

## UI -> Bridge

### CONNECT

The UI sends this message when the user clicks the Connect button.

```json
{
  "type": "CONNECT"
}
```

---

### SEND_MESSAGE

The UI sends this message when the user sends a chat message.

```json
{
  "type": "SEND_MESSAGE",
  "text": "Hello"
}
```

Fields:

- `type` - must be `SEND_MESSAGE`
- `text` - the message text to send

The message text must not be empty.

---

### DISCONNECT

The UI sends this message when the user disconnects.

```json
{
  "type": "DISCONNECT"
}
```

---

## Bridge -> UI

### CONNECTED

Sent when the Python client successfully connects to the remote server.

```json
{
  "type": "CONNECTED"
}
```

---

### MESSAGE_RECEIVED

Sent when a message is received from the remote server.

```json
{
  "type": "MESSAGE_RECEIVED",
  "text": "Hello"
}
```

Fields:

- `type` - `MESSAGE_RECEIVED`
- `text` - the received message

---

### DISCONNECTED

Sent when the Python client disconnects from the remote server.

```json
{
  "type": "DISCONNECTED"
}
```

---

### ERROR

Sent when an error occurs.

```json
{
  "type": "ERROR",
  "reason": "Error description"
}
```

Fields:

- `type` - `ERROR`
- `reason` - a description of the error

Examples:

```json
{
  "type": "ERROR",
  "reason": "Not connected to the server."
}
```

```json
{
  "type": "ERROR",
  "reason": "Already connected to the server."
}
```

```json
{
  "type": "ERROR",
  "reason": "Unknown request type"
}
```

---

## Responsibilities

### UI

The UI is responsible for:

- Opening the local WebSocket connection to `bridge.py`
- Sending JSON requests
- Displaying received messages
- Updating the screen according to `CONNECTED`, `DISCONNECTED`, and `ERROR` events

### bridge.py

The bridge is responsible for:

- Receiving JSON messages from the UI
- Translating UI requests into `ChatClient` operations
- Translating `ChatClient` callbacks into JSON messages for the UI

### client.py

The client is responsible for:

- Connecting to the remote server
- Sending chat messages
- Receiving chat messages
- Disconnecting from the server
- Detecting connection errors
- Maintaining the WebSocket connection with Ping/Pong heartbeat