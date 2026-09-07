import asyncio
import os
from types import SimpleNamespace

from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-url-reputation-tests")

from server import index as server


class FakeWebSocket:
    def __init__(self, requests=None, host="127.0.0.1"):
        self.requests = list(requests or [])
        self.sent = []
        self.closed = False
        self.close_code = None
        self.client = SimpleNamespace(host=host)

    async def accept(self):
        pass

    async def receive_json(self):
        while self.requests:
            return self.requests.pop(0)
        raise WebSocketDisconnect()

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = True
        self.close_code = code


class FakeDbPool:
    def __init__(self):
        self.memberships = {
            (1, 10),
            (2, 10),
        }
        self.usernames = {
            1: "alice",
            2: "bob",
        }
        self.messages = []

    async def fetchval(self, query, *args):
        if "FROM room_members" in query:
            user_id, room_id = args
            return 1 if (user_id, room_id) in self.memberships else None

        if "SELECT username" in query:
            (user_id,) = args
            return self.usernames[user_id]

        raise AssertionError(f"Unexpected fetchval query: {query}")

    async def fetch(self, query, *args):
        if "FROM room_members" in query:
            (room_id,) = args
            return [
                {"user_id": user_id}
                for user_id, member_room_id in self.memberships
                if member_room_id == room_id
            ]

        raise AssertionError(f"Unexpected fetch query: {query}")

    async def execute(self, query, *args):
        if "INSERT INTO messages" in query:
            room_id, user_id, text = args
            self.messages.append({
                "room_id": room_id,
                "user_id": user_id,
                "text": text,
            })
            return

        raise AssertionError(f"Unexpected execute query: {query}")


def send_message(text, token="token-1", room_id=10):
    return {
        "type": "SEND_MESSAGE",
        "token": token,
        "room_id": room_id,
        "text": text,
    }


def vt_report(malicious=0, suspicious=0, harmless=8, undetected=2, timeout=0):
    return {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": malicious,
                    "suspicious": suspicious,
                    "harmless": harmless,
                    "undetected": undetected,
                    "timeout": timeout,
                }
            }
        }
    }


def setup_function():
    server.active_connections.clear()
    server.connection_users.clear()
    server.message_rate_windows.clear()
    server.spam_strikes.clear()
    server.url_reputation_cache.clear()


def run_messages(monkeypatch, requests, reports=None, side_effect=None):
    db = FakeDbPool()
    calls = []
    reports = reports or {}

    async def fake_fetch(url, api_key):
        calls.append((url, api_key))

        if side_effect is not None:
            raise side_effect

        return reports.get(url, vt_report())

    monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-api-key")
    monkeypatch.setattr(server, "fetch_virustotal_url_report", fake_fetch)
    monkeypatch.setattr(
        server,
        "verify_access_token",
        lambda token: {"token-1": 1, "token-2": 2}.get(token),
    )
    server.app.state.db_pool = db

    websocket = FakeWebSocket(requests)
    server.connection_users[websocket] = 1

    asyncio.run(server.websocket_endpoint(websocket))

    return websocket, db, calls


def security_results(websocket):
    return [
        response
        for response in websocket.sent
        if response.get("type") == "SECURITY_RESULT"
    ]


def message_broadcasts(websocket):
    return [
        response
        for response in websocket.sent
        if response.get("type") == "MESSAGE"
    ]


def test_message_without_url_works_normally(monkeypatch):
    websocket, db, calls = run_messages(monkeypatch, [send_message("hello")])

    assert calls == []
    assert db.messages == [{"room_id": 10, "user_id": 1, "text": "hello"}]
    assert len(message_broadcasts(websocket)) == 1
    assert security_results(websocket) == []


def test_safe_url_is_allowed(monkeypatch):
    websocket, db, calls = run_messages(
        monkeypatch,
        [send_message("see https://example.com/path")],
        reports={"https://example.com/path": vt_report(malicious=1, harmless=63)},
    )

    assert calls == [("https://example.com/path", "test-api-key")]
    assert len(db.messages) == 1
    assert len(message_broadcasts(websocket)) == 1
    assert security_results(websocket) == []


def test_malicious_url_is_blocked(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message("see https://bad.example")],
        reports={"https://bad.example": vt_report(malicious=3)},
    )

    assert db.messages == []
    assert security_results(websocket) == [{
        "type": "SECURITY_RESULT",
        "source": "URL_REPUTATION",
        "action": "BLOCK",
        "reason": "MALICIOUS_URL",
        "message": "This message was blocked because it contains a URL reported as malicious.",
    }]


def test_blocked_url_message_is_not_saved(monkeypatch):
    _, db, _ = run_messages(
        monkeypatch,
        [send_message("blocked https://bad.example")],
        reports={"https://bad.example": vt_report(malicious=3)},
    )

    assert db.messages == []


def test_blocked_url_message_is_not_broadcast(monkeypatch):
    recipient = FakeWebSocket()
    server.active_connections.append(recipient)
    server.connection_users[recipient] = 2

    websocket, _, _ = run_messages(
        monkeypatch,
        [send_message("blocked https://bad.example")],
        reports={"https://bad.example": vt_report(malicious=3)},
    )

    assert message_broadcasts(websocket) == []
    assert message_broadcasts(recipient) == []


def test_multiple_urls_one_malicious_url_blocks_whole_message(monkeypatch):
    websocket, db, calls = run_messages(
        monkeypatch,
        [send_message("https://safe.example then https://bad.example")],
        reports={
            "https://safe.example": vt_report(malicious=0),
            "https://bad.example": vt_report(malicious=10, suspicious=3),
        },
    )

    assert calls == [
        ("https://safe.example", "test-api-key"),
        ("https://bad.example", "test-api-key"),
    ]
    assert db.messages == []
    assert security_results(websocket)[0]["reason"] == "MALICIOUS_URL"


def test_virustotal_timeout_follows_failure_policy(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message("check https://slow.example")],
        side_effect=TimeoutError("timed out"),
    )

    assert db.messages == []
    assert security_results(websocket) == [{
        "type": "SECURITY_RESULT",
        "source": "URL_REPUTATION",
        "action": "BLOCK",
        "reason": "URL_REPUTATION_UNAVAILABLE",
        "message": "This message contains a URL that could not be verified right now. Please try again later.",
    }]


def test_malformed_unknown_response_follows_failure_policy(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message("check https://unknown.example")],
        reports={"https://unknown.example": {"data": {"attributes": {}}}},
    )

    assert db.messages == []
    assert security_results(websocket)[0]["reason"] == "URL_REPUTATION_UNAVAILABLE"


def test_cached_url_avoids_duplicate_reputation_calls(monkeypatch):
    websocket, db, calls = run_messages(
        monkeypatch,
        [
            send_message("first https://example.com"),
            send_message("second HTTPS://EXAMPLE.COM"),
        ],
        reports={"https://example.com": vt_report(malicious=0)},
    )

    assert calls == [("https://example.com", "test-api-key")]
    assert len(db.messages) == 2
    assert security_results(websocket) == []


def test_other_users_server_remain_usable_after_url_block(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [
            send_message("blocked https://bad.example", token="token-1"),
            send_message("bob can still send", token="token-2"),
        ],
        reports={"https://bad.example": vt_report(malicious=3)},
    )

    assert db.messages == [{
        "room_id": 10,
        "user_id": 2,
        "text": "bob can still send",
    }]
    assert len(security_results(websocket)) == 1
    assert len(message_broadcasts(websocket)) == 1
