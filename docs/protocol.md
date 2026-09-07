# UI - Bridge Protocol

Endpoint: `ws://127.0.0.1:9001/ws`

## UI → Bridge

### Authentication
```json
{ "type": "SIGNUP", "username": "<username>", "password": "<password>" }
```
```json
{ "type": "SIGNIN", "username": "<username>", "password": "<password>" }
```
```json
{ "type": "LOGOUT" }
```

### Connection & Status
```json
{ "type": "CONNECT" }
```
```json
{ "type": "DISCONNECT" }
```

### Rooms
```json
{ "type": "GET_ROOMS" }
```
```json
{ "type": "JOIN_ROOM", "room_id": "<room_id>" }
```
```json
{ "type": "LEAVE_ROOM", "room_id": "<room_id>" }
```

### Messaging
```json
{ "type": "SEND_MESSAGE", "room_id": "<room_id>", "text": "hello" }
```

---

## Bridge → UI

### Connection & Auth Status
```json
{ "type": "CONNECTED", "logged_in": true, "username": "<username>" }
```
```json
{ "type": "DISCONNECTED" }
```

### Auth Responses
```json
{ "type": "SIGNUP_SUCCESS" }
```
```json
{ "type": "SIGNIN_SUCCESS", "username": "<username>" }
```
```json
{ "type": "LOGOUT_SUCCESS" }
```

### Room Events
```json
{ "type": "ROOMS_LIST", "rooms": [ { "id": "room1", "name": "General" } ] }
```
```json
{ "type": "ROOM_JOINED", "room_id": "<room_id>" }
```
```json
{ "type": "ROOM_LEFT", "room_id": "<room_id>" }
```

### Messaging
```json
{ "type": "MESSAGE_RECEIVED", "room_id": "<room_id>", "from": "<username>", "text": "hello" }
```

### Error
```json
{ "type": "ERROR", "reason": "<error_message>" }
```
