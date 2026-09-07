import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from client.network import bridge as bridge_module


ALLOWED_ORIGIN = "http://127.0.0.1:5500"


class FakeChatClient:
    instances = []

    def __init__(
        self,
        server_url,
        on_message=None,
        on_connected=None,
        on_disconnected=None,
        on_error=None,
    ):
        self.server_url = server_url
        self.on_message = on_message
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.on_error = on_error
        self.calls = []
        self.token = None
        FakeChatClient.instances.append(self)

    def connect(self):
        self.calls.append(("connect",))
        if self.on_connected is not None:
            self.on_connected()

    def signup(self, username, password):
        self.calls.append(("signup", username, password))

    def login(self, username, password):
        self.calls.append(("login", username, password))
        if self.on_message is not None:
            self.on_message(json.dumps({
                "type": "LOGIN_RESULT",
                "success": True,
                "token": "server-secret-token",
            }))

    def list_rooms(self):
        self.calls.append(("list_rooms",))
        if self.on_message is not None:
            self.on_message(json.dumps({
                "type": "ROOMS_LIST",
                "rooms": [
                    {"room_id": 1, "name": "General"},
                ],
            }))

    def create_room(self, name):
        self.calls.append(("create_room", name))

    def join_room(self, room_id):
        self.calls.append(("join_room", room_id))

    def leave_room(self, room_id):
        self.calls.append(("leave_room", room_id))

    def send_room_message(self, room_id, text):
        self.calls.append(("send_room_message", room_id, text))

    def logout(self):
        self.calls.append(("logout",))

    def disconnect(self):
        self.calls.append(("disconnect",))


@pytest.fixture(autouse=True)
def replace_chat_client(monkeypatch):
    FakeChatClient.instances.clear()
    monkeypatch.setattr(
        bridge_module,
        "ChatClient",
        FakeChatClient,
    )


@pytest.fixture
def test_client():
    return TestClient(bridge_module.app)


def ws_connect(test_client, origin=ALLOWED_ORIGIN):
    return test_client.websocket_connect(
        "/ws",
        headers={"origin": origin},
    )


def wait_for_previous_request(websocket):
    """
    Send a request that produces an immediate response.

    bridge.py processes UI requests sequentially, so receiving this ERROR
    proves that the previous asyncio.to_thread() operation has completed.
    This avoids timing-dependent sleeps in the tests.
    """
    websocket.send_json({"type": "__TEST_BARRIER__"})
    response = websocket.receive_json()

    assert response == {
        "type": "ERROR",
        "reason": "Unknown request type",
    }


def test_bridge_rejects_untrusted_origin(test_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_connect(
            test_client,
            origin="https://evil.example",
        ):
            pass

    assert exc_info.value.code == 1008


def test_connect_request_calls_client_and_returns_connected(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({"type": "CONNECT"})

        response = websocket.receive_json()

        assert response == {"type": "CONNECTED"}
        assert FakeChatClient.instances[0].calls[0] == ("connect",)


def test_login_does_not_expose_jwt_to_ui(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({
            "type": "LOGIN",
            "username": "lujain",
            "password": "secret",
        })

        response = websocket.receive_json()

        assert response["type"] == "LOGIN_RESULT"
        assert response["success"] is True
        assert "token" not in response


def test_login_strips_username_before_forwarding(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({
            "type": "LOGIN",
            "username": "  lujain  ",
            "password": "secret",
        })

        websocket.receive_json()

        calls = FakeChatClient.instances[0].calls
        assert ("login", "lujain", "secret") in calls


def test_invalid_login_username_is_rejected_before_client(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({
            "type": "LOGIN",
            "username": "",
            "password": "secret",
        })

        response = websocket.receive_json()

        assert response == {
            "type": "ERROR",
            "reason": "Invalid username",
        }

        calls = FakeChatClient.instances[0].calls
        assert not any(call[0] == "login" for call in calls)


def test_list_rooms_is_forwarded_to_ui(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({"type": "LIST_ROOMS"})

        response = websocket.receive_json()

        assert response == {
            "type": "ROOMS_LIST",
            "rooms": [
                {"room_id": 1, "name": "General"},
            ],
        }


def test_create_room_is_validated_and_forwarded(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({
            "type": "CREATE_ROOM",
            "name": "  Study  ",
        })

        wait_for_previous_request(websocket)

        calls = FakeChatClient.instances[0].calls
        assert ("create_room", "Study") in calls


@pytest.mark.parametrize("room_id", [0, -1, "1", None, True])
def test_join_room_rejects_invalid_room_id(
    test_client,
    room_id,
):
    with ws_connect(test_client) as websocket:
        websocket.send_json({
            "type": "JOIN_ROOM",
            "room_id": room_id,
        })

        response = websocket.receive_json()

        assert response["type"] == "ERROR"
        assert response["reason"] == "Valid room_id is required"


def test_send_message_forwards_room_and_text(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({
            "type": "SEND_MESSAGE",
            "room_id": 5,
            "text": "hello",
        })

        wait_for_previous_request(websocket)

        calls = FakeChatClient.instances[0].calls
        assert ("send_room_message", 5, "hello") in calls


def test_logout_returns_result(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({"type": "LOGOUT"})

        response = websocket.receive_json()

        assert response == {
            "type": "LOGOUT_RESULT",
            "success": True,
        }

        calls = FakeChatClient.instances[0].calls
        assert ("logout",) in calls


def test_unknown_request_type_returns_error(test_client):
    with ws_connect(test_client) as websocket:
        websocket.send_json({"type": "UNKNOWN"})

        response = websocket.receive_json()

        assert response == {
            "type": "ERROR",
            "reason": "Unknown request type",
        }
