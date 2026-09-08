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

### Security Feedback (Provisional Lujain-Side Adapter)

`SECURITY_FEEDBACK` is an internal Bridge-to-React adapter event. Ariel and
Yazan do not need to emit this `type` from the server. The current bridge
provisionally recognizes an upstream response with `"action": "BLOCK"` and
converts it to a sanitized UI event. For compatibility with the login
throttling backend, it also recognizes only a failed `LOGIN_RESULT` whose
reason is `LOGIN_RATE_LIMITED`, even if that response has no `action` field.
All other ordinary login failures remain `LOGIN_RESULT` events. It also quietly
ignores the provisional
standalone `{ "type": "SECURITY_RESULT", "action": "ALLOW" }` shape.
Recognized Day 1 event types continue through their normal handlers even when
they contain `"action": "ALLOW"`; unrelated unknown events remain protocol
errors.

The final Server-to-ChatClient security event type, `action` semantics, and
allowed `source` values still require team agreement. This section documents
only the adapter currently implemented on Lujain's branch; it does not finalize
the team-wide Day 2 security contract. The bridge supplies the safe `message`
and does not forward an upstream message or unknown reason. The optional
upstream `source` field is not forwarded while its contract remains undecided.

For example, this provisional upstream login cooldown response:

```json
{
  "type": "LOGIN_RESULT",
  "success": false,
  "action": "BLOCK",
  "reason": "LOGIN_RATE_LIMITED",
  "retry_after_seconds": 30
}
```

becomes this internal Bridge-to-React event:

```json
{
  "type": "SECURITY_FEEDBACK",
  "action": "BLOCK",
  "reason": "LOGIN_RATE_LIMITED",
  "message": "Too many login attempts. Please wait before trying again.",
  "retry_after_seconds": 30
}
```

Supported reason codes are `SENSITIVE_CONTENT`, `MALICIOUS_URL`,
`LOGIN_RATE_LIMITED`, `SPAM_DETECTED`, `INVALID_INPUT`, and
`SECURITY_CHECK_UNAVAILABLE`. The legacy backend reason
`URL_REPUTATION_UNAVAILABLE` is normalized to
`SECURITY_CHECK_UNAVAILABLE`; it is not exposed to the browser. Unknown codes
become
`UNKNOWN_SECURITY_REASON` with a generic message. `retry_after_seconds` is
included only when it is a non-negative integer; `room_id` is included only
when it is a positive integer. Both fields are optional.

For room-related feedback, a provisional upstream event may include room
context:

```json
{
  "type": "SECURITY_RESULT",
  "action": "BLOCK",
  "reason": "SPAM_DETECTED",
  "room_id": 7
}
```

`SPAM_DETECTED` plus `room_id` identifies the context of the feedback; it does
not prove that server-side membership removal occurred. An explicit membership
removal event or field is still pending from Yazan and the team agreement. The
UI must not clear its active room from this payload alone.

### Error
```json
{ "type": "ERROR", "reason": "<error_message>" }
```
