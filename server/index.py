import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, logger


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI()

active_connections = []


@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)

    logger.info(f"Client connected. Total clients: {len(active_connections)}")

    try:
        while True:
            message = await websocket.receive_text()

            logger.info("Received message")

            for client in active_connections.copy():
                if client is not websocket:
                    await client.send_text(message)

            logger.info("Message broadcasted")        

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(
            f"Client disconnected. Total clients: {len(active_connections)}"
        )