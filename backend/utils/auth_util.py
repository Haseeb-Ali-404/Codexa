import bcrypt, jwt, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Any

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGO = os.getenv("JWT_ALGO")


def hash_password(password: str):
    pw = password.encode("utf-8")[:72]     # bcrypt limit
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw, salt)

def verify_password(password: str, hashed: bytes | str):
    pw = password.encode("utf-8")[:72]
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(pw, hashed)

def create_token(user_id: str, name: str = "", email: str = ""):
    payload = {
        "user_id": user_id,
        "name": name,
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")


def verify_token(token: str):
    decoded = decode_token(token)
    return decoded.get("user_id") or decoded.get("sub")

