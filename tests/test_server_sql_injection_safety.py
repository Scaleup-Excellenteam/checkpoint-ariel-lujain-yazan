import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-sql-safety-tests")

from server import index as server


SQL_LOOKING_USERNAME = "' OR '1'='1"
SQL_LOOKING_ROOM = "admin' --"
SQL_LOOKING_MESSAGE = "'; SELECT 1; --"


class RecordingDbPool:
    def __init__(self):
        self.calls = []
        self.users = {
            "alice": {"id": 1, "password_hash": "alice-hash"},
            "bob": {"id": 2, "password_hash": "bob-hash"},
        }
        self.rooms = {
            10: {"id": 10, "name": "General"},
        }
        self.memberships = {
            (1, 10),
            (2, 10),
        }
        self.messages = []
        self.next_user_id = 3
        self.next_room_id = 11

    def record(self, method, query, args):
        self.calls.append({
            "method": method,
            "query": query,
            "args": args,
        })

    async def fetchrow(self, query, *args):
        self.record("fetchrow", query, args)

        if "FROM users" in query:
            (username,) = args
            return self.users.get(username)

        if "FROM rooms" in query:
            (room_id,) = args
            return self.rooms.get(room_id)

        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetchval(self, query, *args):
        self.record("fetchval", query, args)

        if "INSERT INTO users" in query:
            username, password_hash = args
            user_id = self.next_user_id
            self.next_user_id += 1
            self.users[username] = {
                "id": user_id,
                "password_hash": password_hash,
            }
            return user_id

        if "INSERT INTO rooms" in query:
            (room_name,) = args
            room_id = self.next_room_id
            self.next_room_id += 1
            self.rooms[room_id] = {
                "id": room_id,
                "name": room_name,
            }
            return room_id

        if "FROM room_members" in query:
            user_id, room_id = args
            return 1 if (user_id, room_id) in self.memberships else None

        if "SELECT username" in query:
            (user_id,) = args
            for username, user in self.users.items():
                if user["id"] == user_id:
                    return username
            return None

        raise AssertionError(f"Unexpected fetchval query: {query}")

    async def fetch(self, query, *args):
        self.record("fetch", query, args)

        if "FROM rooms" in query:
            return list(self.rooms.values())

        if "FROM room_members" in query:
            (room_id,) = args
            return [
                {"user_id": user_id}
                for user_id, member_room_id in self.memberships
                if member_room_id == room_id
            ]

        raise AssertionError(f"Unexpected fetch query: {query}")

    async def execute(self, query, *args):
        self.record("execute", query, args)

        if "INSERT INTO users" in query:
            username, password_hash = args
            user_id = self.next_user_id
            self.next_user_id += 1
            self.users[username] = {
                "id": user_id,
                "password_hash": password_hash,
            }
            return

        if "INSERT INTO room_members" in query:
            room_id, user_id = args
            self.memberships.add((user_id, room_id))
            return

        if "DELETE FROM room_members" in query:
            user_id, room_id = args
            self.memberships.discard((user_id, room_id))
            return

        if "INSERT INTO messages" in query:
            room_id, user_id, text = args
            self.messages.append({
                "room_id": room_id,
                "user_id": user_id,
                "text": text,
            })
            return

        raise AssertionError(f"Unexpected execute query: {query}")


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


def setup_function():
    server.active_connections.clear()
    server.connection_users.clear()
    server.login_attempts.clear()
    server.message_rate_windows.clear()
    server.spam_strikes.clear()
    server.url_reputation_cache.clear()


def install_db_and_auth(monkeypatch):
    db = RecordingDbPool()
    monkeypatch.setattr(server, "hash_password", lambda password: f"hash:{password}")
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
    monkeypatch.setattr(
        server,
        "verify_access_token",
        lambda token: {"token-1": 1, "token-2": 2}.get(token),
    )
    server.app.state.db_pool = db
    return db


def run_ws(monkeypatch, requests):
    db = install_db_and_auth(monkeypatch)
    websocket = FakeWebSocket(requests)
    server.connection_users[websocket] = 1

    asyncio.run(server.websocket_endpoint(websocket))

    return websocket, db


def sql_texts(db):
    return [call["query"] for call in db.calls]


def all_args(db):
    return [arg for call in db.calls for arg in call["args"]]


def assert_payload_is_bound_data(db, payload):
    assert payload in all_args(db)
    assert all(payload not in query for query in sql_texts(db))


def assert_no_internal_details(response):
    serialized = str(response)

    for forbidden in (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "Traceback",
        "asyncpg",
        "password_hash",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
    ):
        assert forbidden not in serialized


