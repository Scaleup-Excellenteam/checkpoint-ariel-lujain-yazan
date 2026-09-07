# UI - Bridge Protocol

Endpoint: `ws://127.0.0.1:9001/ws`

## UI → Bridge

### Connection & Status
```json
{ "type": "CONNECT" }
```
```json
{ "type": "DISCONNECT" }
```

### Authentication
```json
{ "type": "SIGNUP", "username": "<username>", "password": "<password>" }
```
```json
{ "type": "LOGIN", "username": "<username>", "password": "<password>" }
```
```json
{ "type": "LOGOUT" }
```

### Rooms
```json
{ "type": "LIST_ROOMS" }
```
```json
{ "type": "CREATE_ROOM", "name": "<room_name>" }
```
```json
{ "type": "JOIN_ROOM", "room_id": <room_id_int> }
```
```json
{ "type": "LEAVE_ROOM", "room_id": <room_id_int> }
```

### Messaging
```json
{ "type": "SEND_MESSAGE", "room_id": <room_id_int>, "text": "hello" }
```

---

## Bridge → UI

### Connection Status
```json
{ "type": "CONNECTED" }
```
```json
{ "type": "DISCONNECTED" }
```

### Auth Responses
```json
{ "type": "SIGNUP_RESULT", "success": true, "reason": "<error_message_if_false>" }
```
```json
{ "type": "LOGIN_RESULT", "success": true, "reason": "<error_message_if_false>" }
```
```json
{ "type": "LOGOUT_RESULT", "success": true }
```

### Room Events
```json
{ "type": "ROOMS_LIST", "rooms": [ { "id": 1, "name": "General" } ] }
```
```json
{ "type": "CREATE_ROOM_RESULT", "success": true, "room": { "id": 2, "name": "New Room" }, "reason": "<error_message>" }
```
```json
{ "type": "JOIN_ROOM_RESULT", "success": true, "room_id": <room_id_int>, "reason": "<error_message>" }
```
```json
{ "type": "LEAVE_ROOM_RESULT", "success": true, "room_id": <room_id_int>, "reason": "<error_message>" }
```

### Messaging
```json
{ "type": "MESSAGE_RECEIVED", "room_id": <room_id_int>, "sender": "<username>", "text": "hello" }
```

### Error
```json
{ "type": "ERROR", "reason": "<error_message>" }
```
