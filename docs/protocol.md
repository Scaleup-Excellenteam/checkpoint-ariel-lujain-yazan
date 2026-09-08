# UI - Bridge Protocol

Endpoint: `ws://127.0.0.1:9001/ws` (UI override: `VITE_BRIDGE_URL`).

Development UI: `http://127.0.0.1:5173`. Bridge origins are configured with
`CHAT_UI_ORIGINS` (comma-separated exact origins); localhost ports 5173 and
5500 are allowed by default.

Room objects at this boundary always use `{ "id": 1, "name": "General" }`.
The bridge translates the server's `room_id` object field to `id`. Command
parameters and message events still use `room_id` as a positive integer.

`CONNECTED` means the upstream server socket opened. The browser socket can
remain open across `LOGOUT`: the client clears its JWT and closes the upstream
socket, and the bridge returns `LOGOUT_RESULT`. A later `LOGIN` or `SIGNUP`
reconnects upstream if needed before sending credentials. Signup does not log
in automatically. JWTs remain in the Python client, never in the browser.

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

### Security feedback contract

Blocked security decisions include `"action": "BLOCK"`, a stable `source`, and
a stable reason code. Message-related blocks also include the requested
`room_id`; login throttling remains a `LOGIN_RESULT` so existing login handling
still applies.

```json
{ "type": "LOGIN_RESULT", "success": false, "source": "LOGIN_THROTTLING", "action": "BLOCK", "reason": "LOGIN_RATE_LIMITED", "retry_after_seconds": 60 }
```
```json
{ "type": "SECURITY_RESULT", "source": "ANTI_SPAM", "action": "BLOCK", "reason": "SPAM_DETECTED", "room_id": 1 }
```
```json
{ "type": "SECURITY_RESULT", "source": "URL_REPUTATION", "action": "BLOCK", "reason": "MALICIOUS_URL", "room_id": 1 }
```

If URL reputation checking is unavailable, the response uses
`SECURITY_CHECK_UNAVAILABLE` with source `URL_REPUTATION`. This allows clients
to show a generic safe failure message without exposing provider details.

### Error
```json
{ "type": "ERROR", "reason": "<error_message>" }
```
