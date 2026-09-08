import json
import os
from threading import Thread, current_thread

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as websocket_connect

from environment import load_root_env


load_root_env()


SERVER_URL = os.environ.get("CHAT_SERVER_URL", "ws://127.0.0.1:8000/")

MAX_SERVER_MESSAGE_SIZE = 64 * 1024
MAX_USERNAME_LENGTH = 50
MAX_PASSWORD_LENGTH = 128
MAX_ROOM_NAME_LENGTH = 50
MAX_CHAT_MESSAGE_LENGTH = 2000
MAX_TOKEN_LENGTH = 8192


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
        if self.websocket is not None:
            self.report_error("Already connected to the server.")
            return

        if self.receiver_thread is not None and self.receiver_thread is not current_thread():
            self.receiver_thread.join()

        try:
            self.websocket = websocket_connect(
                self.server_url,
                legacy=True,
                ping_interval=20,
                ping_timeout=20,
                open_timeout=10,
                close_timeout=10,
                max_size=MAX_SERVER_MESSAGE_SIZE,
                max_queue=16,
                compression=None,
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
        websocket = self.websocket
        try:
            while True:
                message = websocket.recv()

                if not isinstance(message, str):
                    self.report_error("Binary server messages are not supported.")
                    continue

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
                ):
                    if data.get("success") is True:
                        token = data.get("token")

                        if (
                            isinstance(token, str)
                            and token
                            and len(token) <= MAX_TOKEN_LENGTH
                        ):
                            self.token = token
                        else:
                            self.token = None
                            data["success"] = False
                            data["reason"] = "Invalid authentication token"
                            message = json.dumps(data)
                    else:
                        self.token = None

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

        except Exception as error:
            self.websocket = None
            self.report_error(error)

    def send_message(self, text):
        if self.websocket is None:
            self.report_error("Not connected to the server.")
            return

        if not isinstance(text, str):
            self.report_error("Only text messages are supported.")
            return

        if len(text.encode("utf-8")) > MAX_SERVER_MESSAGE_SIZE:
            self.report_error("Message is too large.")
            return

        try:
            self.websocket.send(text)
        except ConnectionClosed as error:
            self.websocket = None
            self.report_error(error)

    def send_json(self, data):
        if not isinstance(data, dict):
            self.report_error("Invalid request format.")
            return

        try:
            message = json.dumps(data)
        except (TypeError, ValueError):
            self.report_error("Request cannot be encoded as JSON.")
            return

        self.send_message(message)

    def send_authenticated_json(self, data):
        if self.token is None:
            self.report_error("Authentication required.")
            return

        payload = dict(data)
        payload["token"] = self.token
        self.send_json(payload)

    def list_rooms(self):
        self.send_authenticated_json({
            "type": "LIST_ROOMS",
        })

    def create_room(self, name):
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > MAX_ROOM_NAME_LENGTH
        ):
            self.report_error("Invalid room name.")
            return

        self.send_authenticated_json({
            "type": "CREATE_ROOM",
            "name": name.strip(),
        })

    def join_room(self, room_id):
        if type(room_id) is not int or room_id <= 0:
            self.report_error("Invalid room_id.")
            return

        self.send_authenticated_json({
            "type": "JOIN_ROOM",
            "room_id": room_id,
        })

    def leave_room(self, room_id):
        if type(room_id) is not int or room_id <= 0:
            self.report_error("Invalid room_id.")
            return

        self.send_authenticated_json({
            "type": "LEAVE_ROOM",
            "room_id": room_id,
        })

    def send_room_message(self, room_id, text):
        if type(room_id) is not int or room_id <= 0:
            self.report_error("Invalid room_id.")
            return

        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > MAX_CHAT_MESSAGE_LENGTH
        ):
            self.report_error("Invalid message text.")
            return

        self.send_authenticated_json({
            "type": "SEND_MESSAGE",
            "room_id": room_id,
            "text": text,
        })

    def signup(self, username, password):
        if (
            not isinstance(username, str)
            or not username.strip()
            or len(username.strip()) > MAX_USERNAME_LENGTH
        ):
            self.report_error("Invalid username.")
            return

        if (
            not isinstance(password, str)
            or not password
            or len(password) > MAX_PASSWORD_LENGTH
        ):
            self.report_error("Invalid password.")
            return

        if self.websocket is None:
            self.connect()
            if self.websocket is None:
                return

        self.send_json({
            "type": "SIGNUP",
            "username": username.strip(),
            "password": password,
        })

    def login(self, username, password):
        if (
            not isinstance(username, str)
            or not username.strip()
            or len(username.strip()) > MAX_USERNAME_LENGTH
        ):
            self.token = None
            self.report_error("Invalid username.")
            return

        if (
            not isinstance(password, str)
            or not password
            or len(password) > MAX_PASSWORD_LENGTH
        ):
            self.token = None
            self.report_error("Invalid password.")
            return

        if self.websocket is None:
            self.connect()
            if self.websocket is None:
                return

        self.send_json({
            "type": "LOGIN",
            "username": username.strip(),
            "password": password,
        })

    def logout(self):
        self.token = None
        self.disconnect()

    def disconnect(self):
        if self.websocket is not None:
            self.websocket.close()
        if self.receiver_thread is not None and self.receiver_thread is not current_thread():
            self.receiver_thread.join()
        self.receiver_thread = None
        self.websocket = None
