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
        send_to_ui({
            "type": "MESSAGE_RECEIVED",
            "text": message,
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