import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-login-throttling-tests")

from starlette.websockets import WebSocketDisconnect

from server import index as server


class FakeWebSocket:
    def __init__(self, requests, host="127.0.0.1"):
        self.requests = list(requests)
        self.sent = []
        self.client = SimpleNamespace(host=host)

    async def accept(self):
        pass

    async def receive_json(self):
        if self.requests:
            return self.requests.pop(0)
        raise WebSocketDisconnect()

    async def send_json(self, data):
        self.sent.append(data)


class FakeDbPool:
    def __init__(self):
        self.users = {
            "alice": {
                "id": 1,
                "password_hash": "correct-hash",
            },
            "bob": {
                "id": 2,
                "password_hash": "correct-hash",
            },
        }

    async def fetchrow(self, query, username):
        return self.users.get(username)


def login_request(username="alice", password="wrong"):
    return {
        "type": "LOGIN",
        "username": username,
        "password": password,
    }


def run_login_sequence(monkeypatch, requests, host="127.0.0.1", now=1000.0):
    current_time = {"value": now}
    monkeypatch.setattr(server, "monotonic", lambda: current_time["value"])
    monkeypatch.setattr(
        server,
        "verify_password",
        lambda password, password_hash: password == "correct",
    )
    monkeypatch.setattr(
        server,
        "create_access_token",
        lambda user_id: f"token-for-{user_id}",
    )
    server.app.state.db_pool = FakeDbPool()
    websocket = FakeWebSocket(requests, host=host)

    asyncio.run(server.websocket_endpoint(websocket))

    return websocket, current_time


def assert_invalid_login(response):
    assert response == {
        "type": "LOGIN_RESULT",
        "success": False,
        "reason": "Invalid username or password",
    }


def assert_rate_limited(response):
    assert response["type"] == "LOGIN_RESULT"
    assert response["success"] is False
    assert response["reason"] == "LOGIN_RATE_LIMITED"
    assert response["retry_after_seconds"] > 0


def setup_function():
    server.login_attempts.clear()
    server.active_connections.clear()
    server.connection_users.clear()


def test_wrong_login_1_returns_normal_invalid_response(monkeypatch):
    websocket, _ = run_login_sequence(monkeypatch, [login_request()])

    assert_invalid_login(websocket.sent[0])


def test_wrong_login_2_returns_normal_invalid_response(monkeypatch):
    websocket, _ = run_login_sequence(monkeypatch, [
        login_request(),
        login_request(),
    ])

    assert_invalid_login(websocket.sent[0])
    assert_invalid_login(websocket.sent[1])


def test_wrong_login_3_starts_cooldown(monkeypatch):
    websocket, _ = run_login_sequence(monkeypatch, [
        login_request(),
        login_request(),
        login_request(),
    ])

    assert_invalid_login(websocket.sent[0])
    assert_invalid_login(websocket.sent[1])
    assert_rate_limited(websocket.sent[2])


def test_login_during_cooldown_is_blocked_immediately(monkeypatch):
    websocket, _ = run_login_sequence(monkeypatch, [
        login_request(),
        login_request(),
        login_request(),
        login_request(password="correct"),
    ])

    assert_rate_limited(websocket.sent[2])
    assert_rate_limited(websocket.sent[3])


def test_retry_after_seconds_is_returned(monkeypatch):
    websocket, _ = run_login_sequence(monkeypatch, [
        login_request(),
        login_request(),
        login_request(),
    ])

    assert "retry_after_seconds" in websocket.sent[2]
    assert websocket.sent[2]["retry_after_seconds"] == 60


def test_login_works_again_after_cooldown(monkeypatch):
    current_time = {"value": 1000.0}
    monkeypatch.setattr(server, "monotonic", lambda: current_time["value"])
    monkeypatch.setattr(
        server,
        "verify_password",
        lambda password, password_hash: password == "correct",
    )
    monkeypatch.setattr(
        server,
        "create_access_token",
        lambda user_id: f"token-for-{user_id}",
    )
    server.app.state.db_pool = FakeDbPool()

    websocket = FakeWebSocket([
        login_request(),
        login_request(),
        login_request(),
    ])
    asyncio.run(server.websocket_endpoint(websocket))

    current_time["value"] = 1061.0
    websocket = FakeWebSocket([login_request(password="correct")])
    asyncio.run(server.websocket_endpoint(websocket))

    assert websocket.sent[0] == {
        "type": "LOGIN_RESULT",
        "success": True,
        "token": "token-for-1",
    }


def test_successful_login_resets_counter(monkeypatch):
    websocket, _ = run_login_sequence(monkeypatch, [
        login_request(),
        login_request(password="correct"),
        login_request(),
        login_request(),
    ])

    assert_invalid_login(websocket.sent[0])
    assert websocket.sent[1]["success"] is True
    assert_invalid_login(websocket.sent[2])
    assert_invalid_login(websocket.sent[3])


def test_another_ip_username_pair_is_not_blocked(monkeypatch):
    run_login_sequence(monkeypatch, [
        login_request(),
        login_request(),
        login_request(),
    ])

    websocket, _ = run_login_sequence(
        monkeypatch,
        [login_request(username="bob", password="correct")],
        host="203.0.113.10",
    )

    assert websocket.sent[0] == {
        "type": "LOGIN_RESULT",
        "success": True,
        "token": "token-for-2",
    }
