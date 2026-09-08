#!/usr/bin/env python3
"""Run a live security smoke test against an already-running chat stack.

Unlike the pytest and React suites, this script uses real WebSocket connections
through the browser-facing FastAPI bridge and its upstream chat server. It
creates unique disposable users and a room, joins two clients, verifies a live
room broadcast, and then checks the integrated security contract for:

* fail-closed URL reputation feedback when VirusTotal isn't configured;
* anti-spam blocking before a message is broadcast; and
* login throttling after three failed attempts.

The server, bridge, and PostgreSQL database must already be running. Configure
the bridge endpoint with ``BRIDGE_URL`` and its allowed browser origin with
``UI_ORIGIN``. The defaults match the local development setup. The script adds
rows to the configured database and intentionally leaves them there so a human
can inspect persistence after the run; generated names contain a random suffix
and won't collide with earlier runs.

This is a smoke test, not a complete security audit. Safe/malicious VirusTotal
verdicts and the second anti-spam strike are covered by deterministic automated
tests because they require an external service or timing-sensitive behavior.
"""

import json
import os
import time
from uuid import uuid4

from websockets.sync.client import connect


BRIDGE_URL = os.environ.get("BRIDGE_URL", "ws://127.0.0.1:9001/ws")
UI_ORIGIN = os.environ.get("UI_ORIGIN", "http://127.0.0.1:5173")


def send(socket, **payload):
    """Serialize and send one UI-to-bridge protocol event."""
    socket.send(json.dumps(payload))


def receive(socket, expected_type):
    """Receive one bridge event and fail with its payload if its type differs."""
    response = json.loads(socket.recv(timeout=5))
    assert response.get("type") == expected_type, response
    return response


def connect_ui():
    """Open one browser-like bridge connection and connect it upstream."""
    socket = connect(BRIDGE_URL, origin=UI_ORIGIN, open_timeout=5, legacy=True)
    send(socket, type="CONNECT")
    receive(socket, "CONNECTED")
    return socket


def signup_and_login(socket, username, password):
    """Create a unique account and establish its authenticated server session."""
    send(socket, type="SIGNUP", username=username, password=password)
    response = receive(socket, "SIGNUP_RESULT")
    assert response["success"] is True, response

    send(socket, type="LOGIN", username=username, password=password)
    response = receive(socket, "LOGIN_RESULT")
    assert response == {"type": "LOGIN_RESULT", "success": True, "reason": None}


def main():
    """Execute chat, URL, spam, and login-throttling scenarios in sequence."""
    # Unique names make the script repeatable against a persistent developer DB.
    suffix = uuid4().hex[:10]
    password = f"smoke-{suffix}"
    alice_name = f"alice-{suffix}"
    bob_name = f"bob-{suffix}"
    room_name = f"room-{suffix}"

    alice = connect_ui()
    bob = connect_ui()
    try:
        signup_and_login(alice, alice_name, password)
        signup_and_login(bob, bob_name, password)

        # Establish a shared room so delivery can be observed by a second user.
        send(alice, type="CREATE_ROOM", name=room_name)
        created = receive(alice, "CREATE_ROOM_RESULT")
        assert created["success"] is True, created
        room_id = created["room"]["id"]

        for socket in (alice, bob):
            send(socket, type="JOIN_ROOM", room_id=room_id)
            joined = receive(socket, "JOIN_ROOM_RESULT")
            assert joined["success"] is True, joined

        send(alice, type="SEND_MESSAGE", room_id=room_id, text="hello from live smoke")
        for socket in (alice, bob):
            delivered = receive(socket, "MESSAGE_RECEIVED")
            assert delivered["text"] == "hello from live smoke", delivered
            assert delivered["sender"] == alice_name, delivered

        # No VirusTotal key is expected for this scenario. The server must fail
        # closed, while the bridge replaces backend details with a safe message.
        send(alice, type="SEND_MESSAGE", room_id=room_id, text="https://example.com")
        unavailable = receive(alice, "SECURITY_FEEDBACK")
        assert unavailable["reason"] == "SECURITY_CHECK_UNAVAILABLE", unavailable
        assert unavailable["room_id"] == room_id, unavailable
        assert "VIRUSTOTAL" not in unavailable["message"], unavailable

        # The accepted message and blocked URL attempt occupy two rate-window
        # slots. Thirteen more messages are allowed; the next one is blocked.
        for index in range(13):
            send(alice, type="SEND_MESSAGE", room_id=room_id, text=f"burst-{index}")
            for socket in (alice, bob):
                receive(socket, "MESSAGE_RECEIVED")

        send(alice, type="SEND_MESSAGE", room_id=room_id, text="burst-blocked")
        blocked = receive(alice, "SECURITY_FEEDBACK")
        assert blocked["reason"] == "SPAM_DETECTED", blocked
        assert blocked["room_id"] == room_id, blocked
    finally:
        alice.close()
        bob.close()

    # Use a fresh browser/server connection so the login test is independent of
    # the authenticated room clients and exercises the bridge's login adapter.
    throttle = connect_ui()
    try:
        missing_user = f"missing-{suffix}"
        for _ in range(2):
            send(throttle, type="LOGIN", username=missing_user, password=password)
            failed = receive(throttle, "LOGIN_RESULT")
            assert failed["reason"] == "Invalid username or password", failed

        send(throttle, type="LOGIN", username=missing_user, password=password)
        limited = receive(throttle, "SECURITY_FEEDBACK")
        assert limited["reason"] == "LOGIN_RATE_LIMITED", limited
        assert limited["retry_after_seconds"] > 0, limited
    finally:
        throttle.close()

    # Machine-readable output makes this convenient in local scripts and CI.
    print(json.dumps({
        "status": "passed",
        "room": room_name,
        "expected_persisted_messages": 14,
    }))


if __name__ == "__main__":
    main()
