# UI - Bridge Protocol

Endpoint: `ws://127.0.0.1:9001/ws`

## UI → Bridge

### Connect
```json
{ "type": "CONNECT" }
```

### Send Message
```json
{ "type": "SEND_MESSAGE", "text": "hello" }
```

### Disconnect
```json
{ "type": "DISCONNECT" }
```

---

## Bridge → UI

### Connected
```json
{ "type": "CONNECTED" }
```

### Disconnected
```json
{ "type": "DISCONNECTED" }
```

### Message Received
```json
{ "type": "MESSAGE_RECEIVED", "text": "hello" }
```

### Error
```json
{ "type": "ERROR", "reason": "<error_message>" }
```
