import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-anti-spam-tests")

from starlette.websockets import WebSocketDisconnect

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
            request = self.requests.pop(0)
            if callable(request):
                request()
                continue
            return request
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
            (1, 20),
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


def send_message(room_id=10, text="hello", token="token-1"):
    return {
        "type": "SEND_MESSAGE",
        "token": token,
        "room_id": room_id,
        "text": text,
    }


def setup_function():
    server.active_connections.clear()
    server.connection_users.clear()
    server.message_rate_windows.clear()
    server.spam_strikes.clear()


def run_messages(monkeypatch, requests, current_time=None, db=None, user_id_by_token=None):
    current_time = current_time or {"value": 1000.0}
    db = db or FakeDbPool()
    user_id_by_token = user_id_by_token or {
        "token-1": 1,
        "token-2": 2,
    }

    monkeypatch.setattr(server, "monotonic", lambda: current_time["value"])
    monkeypatch.setattr(
        server,
        "verify_access_token",
        lambda token: user_id_by_token.get(token),
    )
    server.app.state.db_pool = db

    websocket = FakeWebSocket(requests)
    server.connection_users[websocket] = user_id_by_token["token-1"]

    asyncio.run(server.websocket_endpoint(websocket))

    return websocket, db, current_time


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


def assert_spam_block(response):
    assert response["type"] == "SECURITY_RESULT"
    assert response["source"] == "ANTI_SPAM"
    assert response["action"] == "BLOCK"
    assert response["reason"] == "SPAM_DETECTED"
    assert "message" in response


def test_normal_messaging_below_threshold_is_allowed(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(14)],
    )

    assert len(db.messages) == 14
    assert len(message_broadcasts(websocket)) == 14
    assert security_results(websocket) == []
    assert websocket.closed is False


def test_exactly_15_messages_in_5_seconds_are_allowed(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(15)],
    )

    assert len(db.messages) == 15
    assert len(message_broadcasts(websocket)) == 15
    assert security_results(websocket) == []


def test_message_16_is_blocked(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(16)],
    )

    assert len(db.messages) == 15
    assert len(message_broadcasts(websocket)) == 15
    assert len(security_results(websocket)) == 1
    assert_spam_block(security_results(websocket)[0])


def test_first_violation_does_not_save_or_broadcast(monkeypatch):
    recipient = FakeWebSocket()
    server.active_connections.append(recipient)
    server.connection_users[recipient] = 2

    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(16)],
    )

    assert [message["text"] for message in db.messages] == [
        f"message-{index}" for index in range(15)
    ]
    assert [message["text"] for message in message_broadcasts(recipient)] == [
        f"message-{index}" for index in range(15)
    ]
    assert "message-15" not in [
        message["text"] for message in message_broadcasts(websocket)
    ]


def test_first_violation_keeps_user_connected(monkeypatch):
    websocket, _, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(16)],
    )

    assert websocket.closed is False
    assert len(security_results(websocket)) == 1


def test_messages_during_5_second_spam_cooldown_are_blocked(monkeypatch):
    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(16)]
        + [send_message(text="during-cooldown")],
    )

    assert len(db.messages) == 15
    assert len(security_results(websocket)) == 2
    assert "during-cooldown" not in [
        message["text"] for message in db.messages
    ]
    assert websocket.closed is False


def test_messages_during_5_second_spam_cooldown_do_not_create_second_strike(monkeypatch):
    websocket, _, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(16)]
        + [send_message(text=f"during-cooldown-{index}") for index in range(3)],
    )

    assert len(security_results(websocket)) == 4
    assert websocket.closed is False
    assert server.spam_strikes[1]["count"] == 1


def test_after_5_second_cooldown_user_can_message_again(monkeypatch):
    current_time = {"value": 1000.0}

    def advance_past_cooldown():
        current_time["value"] += server.ANTI_SPAM_COOLDOWN_SECONDS

    websocket, db, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(16)]
        + [advance_past_cooldown, send_message(text="after-cooldown")],
        current_time=current_time,
    )

    assert len(security_results(websocket)) == 1
    assert db.messages[-1]["text"] == "after-cooldown"
    assert websocket.closed is False


def test_later_second_spam_burst_within_120_seconds_disconnects_user(monkeypatch):
    current_time = {"value": 1000.0}

    def advance_past_cooldown():
        current_time["value"] += server.ANTI_SPAM_COOLDOWN_SECONDS

    requests = [send_message(text=f"first-burst-{index}") for index in range(16)]
    requests.append(advance_past_cooldown)
    requests.extend(
        send_message(text=f"second-burst-{index}")
        for index in range(16)
    )

    websocket, db, _ = run_messages(
        monkeypatch,
        requests,
        current_time=current_time,
    )

    assert len(db.messages) == 30
    assert len(security_results(websocket)) == 2
    assert websocket.closed is True
    assert websocket.close_code == 1008
    assert websocket not in server.active_connections
    assert websocket not in server.connection_users


def test_switching_rooms_does_not_bypass_global_user_limit(monkeypatch):
    requests = [
        send_message(room_id=10, text=f"room-10-{index}")
        for index in range(8)
    ]
    requests.extend(
        send_message(room_id=20, text=f"room-20-{index}")
        for index in range(8)
    )

    websocket, db, _ = run_messages(monkeypatch, requests)

    assert len(db.messages) == 15
    assert db.messages[-1]["room_id"] == 20
    assert len(security_results(websocket)) == 1


def test_another_user_is_unaffected(monkeypatch):
    requests = [send_message(text=f"alice-{index}") for index in range(16)]
    requests.append(send_message(text="bob-message", token="token-2"))

    websocket, db, _ = run_messages(monkeypatch, requests)

    assert db.messages[-1] == {
        "room_id": 10,
        "user_id": 2,
        "text": "bob-message",
    }
    assert len(db.messages) == 16
    assert len(security_results(websocket)) == 1


def test_strike_resets_after_120_seconds(monkeypatch):
    current_time = {"value": 1000.0}

    def advance_past_reset():
        current_time["value"] += server.ANTI_SPAM_STRIKE_RESET_SECONDS

    websocket, _, _ = run_messages(
        monkeypatch,
        [send_message(text=f"message-{index}") for index in range(16)]
        + [advance_past_reset, send_message(text="after-reset")],
        current_time=current_time,
    )

    assert len(security_results(websocket)) == 1
    assert server.spam_strikes == {}
    assert websocket.closed is False


def test_after_reset_next_violation_is_treated_as_first_violation(monkeypatch):
    current_time = {"value": 1000.0}

    def advance_past_reset():
        current_time["value"] += server.ANTI_SPAM_STRIKE_RESET_SECONDS

    requests = [send_message(text=f"first-window-{index}") for index in range(16)]
    requests.append(advance_past_reset)
    requests.extend(
        send_message(text=f"second-window-{index}")
        for index in range(16)
    )

    websocket, db, _ = run_messages(
        monkeypatch,
        requests,
        current_time=current_time,
    )

    assert len(db.messages) == 30
    assert len(security_results(websocket)) == 2
    assert websocket.closed is False
    assert server.spam_strikes[1]["count"] == 1
