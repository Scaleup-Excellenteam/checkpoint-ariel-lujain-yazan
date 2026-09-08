#!/usr/bin/env python3
"""Exercise a running bridge and server with two real WebSocket clients."""

import json
import os
import time
from uuid import uuid4

from websockets.sync.client import connect


BRIDGE_URL = os.environ.get("BRIDGE_URL", "ws://127.0.0.1:9001/ws")
UI_ORIGIN = os.environ.get("UI_ORIGIN", "http://127.0.0.1:5173")


def send(socket, **payload):
    socket.send(json.dumps(payload))


def receive(socket, expected_type):
    response = json.loads(socket.recv(timeout=5))
    assert response.get("type") == expected_type, response
    return response


def connect_ui():
    socket = connect(BRIDGE_URL, origin=UI_ORIGIN, open_timeout=5, legacy=True)
    send(socket, type="CONNECT")
    receive(socket, "CONNECTED")
    return socket


def signup_and_login(socket, username, password):
    send(socket, type="SIGNUP", username=username, password=password)
    response = receive(socket, "SIGNUP_RESULT")
    assert response["success"] is True, response

    send(socket, type="LOGIN", username=username, password=password)
    response = receive(socket, "LOGIN_RESULT")
    assert response == {"type": "LOGIN_RESULT", "success": True, "reason": None}


def main():
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

    print(json.dumps({
        "status": "passed",
        "room": room_name,
        "expected_persisted_messages": 14,
    }))


if __name__ == "__main__":
    main()
