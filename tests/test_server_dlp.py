import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketDisconnect

_MISSING_MODULE = object()
_previous_config_modules = {
    name: sys.modules.get(name, _MISSING_MODULE)
    for name in ("auth", "database")
}

with patch.dict(
    os.environ,
    {
        "JWT_SECRET_KEY": "test-only-dlp-integration-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
    },
):
    from server.dlp import DlpDecision, DlpFailure, DlpFailureKind
    from server import index as server_module

for _module_name, _previous_module in _previous_config_modules.items():
    if _previous_module is _MISSING_MODULE:
        sys.modules.pop(_module_name, None)
    else:
        sys.modules[_module_name] = _previous_module


class FakeWebSocket:
    def __init__(self, incoming=()):
        self.incoming = list(incoming)
        self.sent = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive_json(self):
        if not self.incoming:
            raise WebSocketDisconnect
        return self.incoming.pop(0)

    async def send_json(self, message):
        self.sent.append(message)


class FakeDatabasePool:
    def __init__(self, *, is_member=True):
        self.is_member = is_member
        self.persisted_messages = []
        self.calls = []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))

        if "FROM room_members" in query:
            return 1 if self.is_member else None
        if "SELECT username" in query:
            return "lujain"
        raise AssertionError(f"Unexpected fetchval query: {query}")

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))

        if "INSERT INTO messages" not in query:
            raise AssertionError(f"Unexpected execute query: {query}")
        self.persisted_messages.append({
            "room_id": args[0],
            "sender_id": args[1],
            "text": args[2],
        })

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))

        if "FROM room_members" not in query:
            raise AssertionError(f"Unexpected fetch query: {query}")
        return [{"user_id": 1}, {"user_id": 2}]


class FakeDlpClassifier:
    def __init__(self, results):
        self.results = list(results)
        self.messages = []

    async def classify(self, message):
        self.messages.append(message)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture(autouse=True)
def reset_server_connection_state():
    missing_state = object()
    previous_db_pool = getattr(
        server_module.app.state,
        "db_pool",
        missing_state,
    )
    previous_dlp_classifier = getattr(
        server_module.app.state,
        "dlp_classifier",
        missing_state,
    )
    previous_connections = list(server_module.active_connections)
    previous_connection_users = dict(server_module.connection_users)

    server_module.active_connections.clear()
    server_module.connection_users.clear()

    try:
        yield
    finally:
        server_module.active_connections.clear()
        server_module.active_connections.extend(previous_connections)
        server_module.connection_users.clear()
        server_module.connection_users.update(previous_connection_users)

        for name, previous_value in (
            ("db_pool", previous_db_pool),
            ("dlp_classifier", previous_dlp_classifier),
        ):
            if previous_value is missing_state:
                if hasattr(server_module.app.state, name):
                    delattr(server_module.app.state, name)
            else:
                setattr(server_module.app.state, name, previous_value)


def send_message(text, *, token="valid-token", room_id=7):
    return {
        "type": "SEND_MESSAGE",
        "token": token,
        "room_id": room_id,
        "text": text,
    }


def run_endpoint(
    monkeypatch,
    incoming,
    *,
    classifier,
    database=None,
    authenticated_user_id=1,
    include_other_member=True,
):
    sender = FakeWebSocket(incoming)
    other_member = FakeWebSocket()
    database = database or FakeDatabasePool()

    server_module.app.state.db_pool = database
    if classifier is None:
        if hasattr(server_module.app.state, "dlp_classifier"):
            del server_module.app.state.dlp_classifier
    else:
        server_module.app.state.dlp_classifier = classifier

    monkeypatch.setattr(
        server_module,
        "verify_access_token",
        lambda token: authenticated_user_id,
    )

    server_module.connection_users[sender] = authenticated_user_id
    if include_other_member:
        server_module.active_connections.append(other_member)
        server_module.connection_users[other_member] = 2

    asyncio.run(server_module.websocket_endpoint(sender))
    return sender, other_member, database


def test_allow_persists_and_broadcasts_existing_message(monkeypatch):
    classifier = FakeDlpClassifier([DlpDecision(action="ALLOW")])

    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("ordinary chat")],
        classifier=classifier,
    )

    expected_message = {
        "type": "MESSAGE",
        "room_id": 7,
        "sender": "lujain",
        "text": "ordinary chat",
    }
    assert sender.accepted is True
    assert classifier.messages == ["ordinary chat"]
    assert database.persisted_messages == [{
        "room_id": 7,
        "sender_id": 1,
        "text": "ordinary chat",
    }]
    assert sender.sent == [expected_message]
    assert other_member.sent == [expected_message]


