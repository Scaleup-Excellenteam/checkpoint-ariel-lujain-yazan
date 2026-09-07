import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from client.network.client import ChatClient, SERVER_URL


app = FastAPI()


@app.websocket("/ws")
async def ui_websocket(websocket: WebSocket):
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

        elif response_type == "MESSAGE":
            send_to_ui({
                "type": "MESSAGE_RECEIVED",
                "text": data.get("text", ""),
            })

        elif response_type == "ERROR":
            send_to_ui({
                "type": "ERROR",
                "reason": data.get("reason", "Server error"),
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
            "reason": reason,
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
                    chat_client.connect
                )

            elif request_type == "SIGNUP":
                username = request.get("username")
                password = request.get("password")

                if not isinstance(username, str) or not username.strip():
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Username is required",
                    })
                    continue

                if not isinstance(password, str) or not password:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Password is required",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.signup,
                    username,
                    password,
                )

            elif request_type == "LOGIN":
                username = request.get("username")
                password = request.get("password")

                if not isinstance(username, str) or not username.strip():
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Username is required",
                    })
                    continue

                if not isinstance(password, str) or not password:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Password is required",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.login,
                    username,
                    password,
                )

            elif request_type == "SEND_MESSAGE":
                text = request.get("text")

                if not isinstance(text, str) or not text.strip():
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Message text is required",
                    })
                    continue

                await asyncio.to_thread(
                    chat_client.send_message,
                    text,
                )

            elif request_type == "DISCONNECT":
                await asyncio.to_thread(
                    chat_client.disconnect
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
            chat_client.disconnect
        )