import asyncpg
import logging
from contextlib import asynccontextmanager

from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token
)

from database import create_db_pool
from server.dlp import (
    DlpClassifier,
    DlpDecision,
    DlpFailure,
    DlpFailureKind,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# DATABASE STARTUP / SHUTDOWN

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await create_db_pool()
    app.state.dlp_classifier = DlpClassifier(
        provider_call=None,
        protected_context=None,
    )
    logger.info("connected to postgreSQL database")

    yield

    await app.state.db_pool.close()
    logger.info("disconnected from postgreSQL database")


app = FastAPI(lifespan=lifespan)

active_connections = []
connection_users = {}


# TEMP HTTP TEST ROUTES

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/register")
async def register(data: RegisterRequest):
    hashed = hash_password(data.password)

    try:
        user_id = await app.state.db_pool.fetchval(
            """
            INSERT INTO users (username, password_hash)
            VALUES ($1, $2)
            RETURNING id
            """,
            data.username,
            hashed
        )

    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409,
            detail="Username already exists"
        )

    return {
        "user_id": user_id,
        "username": data.username
    }


@app.post("/login")
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

    if not verify_password(
        data.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    token = create_access_token(user["id"])

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# WEBSOCKET


@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    active_connections.append(websocket)

    logger.info(
        f"Client connected. Total clients: {len(active_connections)}"
    )

    try:
        while True:

            data = await websocket.receive_json()

            message_type = data.get("type")


            
            # SIGNUP
            

            if message_type == "SIGNUP":

                username = data.get("username")
                password = data.get("password")

                if not username or not password:
                    await websocket.send_json({
                        "type": "SIGNUP_RESULT",
                        "success": False,
                        "reason": "Username and password are required"
                    })
                    continue

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

                if not username or not password:
                    await websocket.send_json({
                        "type": "LOGIN_RESULT",
                        "success": False,
                        "reason": "Username and password are required"
                    })
                    continue

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

                    connection_users[websocket] = user["id"]

                    await websocket.send_json({
                        "type": "LOGIN_RESULT",
                        "success": True,
                        "token": token
                    })


            
            # LIST ROOMS
            

            elif message_type == "LIST_ROOMS":

                token = data.get("token")

                user_id = (
                    verify_access_token(token)
                    if token
                    else None
                )

                if user_id is None:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid token"
                    })
                    continue

                rooms = await app.state.db_pool.fetch(
                    """
                    SELECT id, name
                    FROM rooms
                    ORDER BY id
                    """
                )

                await websocket.send_json({
                    "type": "ROOMS_LIST",
                    "rooms": [
                        {
                            "room_id": room["id"],
                            "name": room["name"]
                        }
                        for room in rooms
                    ]
                })


            
            # CREATE ROOM
            

            elif message_type == "CREATE_ROOM":

                token = data.get("token")
                room_name = data.get("name")

                user_id = (
                    verify_access_token(token)
                    if token
                    else None
                )

                if user_id is None:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid token"
                    })
                    continue

                if not room_name:
                    await websocket.send_json({
                        "type": "CREATE_ROOM_RESULT",
                        "success": False,
                        "reason": "Room name is required"
                    })
                    continue

                try:

                    room_id = await app.state.db_pool.fetchval(
                        """
                        INSERT INTO rooms (name)
                        VALUES ($1)
                        RETURNING id
                        """,
                        room_name
                    )

                    await websocket.send_json({
                        "type": "CREATE_ROOM_RESULT",
                        "success": True,
                        "room": {
                            "room_id": room_id,
                            "name": room_name
                        }
                    })

                except asyncpg.UniqueViolationError:

                    await websocket.send_json({
                        "type": "CREATE_ROOM_RESULT",
                        "success": False,
                        "reason": "Room name already exists"
                    })

            elif message_type == "JOIN_ROOM":

                token = data.get("token")
                room_id = data.get("room_id")

                user_id = (
                    verify_access_token(token)
                    if token
                    else None
                )

                if user_id is None:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid token"
                    })
                    continue

                #check that the room exists
                room = await app.state.db_pool.fetchrow(
                    """
                    SELECT id
                    FROM rooms
                    WHERE id = $1
                    """,
                    room_id
                )      

                if room is None:
                    await websocket.send_json({
                        "type": "JOIN_ROOM_RESULT",
                        "success": False,
                        "reason": "Room does not exist"
                    })
                    continue

                #add user to room 
                await app.state.db_pool.execute(
                    """
                    INSERT INTO room_members (room_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    room_id,
                    user_id
                )

                await websocket.send_json({
                    "type": "JOIN_ROOM_RESULT",
                    "success": True,
                    "room_id": room_id
                })

            elif message_type == "LEAVE_ROOM":

                token = data.get("token")
                room_id = data.get("room_id")

                user_id = (
                    verify_access_token(token)
                    if token
                    else None
                )

                if user_id is None:
                    await websocket.send_json({
                        "type": "ERROR",
                         "reason": "Invalid token"
                    })
                    continue

                await app.state.db_pool.execute(
                    """
                    DELETE FROM room_members
                    WHERE user_id = $1
                    AND room_id = $2
                    """,
                    user_id,
                    room_id
                )

                await websocket.send_json({
                    "type": "LEAVE_ROOM_RESULT",
                    "success": True,
                    "room_id": room_id
            })



            elif message_type == "SEND_MESSAGE":

                token = data.get("token")
                room_id = data.get("room_id")
                text = data.get("text")

                user_id = verify_access_token(token) if token else None

                if user_id is None:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Invalid token"
                    })
                    continue

                if not text:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Message text is required"
                    })
                    continue

                #check user belongs to room
                membership = await app.state.db_pool.fetchval(
                    """
                    SELECT 1
                    FROM room_members
                    WHERE  user_id = $1 AND room_id = $2
                    """,
                    user_id,
                    room_id
                )

                if membership is None:
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "You are not a member of this room"
                    })
                    continue

                dlp_classifier = getattr(
                    app.state,
                    "dlp_classifier",
                    None,
                )

                try:
                    if dlp_classifier is None:
                        raise DlpFailure(DlpFailureKind.UNAVAILABLE)
                    decision = await dlp_classifier.classify(text)
                    if (
                        not isinstance(decision, DlpDecision)
                        or decision.action not in {"ALLOW", "BLOCK"}
                    ):
                        raise DlpFailure(
                            DlpFailureKind.MALFORMED_RESPONSE
                        )
                except DlpFailure as error:
                    logger.warning(
                        "security_source=DLP action=BLOCK "
                        "reason=SECURITY_CHECK_UNAVAILABLE "
                        "failure_kind=%s room_id=%s user_id=%s",
                        error.kind.value,
                        room_id,
                        user_id,
                    )
                    await websocket.send_json({
                        "type": "SECURITY_RESULT",
                        "source": "DLP",
                        "action": "BLOCK",
                        "reason": "SECURITY_CHECK_UNAVAILABLE",
                        "room_id": room_id
                    })
                    continue

                if decision.action != "ALLOW":
                    logger.warning(
                        "security_source=DLP action=BLOCK "
                        "reason=SENSITIVE_CONTENT room_id=%s user_id=%s",
                        room_id,
                        user_id,
                    )
                    await websocket.send_json({
                        "type": "SECURITY_RESULT",
                        "source": "DLP",
                        "action": "BLOCK",
                        "reason": "SENSITIVE_CONTENT",
                        "room_id": room_id
                    })
                    continue

                #save message to database
                await app.state.db_pool.execute(
                    """
                    INSERT INTO messages (room_id, sender_id, content)
                    VALUES ($1, $2, $3)
                    """,
                    room_id,
                    user_id,
                    text
                )

                #get sender username
                username = await app.state.db_pool.fetchval(
                    """
                    SELECT username
                    FROM users
                    WHERE id = $1
                    """,
                    user_id
                )

                #get all users in the room
                members = await app.state.db_pool.fetch(
                    """
                    SELECT user_id
                    FROM room_members
                    WHERE room_id = $1
                    """,
                    room_id
                )

                member_ids = {member["user_id"] for member in members}

                #send only to connected users in the room
                for client in active_connections.copy():
                    connected_user_id = connection_users.get(client)

                    if connected_user_id in member_ids:
                        await client.send_json({
                            "type": "MESSAGE",
                            "room_id": room_id,
                            "sender": username,
                            "text": text
                        })



            
            # UNKNOWN MESSAGE
            

            else:

                await websocket.send_json({
                    "type": "ERROR",
                    "reason": "Unknown message type"
                })


    except WebSocketDisconnect:

        connection_users.pop(websocket, None)
        active_connections.remove(websocket)

        logger.info(
            f"Client disconnected. Total clients: {len(active_connections)}"
        )