def test_block_is_not_persisted_or_broadcast_and_connection_recovers(monkeypatch):
    classifier = FakeDlpClassifier([
        DlpDecision(action="BLOCK"),
        DlpDecision(action="ALLOW"),
    ])

    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("blocked text"), send_message("later safe text")],
        classifier=classifier,
    )

    assert classifier.messages == ["blocked text", "later safe text"]
    assert database.persisted_messages == [{
        "room_id": 7,
        "sender_id": 1,
        "text": "later safe text",
    }]
    assert sender.sent == [
        {
            "type": "SECURITY_RESULT",
            "source": "DLP",
            "action": "BLOCK",
            "reason": "SENSITIVE_CONTENT",
            "room_id": 7,
        },
        {
            "type": "MESSAGE",
            "room_id": 7,
            "sender": "lujain",
            "text": "later safe text",
        },
    ]
    assert other_member.sent == [{
        "type": "MESSAGE",
        "room_id": 7,
        "sender": "lujain",
        "text": "later safe text",
    }]


def test_failure_is_not_persisted_or_broadcast_and_connection_recovers(monkeypatch):
    classifier = FakeDlpClassifier([
        DlpFailure(DlpFailureKind.TIMEOUT),
        DlpDecision(action="ALLOW"),
    ])

    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("unchecked text"), send_message("later safe text")],
        classifier=classifier,
    )

    assert classifier.messages == ["unchecked text", "later safe text"]
    assert database.persisted_messages == [{
        "room_id": 7,
        "sender_id": 1,
        "text": "later safe text",
    }]
    expected_allowed_message = {
        "type": "MESSAGE",
        "room_id": 7,
        "sender": "lujain",
        "text": "later safe text",
    }
    assert sender.sent == [
        {
            "type": "SECURITY_RESULT",
            "source": "DLP",
            "action": "BLOCK",
            "reason": "SECURITY_CHECK_UNAVAILABLE",
            "room_id": 7,
        },
        expected_allowed_message,
    ]
    assert other_member.sent == [expected_allowed_message]


@pytest.mark.parametrize(
    "invalid_decision",
    [
        None,
        object(),
        SimpleNamespace(action=None),
        SimpleNamespace(action="REVIEW"),
        SimpleNamespace(action="allow"),
    ],
    ids=[
        "none",
        "missing-action",
        "none-action",
        "unknown-action",
        "lowercase-action",
    ],
)
def test_invalid_decision_fails_closed_and_connection_recovers(
    monkeypatch,
    invalid_decision,
):
    classifier = FakeDlpClassifier([
        invalid_decision,
        DlpDecision(action="ALLOW"),
    ])

    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("unchecked text"), send_message("later safe text")],
        classifier=classifier,
    )

    expected_allowed_message = {
        "type": "MESSAGE",
        "room_id": 7,
        "sender": "lujain",
        "text": "later safe text",
    }
    assert classifier.messages == ["unchecked text", "later safe text"]
    assert database.persisted_messages == [{
        "room_id": 7,
        "sender_id": 1,
        "text": "later safe text",
    }]
    assert sender.sent == [
        {
            "type": "SECURITY_RESULT",
            "source": "DLP",
            "action": "BLOCK",
            "reason": "SECURITY_CHECK_UNAVAILABLE",
            "room_id": 7,
        },
        expected_allowed_message,
    ]
    assert other_member.sent == [expected_allowed_message]


def test_invalid_jwt_does_not_call_classifier(monkeypatch):
    classifier = FakeDlpClassifier([])
    database = FakeDatabasePool()

    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("must not be classified", token="invalid")],
        classifier=classifier,
        database=database,
        authenticated_user_id=None,
    )

    assert classifier.messages == []
    assert database.calls == []
    assert database.persisted_messages == []
    assert sender.sent == [{"type": "ERROR", "reason": "Invalid token"}]
    assert other_member.sent == []


def test_non_member_does_not_call_classifier(monkeypatch):
    classifier = FakeDlpClassifier([])
    database = FakeDatabasePool(is_member=False)

    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("must not be classified")],
        classifier=classifier,
        database=database,
    )

    assert classifier.messages == []
    assert database.persisted_messages == []
    assert sender.sent == [{
        "type": "ERROR",
        "reason": "You are not a member of this room",
    }]
    assert other_member.sent == []


def test_existing_empty_message_validation_precedes_classifier(monkeypatch):
    classifier = FakeDlpClassifier([])
    database = FakeDatabasePool()

    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("")],
        classifier=classifier,
        database=database,
    )

    assert classifier.messages == []
    assert database.calls == []
    assert sender.sent == [{
        "type": "ERROR",
        "reason": "Message text is required",
    }]
    assert other_member.sent == []


def test_missing_classifier_fails_closed(monkeypatch):
    sender, other_member, database = run_endpoint(
        monkeypatch,
        [send_message("must not pass unchecked")],
        classifier=None,
    )

    assert database.persisted_messages == []
    assert sender.sent == [{
        "type": "SECURITY_RESULT",
        "source": "DLP",
        "action": "BLOCK",
        "reason": "SECURITY_CHECK_UNAVAILABLE",
        "room_id": 7,
    }]
    assert other_member.sent == []
