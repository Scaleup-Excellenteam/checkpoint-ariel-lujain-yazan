import asyncpg
import asyncio
import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from math import ceil
from contextlib import asynccontextmanager
from collections import deque
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token
)

from database import create_db_pool


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# DATABASE STARTUP / SHUTDOWN

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await create_db_pool()
    logger.info("connected to postgreSQL database")

    yield

    await app.state.db_pool.close()
    logger.info("disconnected from postgreSQL database")


app = FastAPI(lifespan=lifespan)

active_connections = []
connection_users = {}
login_attempts = {}
message_rate_windows = {}
spam_strikes = {}

LOGIN_FAILURE_LIMIT = 3
LOGIN_COOLDOWN_SECONDS = 60
ANTI_SPAM_THRESHOLD = 15
ANTI_SPAM_WINDOW_SECONDS = 5
ANTI_SPAM_COOLDOWN_SECONDS = 5
ANTI_SPAM_STRIKE_RESET_SECONDS = 120
ANTI_SPAM_BLOCK_RESPONSE = {
    "type": "SECURITY_RESULT",
    "source": "ANTI_SPAM",
    "action": "BLOCK",
    "reason": "SPAM_DETECTED",
    "message": "You are sending messages too quickly. Please wait a moment and try again.",
}
URL_REPUTATION_CACHE_TTL_SECONDS = 600
URL_REPUTATION_MALICIOUS_THRESHOLD = 3
VIRUSTOTAL_REQUEST_TIMEOUT_SECONDS = 2.0
VIRUSTOTAL_URL_REPORT_URL = "https://www.virustotal.com/api/v3/urls/{url_id}"
URL_REPUTATION_SOURCE = "URL_REPUTATION"
MALICIOUS_URL_RESPONSE = {
    "type": "SECURITY_RESULT",
    "source": URL_REPUTATION_SOURCE,
    "action": "BLOCK",
    "reason": "MALICIOUS_URL",
    "message": "This message was blocked because it contains a URL reported as malicious.",
}
URL_REPUTATION_UNAVAILABLE_RESPONSE = {
    "type": "SECURITY_RESULT",
    "source": URL_REPUTATION_SOURCE,
    "action": "BLOCK",
    "reason": "URL_REPUTATION_UNAVAILABLE",
    "message": "This message contains a URL that could not be verified right now. Please try again later.",
}
HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,!?;:)]}'\""
url_reputation_cache = {}


def login_attempt_key(websocket: WebSocket, username: str):
    client = getattr(websocket, "client", None)
    client_ip = getattr(client, "host", None) or "unknown"
    return (client_ip, username)


def login_cooldown_retry_after(key):
    attempt = login_attempts.get(key)

    if attempt is None:
        return None

    cooldown_until = attempt.get("cooldown_until")

    if cooldown_until is None:
        return None

    remaining = cooldown_until - monotonic()

    if remaining <= 0:
        login_attempts.pop(key, None)
        return None

    return max(1, ceil(remaining))


def record_failed_login(key):
    attempt = login_attempts.setdefault(key, {
        "failed_count": 0,
        "cooldown_until": None,
    })

    attempt["failed_count"] += 1
    failed_count = attempt["failed_count"]

    logger.info(
        "Failed login attempt count=%s client_ip=%s username=%r",
        failed_count,
        key[0],
        key[1],
    )

    if failed_count >= LOGIN_FAILURE_LIMIT:
        attempt["cooldown_until"] = monotonic() + LOGIN_COOLDOWN_SECONDS

        logger.warning(
            "Login cooldown activated client_ip=%s username=%r retry_after_seconds=%s",
            key[0],
            key[1],
            LOGIN_COOLDOWN_SECONDS,
        )

        return LOGIN_COOLDOWN_SECONDS

    return None


def reset_failed_login(key):
    if key in login_attempts:
        login_attempts.pop(key, None)
        logger.info(
            "Successful login reset failed-attempt state client_ip=%s username=%r",
            key[0],
            key[1],
        )


def is_non_empty_string(value):
    return isinstance(value, str) and bool(value)


def is_valid_room_id(value):
    return type(value) is int and value > 0


