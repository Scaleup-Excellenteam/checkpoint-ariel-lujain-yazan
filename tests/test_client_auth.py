import json

import pytest

from client.network import client as client_module
from client.network.client import ChatClient, MAX_TOKEN_LENGTH


class FakeReceiveWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)

    def recv(self):
        if self.messages:
            return self.messages.pop(0)
        raise RuntimeError("stop test loop")


class FakeClosableWebSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_login_sends_expected_json():
    sent = []
    client = ChatClient("ws://test")
    client.websocket = object()
    client.send_message = sent.append

    client.login("  lujain  ", "secret")

    assert len(sent) == 1
    assert json.loads(sent[0]) == {
        "type": "LOGIN",
        "username": "lujain",
        "password": "secret",
    }


def test_signup_sends_expected_json():
    sent = []
    client = ChatClient("ws://test")
    client.websocket = object()
    client.send_message = sent.append

    client.signup("  new_user  ", "secret")

    assert len(sent) == 1
    assert json.loads(sent[0]) == {
        "type": "SIGNUP",
        "username": "new_user",
        "password": "secret",
    }


def test_failed_login_clears_existing_token():
    errors = []
    client = ChatClient("ws://test", on_error=errors.append)
    client.token = "old-token"

    client.login("", "secret")

    assert client.token is None
    assert errors == ["Invalid username."]


def test_successful_login_result_stores_valid_token():
    received = []
    errors = []
    token = "valid.jwt.token"

    client = ChatClient(
        "ws://test",
        on_message=received.append,
        on_error=errors.append,
    )
    client.websocket = FakeReceiveWebSocket([
        json.dumps({
            "type": "LOGIN_RESULT",
            "success": True,
            "token": token,
        })
    ])

    client.receive_messages()

    assert client.token == token
    assert json.loads(received[0])["success"] is True


def test_failed_login_result_clears_previous_token():
    client = ChatClient("ws://test", on_error=lambda _: None)
    client.token = "old-token"
    client.websocket = FakeReceiveWebSocket([
        json.dumps({
            "type": "LOGIN_RESULT",
            "success": False,
            "reason": "Invalid credentials",
        })
    ])

    client.receive_messages()

    assert client.token is None


def test_invalid_token_is_not_accepted_and_result_becomes_failure():
    received = []
    client = ChatClient(
        "ws://test",
        on_message=received.append,
        on_error=lambda _: None,
    )
    client.websocket = FakeReceiveWebSocket([
        json.dumps({
            "type": "LOGIN_RESULT",
            "success": True,
            "token": "x" * (MAX_TOKEN_LENGTH + 1),
        })
    ])

    client.receive_messages()

    assert client.token is None

    forwarded = json.loads(received[0])
    assert forwarded["success"] is False
    assert forwarded["reason"] == "Invalid authentication token"
    assert "token" in forwarded


def test_security_decision_passes_through_client_unchanged():
    received = []
    payload = {
        "type": "SECURITY_RESULT",
        "action": "BLOCK",
        "reason": "SENSITIVE_CONTENT",
        "room_id": 7,
    }
    client = ChatClient(
        "ws://test",
        on_message=received.append,
        on_error=lambda _: None,
    )
    client.websocket = FakeReceiveWebSocket([json.dumps(payload)])

    client.receive_messages()

    assert json.loads(received[0]) == payload


def test_logout_clears_token_and_disconnects():
    websocket = FakeClosableWebSocket()
    client = ChatClient("ws://test")
    client.token = "jwt-token"
    client.websocket = websocket

    client.logout()

    assert client.token is None
    assert websocket.closed is True
    assert client.websocket is None


def test_send_authenticated_json_does_not_mutate_original_payload():
    sent = []
    client = ChatClient("ws://test")
    client.token = "jwt-token"
    client.websocket = object()
    client.send_message = sent.append

    original = {
        "type": "JOIN_ROOM",
        "room_id": 7,
    }

    client.send_authenticated_json(original)

    assert original == {
        "type": "JOIN_ROOM",
        "room_id": 7,
    }

    assert json.loads(sent[0]) == {
        "type": "JOIN_ROOM",
        "room_id": 7,
        "token": "jwt-token",
    }


def test_send_json_rejects_non_dict():
    errors = []
    client = ChatClient("ws://test", on_error=errors.append)
    client.websocket = object()

    client.send_json(["not", "a", "dict"])

    assert errors == ["Invalid request format."]


def test_connect_rejects_duplicate_connection():
    errors = []
    client = ChatClient("ws://test", on_error=errors.append)
    client.websocket = object()

    client.connect()

    assert errors == ["Already connected to the server."]


def test_connect_uses_security_limits(monkeypatch):
    captured = {}

    class DummyWebSocket:
        pass

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            pass

    def fake_connect(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return DummyWebSocket()

    monkeypatch.setattr(client_module, "websocket_connect", fake_connect)
    monkeypatch.setattr(client_module, "Thread", FakeThread)

    client = ChatClient("ws://example.test")
    client.connect()

    assert captured["url"] == "ws://example.test"
    assert captured["open_timeout"] == 10
    assert captured["close_timeout"] == 10
    assert captured["max_size"] == 64 * 1024
    assert captured["max_queue"] == 16
    assert captured["compression"] is None


@pytest.mark.parametrize("operation", ["login", "signup"])
def test_auth_connects_only_when_needed(operation):
    client = ChatClient("ws://test")
    calls = []
    socket = FakeClosableWebSocket()
    def connect():
        calls.append("connect")
        client.websocket = socket
    client.connect = connect
    client.send_message = lambda message: calls.append(json.loads(message)["type"])
    getattr(client, operation)("user", "password")
    getattr(client, operation)("user", "password")
    assert calls == ["connect", operation.upper(), operation.upper()]
    client.logout()
    getattr(client, operation)("user", "password")
    assert calls[-2:] == ["connect", operation.upper()]


def test_failed_reconnect_does_not_send_login():
    client = ChatClient("ws://test")
    sent = []
    client.connect = lambda: None
    client.send_message = sent.append
    client.login("user", "password")
    assert sent == []
