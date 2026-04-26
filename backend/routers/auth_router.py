from bson import ObjectId
from fastapi import APIRouter, Header, HTTPException

from models.schemas import (
    Login,
    PasswordChangePayload,
    ProfileUpdatePayload,
    Signup,
)
from utils.auth_util import create_token, decode_token, hash_password, verify_password
from utils.database_util import (
    chats_col,
    files_col,
    messages_col,
    project_assets_col,
    projects_col,
    users_col,
)

router = APIRouter(prefix="/auth")


def _user_response(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "name": str(user.get("name") or ""),
        "email": str(user.get("email") or ""),
    }


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(401, "Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Invalid authorization header")
    return token.strip()


def _get_current_user(authorization: str | None) -> dict:
    token = _extract_bearer_token(authorization)
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(401, str(exc)) from exc

    user_id = payload.get("user_id")
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(401, "Invalid token payload")

    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.post("/signup")
def signup(payload: Signup):
    if payload.password != payload.confirm_password:
        raise HTTPException(400, "Passwords do not match")

    if users_col.find_one({"email": payload.email}):
        raise HTTPException(400, "Email already exists")

    hashed = hash_password(payload.password)

    res = users_col.insert_one({
        "name": payload.name.strip(),
        "email": payload.email.strip().lower(),
        "password": hashed
    })
    token = create_token(str(res.inserted_id), str(payload.name.strip()), str(payload.email.strip().lower()))
    return {"ok": True, "token": token}


@router.post("/login")
def login(payload: Login):
    user = users_col.find_one({"email": payload.email.strip().lower()})
    if not user:
        raise HTTPException(400, "Invalid credentials")

    if not verify_password(payload.password, user["password"]):
        raise HTTPException(400, "Invalid credentials")

    token = create_token(str(user["_id"]), str(user["name"]), str(user["email"]))

    return {"ok": True, "token": token}


@router.get("/me")
def get_me(authorization: str | None = Header(default=None)):
    user = _get_current_user(authorization)
    return {"ok": True, "user": _user_response(user)}


@router.patch("/profile")
def update_profile(
    payload: ProfileUpdatePayload,
    authorization: str | None = Header(default=None),
):
    user = _get_current_user(authorization)

    name = payload.name.strip()
    email = payload.email.strip().lower()

    if len(name) < 2:
        raise HTTPException(400, "Display name must be at least 2 characters")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Enter a valid email address")

    existing = users_col.find_one({
        "email": email,
        "_id": {"$ne": user["_id"]},
    })
    if existing:
        raise HTTPException(400, "Email already exists")

    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"name": name, "email": email}},
    )

    refreshed = users_col.find_one({"_id": user["_id"]}) or {
        "_id": user["_id"],
        "name": name,
        "email": email,
    }
    token = create_token(str(refreshed["_id"]), str(refreshed["name"]), str(refreshed["email"]))
    return {"ok": True, "token": token, "user": _user_response(refreshed)}


@router.post("/change-password")
def change_password(
    payload: PasswordChangePayload,
    authorization: str | None = Header(default=None),
):
    user = _get_current_user(authorization)

    if not verify_password(payload.current_password, user["password"]):
        raise HTTPException(400, "Current password is incorrect")

    new_password = payload.new_password
    if len(new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")

    if verify_password(new_password, user["password"]):
        raise HTTPException(400, "New password must be different from the current password")

    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": hash_password(new_password)}},
    )

    refreshed = users_col.find_one({"_id": user["_id"]}) or user
    token = create_token(str(refreshed["_id"]), str(refreshed["name"]), str(refreshed["email"]))
    return {"ok": True, "token": token}


@router.delete("/account")
def delete_account(authorization: str | None = Header(default=None)):
    user = _get_current_user(authorization)
    user_id = str(user["_id"])

    chats = list(chats_col.find({"user_id": user_id}, {"_id": 1}))
    chat_ids = [str(chat["_id"]) for chat in chats]

    projects = list(projects_col.find({"user_id": user_id}, {"_id": 1}))
    project_ids = [project["_id"] for project in projects]

    if project_ids:
        files_col.delete_many({"project_id": {"$in": project_ids}})
        project_assets_col.delete_many({"project_id": {"$in": project_ids}})

    if chat_ids:
        messages_col.delete_many({"chat_id": {"$in": chat_ids}})

    projects_col.delete_many({"user_id": user_id})
    chats_col.delete_many({"user_id": user_id})
    users_col.delete_one({"_id": user["_id"]})

    return {"ok": True}
