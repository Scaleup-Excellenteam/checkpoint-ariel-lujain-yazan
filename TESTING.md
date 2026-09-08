# Verification

Install dependencies and configure PostgreSQL as described in README.md.

## Automated tests

From the repository root:

```bash
.venv/bin/python -m pytest -v
npm --prefix client/ui test
npm --prefix client/ui run lint
npm --prefix client/ui run build
```

After installing dependencies, the same checks can be run with one command:

```bash
./scripts/test-security.sh
```

The Python suite includes client validation, JWT handling, bridge forwarding,
Origin validation, normalized room objects, and reconnect behavior. The
transport regression uses real loopback WebSockets with a test protocol peer.
It does not use the real server or PostgreSQL. Tests require local socket and
thread access; restrictive sandboxes can hang the FastAPI test infrastructure.

The React tests render the real provider and pages with a fake browser socket.
They check that room responses don't cause repeated LIST_ROOMS requests,
created rooms can be joined using their numeric ID, and the browser connection
remains usable after logout. StrictMode may run the initial mount effect twice;
receiving results must not cause continuing requests.

These tests do not establish full end-to-end success. Use the following real
scenario with `VITE_USE_MOCKS=false` and all three services running.

## Manual two-client scenario

1. Open two tabs at http://127.0.0.1:5173 (A and B).
2. A: sign up with a new username. Confirm the success notice, then log in.
3. A: create a uniquely named room. Confirm its numeric ID and click Join Room.
4. B: sign up as a different user, then log in. Refresh Rooms if needed and
   join the same room ID.
5. A: send a unique message. Both tabs must receive it with A's username.
6. B: reply. Both tabs must receive the reply with B's username.
7. A: Leave Room, then Logout. Log in again without reloading the tab, rejoin
   the room, and send another message. B must receive it.
8. Try a duplicate username, wrong password, and duplicate room name. Confirm
   understandable errors and that valid actions still work afterward.
9. Inspect browser WebSocket traffic: room-list responses must not trigger
   continuous LIST_ROOMS requests, and LOGIN_RESULT must not expose a token.
10. Optionally inspect PostgreSQL to confirm persisted users, membership, and
    messages. Rejoining currently shows new live messages, not stored history.

## Manual security scenarios

Run these with the real server, bridge, UI, and PostgreSQL described above.

1. Log out, then submit the same wrong username/password three times. The third
   attempt must show an `Action blocked` notice with `LOGIN_RATE_LIMITED` and a
   retry time. Attempts before the limit must remain normal login errors.
2. After logging in and joining a room, send 16 short messages inside five
   seconds. The sixteenth must be blocked with `SPAM_DETECTED`, must not appear
   for another member, and must not be stored. Wait five seconds and confirm a
   normal message works. A second burst inside 120 seconds disconnects the
   sender; the block reason must remain visible on the login screen.
3. With `VIRUSTOTAL_API_KEY` unset, send a message containing an `http://` or
   `https://` URL. It must fail closed with `SECURITY_CHECK_UNAVAILABLE`, and
   the browser must not display provider details. Plain text must still work.
4. With a working VirusTotal key, confirm a known-clean URL is delivered. Test
   malicious verdicts only with a safe test URL or a mocked provider response;
   do not browse to a malicious URL.

Database availability, credentials, schema, firewall rules, and two-browser
message delivery must be verified separately from the automated tests.