def check_message_rate_limit(user_id):
    now = monotonic()
    window = message_rate_windows.setdefault(user_id, deque())
    cutoff = now - ANTI_SPAM_WINDOW_SECONDS
    strike = spam_strikes.get(user_id)

    if (
        strike is not None
        and now - strike["first_violation_at"] >= ANTI_SPAM_STRIKE_RESET_SECONDS
    ):
        spam_strikes.pop(user_id, None)
        strike = None
        logger.info(
            "Spam strike reset user_id=%s strike_window_seconds=%s",
            user_id,
            ANTI_SPAM_STRIKE_RESET_SECONDS,
        )

    if strike is not None and now < strike.get("cooldown_until", 0):
        logger.warning(
            "Spam cooldown block user_id=%s cooldown_remaining_seconds=%s",
            user_id,
            max(1, ceil(strike["cooldown_until"] - now)),
        )
        return "cooldown"

    while window and window[0] <= cutoff:
        window.popleft()

    if len(window) >= ANTI_SPAM_THRESHOLD:
        strike = spam_strikes.get(user_id)

        if strike is None:
            spam_strikes[user_id] = {
                "count": 1,
                "first_violation_at": now,
                "cooldown_until": now + ANTI_SPAM_COOLDOWN_SECONDS,
            }
            logger.warning(
                "First spam violation user_id=%s threshold=%s window_seconds=%s cooldown_seconds=%s",
                user_id,
                ANTI_SPAM_THRESHOLD,
                ANTI_SPAM_WINDOW_SECONDS,
                ANTI_SPAM_COOLDOWN_SECONDS,
            )
            return "first"

        strike["count"] += 1
        logger.warning(
            "Second spam violation user_id=%s threshold=%s window_seconds=%s strike_window_seconds=%s",
            user_id,
            ANTI_SPAM_THRESHOLD,
            ANTI_SPAM_WINDOW_SECONDS,
            ANTI_SPAM_STRIKE_RESET_SECONDS,
        )
        return "second"

    window.append(now)
    return None


def normalize_url(url):
    trimmed_url = url.strip().rstrip(TRAILING_URL_PUNCTUATION)
    parsed = urlsplit(trimmed_url)

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None

    normalized_netloc = parsed.netloc.lower()
    return urlunsplit((
        parsed.scheme.lower(),
        normalized_netloc,
        parsed.path or "",
        parsed.query or "",
        "",
    ))


def extract_http_urls(text):
    urls = []
    seen = set()

    for match in HTTP_URL_PATTERN.finditer(text):
        normalized_url = normalize_url(match.group(0))

        if normalized_url and normalized_url not in seen:
            urls.append(normalized_url)
            seen.add(normalized_url)

    return urls


def virustotal_url_id(url):
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


async def fetch_virustotal_url_report(url, api_key):
    url_id = virustotal_url_id(url)
    request = urllib.request.Request(
        VIRUSTOTAL_URL_REPORT_URL.format(url_id=url_id),
        headers={"x-apikey": api_key},
        method="GET",
    )

    def make_request():
        with urllib.request.urlopen(
            request,
            timeout=VIRUSTOTAL_REQUEST_TIMEOUT_SECONDS,
        ) as response:
            return json.loads(response.read().decode("utf-8"))

    return await asyncio.to_thread(make_request)


def parse_virustotal_stats(report):
    try:
        stats = report["data"]["attributes"]["last_analysis_stats"]
    except (KeyError, TypeError):
        return None

    if not isinstance(stats, dict):
        return None

    normalized_stats = {}

    for key in ("malicious", "suspicious", "harmless", "undetected", "timeout"):
        value = stats.get(key, 0)

        if not isinstance(value, int):
            return None

        normalized_stats[key] = value

    if sum(normalized_stats.values()) <= 0:
        return None

    return normalized_stats


async def get_url_reputation(url):
    now = monotonic()
    cached = url_reputation_cache.get(url)

    if cached and cached["expires_at"] > now:
        logger.info(
            "URL reputation cache hit verdict=%s reason=%s malicious=%s total=%s",
            cached["verdict"]["action"],
            cached["verdict"].get("reason"),
            cached["verdict"].get("malicious", 0),
            cached["verdict"].get("total", 0),
        )
        return cached["verdict"]

    api_key = os.environ.get("VIRUSTOTAL_API_KEY")

    if not api_key:
        logger.warning("URL reputation unavailable reason=missing_api_key")
        verdict = {
            "action": "BLOCK",
            "reason": "URL_REPUTATION_UNAVAILABLE",
        }
    else:
        try:
            report = await fetch_virustotal_url_report(url, api_key)
            stats = parse_virustotal_stats(report)

            if stats is None:
                logger.warning("URL reputation unavailable reason=malformed_or_unknown_response")
                verdict = {
                    "action": "BLOCK",
                    "reason": "URL_REPUTATION_UNAVAILABLE",
                }
            elif stats["malicious"] >= URL_REPUTATION_MALICIOUS_THRESHOLD:
                logger.warning(
                    "URL reputation blocked malicious=%s suspicious=%s harmless=%s undetected=%s timeout=%s total=%s",
                    stats["malicious"],
                    stats["suspicious"],
                    stats["harmless"],
                    stats["undetected"],
                    stats["timeout"],
                    sum(stats.values()),
                )
                verdict = {
                    "action": "BLOCK",
                    "reason": "MALICIOUS_URL",
                    "malicious": stats["malicious"],
                    "total": sum(stats.values()),
                }
            else:
                logger.info(
                    "URL reputation allowed malicious=%s suspicious=%s harmless=%s undetected=%s timeout=%s total=%s",
                    stats["malicious"],
                    stats["suspicious"],
                    stats["harmless"],
                    stats["undetected"],
                    stats["timeout"],
                    sum(stats.values()),
                )
                verdict = {
                    "action": "ALLOW",
                    "reason": "CLEAN_URL",
                    "malicious": stats["malicious"],
                    "total": sum(stats.values()),
                }

        except (
            TimeoutError,
            OSError,
            ValueError,
            urllib.error.HTTPError,
            urllib.error.URLError,
        ) as exc:
            logger.warning(
                "URL reputation unavailable reason=service_failure error_type=%s",
                type(exc).__name__,
            )
            verdict = {
                "action": "BLOCK",
                "reason": "URL_REPUTATION_UNAVAILABLE",
            }

    url_reputation_cache[url] = {
        "expires_at": now + URL_REPUTATION_CACHE_TTL_SECONDS,
        "verdict": verdict,
    }
    return verdict


