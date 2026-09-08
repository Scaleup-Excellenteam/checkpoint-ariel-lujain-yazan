import asyncio
import json
import os

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
    origin.strip() for origin in os.environ.get(
        "CHAT_UI_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:5500,http://localhost:5500",
    ).split(",") if origin.strip()
}

SECURITY_FEEDBACK_MESSAGES = {
    "SENSITIVE_CONTENT": "The message was not sent because it may contain sensitive information.",
    "MALICIOUS_URL": "The message was not sent because it contains a potentially unsafe link.",
    "LOGIN_RATE_LIMITED": "Too many login attempts. Please wait before trying again.",
    "SPAM_DETECTED": "The action was blocked because spam-like activity was detected.",
    "INVALID_INPUT": "The action was blocked because the submitted data is invalid.",
    "SECURITY_CHECK_UNAVAILABLE": "The action could not be completed because a security check is unavailable.",
}

# The URL-reputation backend used this name before the shared UI contract
# settled on SECURITY_CHECK_UNAVAILABLE.  Keep the backend detail out of the
# browser protocol while both versions can still be deployed during merge.
SECURITY_FEEDBACK_REASON_ALIASES = {
    "URL_REPUTATION_UNAVAILABLE": "SECURITY_CHECK_UNAVAILABLE",
}

# Login throttling predates the explicit action=BLOCK envelope.  Only this
# narrow, failed LOGIN_RESULT shape is treated as a security decision; normal
# login failures must retain their Day 1 behavior.
LOGIN_SECURITY_BLOCK_REASONS = {"LOGIN_RATE_LIMITED"}


def normalize_security_feedback(data):
    """Return a safe UI event for a recognized server security block."""
    if not isinstance(data, dict):
        return None

    reason = data.get("reason")
    is_explicit_block = data.get("action") == "BLOCK"
    is_legacy_login_block = (
        data.get("type") == "LOGIN_RESULT"
        and data.get("success") is False
        and isinstance(reason, str)
        and reason in LOGIN_SECURITY_BLOCK_REASONS
    )

    if not is_explicit_block and not is_legacy_login_block:
        return None

    if isinstance(reason, str):
        reason = SECURITY_FEEDBACK_REASON_ALIASES.get(reason, reason)
    if not isinstance(reason, str) or reason not in SECURITY_FEEDBACK_MESSAGES:
        reason = "UNKNOWN_SECURITY_REASON"

    feedback = {
        "type": "SECURITY_FEEDBACK",
        "action": "BLOCK",
        "reason": reason,
        "message": SECURITY_FEEDBACK_MESSAGES.get(
            reason,
            "The action was blocked for security reasons.",
        ),
    }

    retry_after_seconds = data.get("retry_after_seconds")
    if type(retry_after_seconds) is int and retry_after_seconds >= 0:
        feedback["retry_after_seconds"] = retry_after_seconds

    room_id = data.get("room_id")
    if type(room_id) is int and room_id > 0:
        feedback["room_id"] = room_id

    return feedback


def is_standalone_security_allow(data):
    """Recognize the provisional standalone ALLOW verdict shape."""
    return (
        isinstance(data, dict)
        and data.get("type") == "SECURITY_RESULT"
        and data.get("action") == "ALLOW"
    )


def ui_room(room):
    """Translate server room objects to the documented browser contract."""
    if not isinstance(room, dict):
        raise ValueError("Invalid room from server")
    room_id = room.get("room_id")
    if type(room_id) is not int or room_id <= 0 or not isinstance(room.get("name"), str):
        raise ValueError("Invalid room from server")
    return {"id": room_id, "name": room["name"]}


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

        security_feedback = normalize_security_feedback(data)
        if security_feedback is not None:
            send_to_ui(security_feedback)
            return

        if is_standalone_security_allow(data):
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

            try:
                rooms = [ui_room(room) for room in rooms]
            except ValueError as error:
                send_to_ui({"type": "ERROR", "reason": str(error)})
                return

            send_to_ui({
                "type": "ROOMS_LIST",
                "rooms": rooms,
            })

        elif response_type == "CREATE_ROOM_RESULT":
            try:
                room = ui_room(data.get("room")) if data.get("success") else None
            except ValueError as error:
                send_to_ui({"type": "ERROR", "reason": str(error)})
                return
            send_to_ui({
                "type": "CREATE_ROOM_RESULT",
                "success": data.get("success", False),
                "room": room,
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

        elif response_type == "SECURITY_RESULT":
            send_to_ui({
                "type": "SECURITY_RESULT",
                "source": data.get("source"),
                "action": data.get("action"),
                "reason": data.get("reason"),
                "message": data.get("message"),
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
