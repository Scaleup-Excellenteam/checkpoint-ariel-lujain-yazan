"""Real loopback WebSocket transport; the upstream protocol peer is a test server."""
import json
from queue import Queue
from threading import Thread

from websockets.sync.server import serve

from client.network.client import ChatClient


def test_real_transport_logout_then_login_again():
    requests = Queue()
    received = Queue()
    errors = []

    def peer(socket):
        for message in socket:
            request = json.loads(message)
            requests.put(request)
            socket.send(json.dumps({
                "type": "LOGIN_RESULT", "success": True, "token": "test.jwt.token",
            }))

    with serve(peer, "127.0.0.1", 0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = ChatClient(
            f"ws://127.0.0.1:{server.socket.getsockname()[1]}/",
            on_message=received.put, on_error=errors.append,
        )
        try:
            for _ in range(2):
                client.login("alice", "password")
                assert requests.get(timeout=5)["type"] == "LOGIN"
                assert json.loads(received.get(timeout=5))["success"] is True
                assert client.token == "test.jwt.token"
                client.logout()
                assert client.websocket is None
                assert client.token is None
            assert errors == []
        finally:
            client.disconnect()
            server.shutdown()
            thread.join(timeout=5)


def test_bridge_real_client_reconnects_without_reopening_browser_socket(monkeypatch):
    from fastapi.testclient import TestClient
    from client.network import bridge

    requests = Queue()

    def peer(socket):
        for raw in socket:
            request = json.loads(raw)
            requests.put(request)
            socket.send(json.dumps({
                "type": "LOGIN_RESULT", "success": True, "token": "private.jwt.token",
            }))

    with serve(peer, "127.0.0.1", 0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setattr(bridge, "SERVER_URL", f"ws://127.0.0.1:{server.socket.getsockname()[1]}/")
        try:
            with TestClient(bridge.app).websocket_connect(
                "/ws", headers={"origin": "http://127.0.0.1:5173"},
            ) as browser:
                for _ in range(2):
                    browser.send_json({"type": "LOGIN", "username": "alice", "password": "password"})
                    responses = [browser.receive_json(), browser.receive_json()]
                    assert {response["type"] for response in responses} == {"CONNECTED", "LOGIN_RESULT"}
                    result = next(response for response in responses if response["type"] == "LOGIN_RESULT")
                    assert result["success"] is True
                    assert "token" not in result
                    assert requests.get(timeout=5)["type"] == "LOGIN"
                    browser.send_json({"type": "LOGOUT"})
                    responses = [browser.receive_json(), browser.receive_json()]
                    assert {response["type"] for response in responses} == {"DISCONNECTED", "LOGOUT_RESULT"}
        finally:
            server.shutdown()
            thread.join(timeout=5)
