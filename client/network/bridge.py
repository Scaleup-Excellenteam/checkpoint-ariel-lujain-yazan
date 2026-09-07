import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from client.network.client import (
    ChatClient,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_PASSWORD_LENGTH,
    MAX_ROOM_NAME_LENGTH,
    MAX_USERNAME_LENGTH,
    SERVER_URL,
)


app = FastAPI()

ALLOWED_UI_ORIGINS = {
    "http://127.0.0.1:5500",
    "http://localhost:5500",
}


@app.websocket("/ws")
async def ui_websocket(websocket: WebSocket):
    origin = websocket.headers.get("origin")

    if origin not in ALLOWED_UI_ORIGINS:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    print("UI connected")

    loop = asyncio.get_running_loop()
    ui_connected = True

    def send_to_ui(data):
        if not ui_connected:
            return

        asyncio.run_coroutine_threadsafe(
            websocket.send_json(data),
            loop,
        )

    def on_server_message(message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            if len(message) > MAX_CHAT_MESSAGE_LENGTH:
                send_to_ui({
                    "type": "ERROR",
                    "reason": "Server message is too long",
                })
                return

            send_to_ui({
                "type": "MESSAGE_RECEIVED",
                "text": message,
            })
            return

        if not isinstance(data, dict):
            send_to_ui({
                "type": "ERROR",
                "reason": "Invalid response from server",
            })
            return

        response_type = data.get("type")

        if response_type == "LOGIN_RESULT":
            send_to_ui({
                "type": "LOGIN_RESULT",
                "success": data.get("success", False),
                "reason": data.get("reason"),
            })

        elif response_type == "SIGNUP_RESULT":
            send_to_ui({
                "type": "SIGNUP_RESULT",
                "success": data.get("success", False),
                "reason": data.get("reason"),
            })

        elif response_type == "ROOMS_LIST":
            rooms = data.get("rooms", [])

            if not isinstance(rooms, list):
                send_to_ui({
                    "type": "ERROR",
                    "reason": "Invalid rooms list from server",
                })
                return

            send_to_ui({
                "type": "ROOMS_LIST",
                "rooms": rooms,
            })

        elif response_type == "CREATE_ROOM_RESULT":
            send_to_ui({
                "type": "CREATE_ROOM_RESULT",
                "success": data.get("success", False),
                "room": data.get("room"),
                "reason": data.get("reason"),
            })

        elif response_type == "JOIN_ROOM_RESULT":
            send_to_ui({
                "type": "JOIN_ROOM_RESULT",
                "success": data.get("success", False),
                "room_id": data.get("room_id"),
                "reason": data.get("reason"),
            })

        elif response_type == "LEAVE_ROOM_RESULT":
            send_to_ui({
                "type": "LEAVE_ROOM_RESULT",
                "success": data.get("success", False),
                "room_id": data.get("room_id"),
                "reason": data.get("reason"),
            })

        elif response_type == "MESSAGE":
            text = data.get("text", "")

            if (
                not isinstance(text, str)
                or len(text) > MAX_CHAT_MESSAGE_LENGTH
            ):
                send_to_ui({
                    "type": "ERROR",
                    "reason": "Invalid message from server",
                })
                return

            send_to_ui({
                "type": "MESSAGE_RECEIVED",
                "room_id": data.get("room_id"),
                "sender": data.get("sender"),
                "text": text,
            })

        elif response_type == "ERROR":
            reason = data.get("reason", "Server error")

            if not isinstance(reason, str):
                reason = "Server error"

            send_to_ui({
                "type": "ERROR",
                "reason": reason,
            })

        else:
            send_to_ui({
                "type": "ERROR",
                "reason": "Unknown response type from server",
            })

    def on_connected():
        send_to_ui({
            "type": "CONNECTED",
        })

    def on_disconnected():
        send_to_ui({
            "type": "DISCONNECTED",
        })

    def on_error(reason):
        send_to_ui({
            "type": "ERROR",
            "reason": str(reason),
        })

    chat_client = ChatClient(
        SERVER_URL,
        on_message=on_server_message,
        on_connected=on_connected,
        on_disconnected=on_disconnected,
        on_error=on_error,
    )

    try:
        while True:
            try:
                request = await websocket.receive_json()

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "ERROR",
                    "reason": "Invalid JSON format",
                })
                continue

            if not isinstance(request, dict):
                await websocket.send_json({
                    "type": "ERROR",
                    "reason": "Invalid request format",
                })
                continue

            request_type = request.get("type")

            if request_type == "CONNECT":
                await asyncio.to_thread(
                    chat_client.connect,
                )

            elif request_type == "SIGNUP":
                username = request.get("username")
                password = request.get("password")

                if (
                    not isinstance(username, str)
                    or not username.strip()
                    or len(username.strip()) > MAX_USERNAME_LENGTH
                ):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid username",
                    })
                    continue

                if (
                    not isinstance(password, str)
                    or not password
                    or len(password) > MAX_PASSWORD_LENGTH
                ):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid password",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.signup,
                    username.strip(),
                    password,
                )

            elif request_type == "LOGIN":
                username = request.get("username")
                password = request.get("password")

                if (
                    not isinstance(username, str)
                    or not username.strip()
                    or len(username.strip()) > MAX_USERNAME_LENGTH
                ):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid username",
                    })
                    continue

                if (
                    not isinstance(password, str)
                    or not password
                    or len(password) > MAX_PASSWORD_LENGTH
                ):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid password",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.login,
                    username.strip(),
                    password,
                )

            elif request_type == "LIST_ROOMS":
                await asyncio.to_thread(
                    chat_client.list_rooms,
                )

            elif request_type == "CREATE_ROOM":
                name = request.get("name")

                if (
                    not isinstance(name, str)
                    or not name.strip()
                    or len(name.strip()) > MAX_ROOM_NAME_LENGTH
                ):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid room name",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.create_room,
                    name.strip(),
                )

            elif request_type == "JOIN_ROOM":
                room_id = request.get("room_id")

                if type(room_id) is not int or room_id <= 0:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Valid room_id is required",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.join_room,
                    room_id,
                )

            elif request_type == "LEAVE_ROOM":
                room_id = request.get("room_id")

                if type(room_id) is not int or room_id <= 0:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Valid room_id is required",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.leave_room,
                    room_id,
                )

            elif request_type == "SEND_MESSAGE":
                room_id = request.get("room_id")
                text = request.get("text")

                if type(room_id) is not int or room_id <= 0:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Valid room_id is required",
                    })
                    continue

                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or len(text) > MAX_CHAT_MESSAGE_LENGTH
                ):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid message text",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.send_room_message,
                    room_id,
                    text,
                )

            elif request_type == "LOGOUT":
                await asyncio.to_thread(
                    chat_client.logout,
                )

                await websocket.send_json({
                    "type": "LOGOUT_RESULT",
                    "success": True,
                })

            elif request_type == "DISCONNECT":
                await asyncio.to_thread(
                    chat_client.disconnect,
                )

            else:
                await websocket.send_json({
                    "type": "ERROR",
                    "reason": "Unknown request type",
                })

    except WebSocketDisconnect:
        ui_connected = False
        print("UI disconnected")

    finally:
        ui_connected = False

        await asyncio.to_thread(
            chat_client.disconnect,
        )
