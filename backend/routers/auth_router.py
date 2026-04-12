from fastapi import APIRouter, HTTPException
from utils.database_util import users_col
from utils.auth_util import hash_password, verify_password, create_token
from models.schemas import Signup, Login

router = APIRouter(prefix="/auth")

@router.post("/signup")
def signup(payload: Signup):
    if payload.password != payload.confirm_password:
        raise HTTPException(400, "Passwords do not match")

    if users_col.find_one({"email": payload.email}):
        raise HTTPException(400, "Email already exists")

    hashed = hash_password(payload.password)

    res = users_col.insert_one({
        "name": payload.name,
        "email": payload.email,
        "password": hashed
    })
    token = create_token(str(res.inserted_id), str(payload.name), str(payload.email))
    return {"ok": True, "token": token}

@router.post("/login")
def login(payload: Login):
    user = users_col.find_one({"email": payload.email})
    if not user:
        raise HTTPException(400, "Invalid credentials")

    if not verify_password(payload.password, user["password"]):
        raise HTTPException(400, "Invalid credentials")

    token = create_token(str(user["_id"]), str(user["name"]), str(user["email"]))

    return {"ok": True, "token": token}
