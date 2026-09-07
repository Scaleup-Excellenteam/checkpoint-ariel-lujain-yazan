import jwt
from pwdlib import PasswordHash
from datetime import datetime, timedelta, timezone

SECRET_KEY = "temporary-secret-key"
ALGORITHM = "HS256"

password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

#the auth has 2 jobs , 1-password functions : hash and verify password , 2-JWT functions : create login token