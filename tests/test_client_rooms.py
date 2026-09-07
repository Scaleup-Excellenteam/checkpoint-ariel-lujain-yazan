import json

import pytest

from client.network.client import (
    ChatClient,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_ROOM_NAME_LENGTH,
)


@pytest.fixture
def authenticated_client():
    errors = []
    sent = []

    client = ChatClient("ws://test", on_error=errors.append)
    client.websocket = object()
    client.token = "jwt-token"
    client.send_message = sent.append

    return client, sent, errors


def test_room_operation_requires_authentication():
    errors = []
    client = ChatClient("ws://test", on_error=errors.append)
    client.websocket = object()

    client.list_rooms()

    assert errors == ["Authentication required."]


def test_list_rooms_adds_token(authenticated_client):
    client, sent, _ = authenticated_client

    client.list_rooms()

    assert json.loads(sent[0]) == {
        "type": "LIST_ROOMS",
        "token": "jwt-token",
    }


def test_create_room_adds_token_and_strips_name(authenticated_client):
    client, sent, _ = authenticated_client

    client.create_room("  Study  ")

    assert json.loads(sent[0]) == {
        "type": "CREATE_ROOM",
        "name": "Study",
        "token": "jwt-token",
    }


@pytest.mark.parametrize(
    "room_name",
    [
        "",
        "   ",
        "x" * (MAX_ROOM_NAME_LENGTH + 1),
    ],
)
def test_create_room_rejects_invalid_name(
    authenticated_client,
    room_name,
):
    client, sent, errors = authenticated_client

    client.create_room(room_name)

    assert sent == []
    assert errors == ["Invalid room name."]


@pytest.mark.parametrize("room_id", [None, 0, -1, "1", True])
def test_join_room_rejects_invalid_room_id(
    authenticated_client,
    room_id,
):
    client, sent, errors = authenticated_client

    client.join_room(room_id)

    assert sent == []
    assert errors == ["Invalid room_id."]


def test_join_room_adds_token(authenticated_client):
    client, sent, _ = authenticated_client

    client.join_room(3)

    assert json.loads(sent[0]) == {
        "type": "JOIN_ROOM",
        "room_id": 3,
        "token": "jwt-token",
    }


def test_leave_room_adds_token(authenticated_client):
    client, sent, _ = authenticated_client

    client.leave_room(3)

    assert json.loads(sent[0]) == {
        "type": "LEAVE_ROOM",
        "room_id": 3,
        "token": "jwt-token",
    }


def test_send_room_message_adds_room_and_token(authenticated_client):
    client, sent, _ = authenticated_client

    client.send_room_message(4, "hello")

    assert json.loads(sent[0]) == {
        "type": "SEND_MESSAGE",
        "room_id": 4,
        "text": "hello",
        "token": "jwt-token",
    }


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "x" * (MAX_CHAT_MESSAGE_LENGTH + 1),
    ],
)
def test_send_room_message_rejects_invalid_text(
    authenticated_client,
    text,
):
    client, sent, errors = authenticated_client

    client.send_room_message(4, text)

    assert sent == []
    assert errors == ["Invalid message text."]


@pytest.mark.parametrize("room_id", [0, -1, "4", None, True])
def test_send_room_message_rejects_invalid_room_id(
    authenticated_client,
    room_id,
):
    client, sent, errors = authenticated_client

    client.send_room_message(room_id, "hello")

    assert sent == []
    assert errors == ["Invalid room_id."]