async def check_url_reputation(text):
    urls = extract_http_urls(text)

    if not urls:
        return None

    for url in urls:
        verdict = await get_url_reputation(url)

        if verdict["action"] == "BLOCK":
            if verdict["reason"] == "MALICIOUS_URL":
                return dict(MALICIOUS_URL_RESPONSE)

            return dict(URL_REPUTATION_UNAVAILABLE_RESPONSE)

    return None


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

                if not is_non_empty_string(username) or not is_non_empty_string(password):
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

                if not is_non_empty_string(username) or not is_non_empty_string(password):
                    await websocket.send_json({
                        "type": "LOGIN_RESULT",
                        "success": False,
                        "reason": "Username and password are required"
                    })
                    continue

                attempt_key = login_attempt_key(websocket, username)
                retry_after_seconds = login_cooldown_retry_after(attempt_key)

                if retry_after_seconds is not None:
                    logger.warning(
                        "Login cooldown rejection client_ip=%s username=%r retry_after_seconds=%s",
                        attempt_key[0],
                        attempt_key[1],
                        retry_after_seconds,
                    )

                    await websocket.send_json({
                        "type": "LOGIN_RESULT",
                        "success": False,
                        "reason": "LOGIN_RATE_LIMITED",
                        "retry_after_seconds": retry_after_seconds
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

                    retry_after_seconds = record_failed_login(attempt_key)

                    if retry_after_seconds is not None:
                        await websocket.send_json({
                            "type": "LOGIN_RESULT",
                            "success": False,
                            "reason": "LOGIN_RATE_LIMITED",
                            "retry_after_seconds": retry_after_seconds
                        })
                        continue

                    await websocket.send_json({
                        "type": "LOGIN_RESULT",
                        "success": False,
                        "reason": "Invalid username or password"
                    })

                else:

                    reset_failed_login(attempt_key)

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

                if not is_non_empty_string(room_name):
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

                if not is_valid_room_id(room_id):
                    await websocket.send_json({
                        "type": "JOIN_ROOM_RESULT",
                        "success": False,
                        "reason": "Valid room_id is required"
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

                if not is_valid_room_id(room_id):
                    await websocket.send_json({
                        "type": "LEAVE_ROOM_RESULT",
                        "success": False,
                        "room_id": room_id,
                        "reason": "Valid room_id is required"
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

                if not is_non_empty_string(text):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Message text is required"
                    })
                    continue

                if not is_valid_room_id(room_id):
                    await websocket.send_json({
                        "type": "ERROR",
                        "reason": "Valid room_id is required"
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

                spam_violation = check_message_rate_limit(user_id)

                if spam_violation in {"first", "cooldown"}:
                    await websocket.send_json(dict(ANTI_SPAM_BLOCK_RESPONSE))
                    continue

                if spam_violation == "second":
                    await websocket.send_json({
                        **ANTI_SPAM_BLOCK_RESPONSE,
                        "message": "Spam detected. You have been disconnected for sending messages too quickly.",
                    })
                    logger.warning(
                        "Disconnecting user for spam user_id=%s threshold=%s window_seconds=%s",
                        user_id,
                        ANTI_SPAM_THRESHOLD,
                        ANTI_SPAM_WINDOW_SECONDS,
                    )
                    connection_users.pop(websocket, None)
                    if websocket in active_connections:
                        active_connections.remove(websocket)
                    await websocket.close(code=1008)
                    return

                url_reputation_response = await check_url_reputation(text)

                if url_reputation_response is not None:
                    await websocket.send_json(url_reputation_response)
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
