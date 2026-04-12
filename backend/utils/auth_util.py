import bcrypt, jwt, os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGO = os.getenv("JWT_ALGO")


def hash_password(password: str):
    pw = password.encode("utf-8")[:72]     # bcrypt limit
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw, salt)

def verify_password(password: str, hashed: bytes):
    pw = password.encode("utf-8")[:72]
    return bcrypt.checkpw(pw, hashed)

def create_token(user_id: str, name: str = "", email: str = ""):
    payload = {
        "user_id": user_id,
        "name": name,
        "email":email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def verify_token(token: str):
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return decoded["sub"]
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")

