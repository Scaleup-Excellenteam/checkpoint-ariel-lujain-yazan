import asyncpg
import logging
from contextlib import asynccontextmanager

from pydantic import BaseModel
from auth import hash_password,verify_password, create_access_token

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from database import create_db_pool

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await create_db_pool()
    logger.info("connected to postgreSQL database")

    yield #FastAPI  runs normal operations here

    await app.state.db_pool.close()
    logger.info("disconnected from postgreSQL database")



app = FastAPI(lifespan=lifespan)

active_connections = []

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str    

@app.post("/register")
async def register(data: RegisterRequest):
    hashed = hash_password(data.password)    

    user_id = await app.state.db_pool.fetchval(
        """
        INSERT INTO users (username, password_hash) 
        VALUES ($1, $2) 
        RETURNING id

        """,
        data.username, hashed
    )

    return {"user_id": user_id, "username": data.username}


@app.post("/login") #user tries to login with username and password, if correct, return a JWT token
async def login(data: LoginRequest):

    user = await app.state.db_pool.fetchrow(
        """
        SELECT id, password_hash
        FROM users
        WHERE username = $1
        """,
        data.username
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    token = create_access_token(user["id"])

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)

    logger.info(f"Client connected. Total clients: {len(active_connections)}")

    try:
        while True:
            data = await websocket.receive_json()

            message_type = data.get("type")

            # SIGNUP
            if message_type == "SIGNUP":
                username = data.get("username")
                password = data.get("password")

                hashed = hash_password(password)

                try:
                    await app.state.db_pool.execute(
                        """
                        INSERT INTO users (username, password_hash)
                        VALUES ($1, $2)
                        """,
                        username,
                        hashed
                    )

                    await websocket.send_json({
                        "type": "SIGNUP_RESULT",
                        "success": True
                    })

                except asyncpg.UniqueViolationError:
                    await websocket.send_json({
                        "type": "SIGNUP_RESULT",
                        "success": False,
                        "reason": "Username already exists"
                    })

            # LOGIN
            elif message_type == "LOGIN":
                username = data.get("username")
                password = data.get("password")

                user = await app.state.db_pool.fetchrow(
                    """
                    SELECT id, password_hash
                    FROM users
                    WHERE username = $1
                    """,
                    username
                )

                if user is None or not verify_password(
                    password,
                    user["password_hash"]
                ):
                    await websocket.send_json({
                        "type": "LOGIN_RESULT",
                        "success": False,
                        "reason": "Invalid username or password"
                    })

                else:
                    token = create_access_token(user["id"])

                    await websocket.send_json({
                        "type": "LOGIN_RESULT",
                        "success": True,
                        "token": token
                    })

            else:
                await websocket.send_json({
                    "type": "ERROR",
                    "reason": "Unknown message type"
                })

    except WebSocketDisconnect:
        active_connections.remove(websocket)

        logger.info(
            f"Client disconnected. Total clients: {len(active_connections)}"
        )