def test_sql_looking_username_cannot_bypass_login(monkeypatch):
    db = install_db_and_auth(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(server.login(server.LoginRequest(
            username=SQL_LOOKING_USERNAME,
            password="correct",
        )))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid username or password"
    assert_payload_is_bound_data(db, SQL_LOOKING_USERNAME)
    assert_no_internal_details(exc_info.value.detail)


def test_sql_looking_signup_input_is_treated_only_as_data(monkeypatch):
    db = install_db_and_auth(monkeypatch)

    result = asyncio.run(server.register(server.RegisterRequest(
        username=SQL_LOOKING_USERNAME,
        password="password",
    )))

    assert result["username"] == SQL_LOOKING_USERNAME
    assert db.users[SQL_LOOKING_USERNAME]["password_hash"] == "hash:password"
    assert_payload_is_bound_data(db, SQL_LOOKING_USERNAME)


def test_sql_looking_room_name_cannot_alter_queries(monkeypatch):
    websocket, db = run_ws(monkeypatch, [{
        "type": "CREATE_ROOM",
        "token": "token-1",
        "name": SQL_LOOKING_ROOM,
    }])

    assert websocket.sent == [{
        "type": "CREATE_ROOM_RESULT",
        "success": True,
        "room": {
            "room_id": 11,
            "name": SQL_LOOKING_ROOM,
        },
    }]
    assert db.rooms[11]["name"] == SQL_LOOKING_ROOM
    assert_payload_is_bound_data(db, SQL_LOOKING_ROOM)


def test_sql_looking_message_text_is_normal_message_data(monkeypatch):
    websocket, db = run_ws(monkeypatch, [{
        "type": "SEND_MESSAGE",
        "token": "token-1",
        "room_id": 10,
        "text": SQL_LOOKING_MESSAGE,
    }])

    assert db.messages == [{
        "room_id": 10,
        "user_id": 1,
        "text": SQL_LOOKING_MESSAGE,
    }]
    assert websocket.sent[-1]["text"] == SQL_LOOKING_MESSAGE
    assert_payload_is_bound_data(db, SQL_LOOKING_MESSAGE)


@pytest.mark.parametrize("room_id", ["10", SQL_LOOKING_MESSAGE, None, True, -1, 0])
def test_malformed_room_id_is_rejected_safely(monkeypatch, room_id):
    websocket, db = run_ws(monkeypatch, [{
        "type": "SEND_MESSAGE",
        "token": "token-1",
        "room_id": room_id,
        "text": "hello",
    }])

    assert websocket.sent == [{
        "type": "ERROR",
        "reason": "Valid room_id is required",
    }]
    assert db.calls == []
    assert_no_internal_details(websocket.sent[0])


def test_crafted_input_cannot_retrieve_unrelated_user_data(monkeypatch):
    db = install_db_and_auth(monkeypatch)

    with pytest.raises(HTTPException):
        asyncio.run(server.login(server.LoginRequest(
            username="alice' OR '1'='1",
            password="correct",
        )))

    assert "access_token" not in str(db.calls)
    assert_payload_is_bound_data(db, "alice' OR '1'='1")


def test_database_layer_remains_usable_after_sql_looking_inputs(monkeypatch):
    websocket, db = run_ws(monkeypatch, [
        {
            "type": "CREATE_ROOM",
            "token": "token-1",
            "name": SQL_LOOKING_ROOM,
        },
        {
            "type": "SEND_MESSAGE",
            "token": "token-1",
            "room_id": 10,
            "text": SQL_LOOKING_MESSAGE,
        },
        {
            "type": "SEND_MESSAGE",
            "token": "token-2",
            "room_id": 10,
            "text": "normal after crafted input",
        },
    ])

    assert db.rooms[11]["name"] == SQL_LOOKING_ROOM
    assert db.messages[-1]["text"] == "normal after crafted input"
    assert websocket.sent[-1]["sender"] == "bob"
    assert websocket.closed is False


def test_normal_valid_operations_still_work(monkeypatch):
    websocket, db = run_ws(monkeypatch, [
        {
            "type": "JOIN_ROOM",
            "token": "token-1",
            "room_id": 10,
        },
        {
            "type": "SEND_MESSAGE",
            "token": "token-1",
            "room_id": 10,
            "text": "hello",
        },
    ])

    assert websocket.sent[0] == {
        "type": "JOIN_ROOM_RESULT",
        "success": True,
        "room_id": 10,
    }
    assert db.messages == [{
        "room_id": 10,
        "user_id": 1,
        "text": "hello",
    }]


def test_no_sql_stack_trace_credentials_or_db_details_are_returned(monkeypatch):
    websocket, _ = run_ws(monkeypatch, [
        {
            "type": "JOIN_ROOM",
            "token": "token-1",
            "room_id": SQL_LOOKING_MESSAGE,
        },
        {
            "type": "LEAVE_ROOM",
            "token": "token-1",
            "room_id": {"id": 10},
        },
    ])

    for response in websocket.sent:
        assert_no_internal_details(response)
