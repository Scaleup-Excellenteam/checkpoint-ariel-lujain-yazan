import json
from threading import Thread

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as websocket_connect


SERVER_URL = "ws://172.20.10.3:8000/"


class ChatClient:
    def __init__(
        self,
        server_url,
        on_message=None,
        on_connected=None,
        on_disconnected=None,
        on_error=None,
    ):
        self.server_url = server_url
        self.websocket = None
        self.receiver_thread = None
        self.token = None
        self.on_message = on_message
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.on_error = on_error

    def report_error(self, reason):
        if self.on_error is not None:
            self.on_error(str(reason))
        else:
            print(f"Error: {reason}")

    def connect(self):
        try:
            self.websocket = websocket_connect(
                self.server_url,
                legacy=True,
                ping_interval=20,
                ping_timeout=20,
            )
        except Exception as error:
            self.report_error(error)
            return

        self.receiver_thread = Thread(
            target=self.receive_messages,
            daemon=True,
        )
        self.receiver_thread.start()

        if self.on_connected is not None:
            self.on_connected()
        else:
            print("Connected to the server.")

    def receive_messages(self):
        try:
            while True:
                message = self.websocket.recv()

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    data = {
                        "type": "MESSAGE",
                        "text": message,
                    }

                if (
                    isinstance(data, dict)
                    and data.get("type") == "LOGIN_RESULT"
                    and data.get("success") is True
                ):
                    token = data.get("token")

                    if isinstance(token, str) and token:
                        self.token = token

                if self.on_message is not None:
                    self.on_message(message)
                else:
                    print(f"\nMessage: {message}")

        except ConnectionClosed:
            self.websocket = None

            if self.on_disconnected is not None:
                self.on_disconnected()
            else:
                print("\nDisconnected from server.")

    def send_message(self, text):
        if self.websocket is None:
            self.report_error("Not connected to the server.")
            return

        try:
            self.websocket.send(text)
        except ConnectionClosed as error:
            self.report_error(error)

    def send_json(self, data):
        message = json.dumps(data)
        self.send_message(message)

    def signup(self, username, password):
        data = {
            "type": "SIGNUP",
            "username": username,
            "password": password,
        }

        self.send_json(data)

    def login(self, username, password):
        data = {
            "type": "LOGIN",
            "username": username,
            "password": password,
        }

        self.send_json(data)

    def disconnect(self):
        if self.websocket is not None:
            self.websocket.close()
            self.websocket = None


def run_terminal():
    client = ChatClient(SERVER_URL)
    client.connect()

    try:
        while True:
            message = input("You: ")

            if message == "/exit":
                break

            client.send_message(message)
    finally:
        client.disconnect()


if __name__ == "__main__":
    run_terminal()
