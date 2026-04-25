from utils.database_util import (
    chats_col,
    files_col,
    messages_col,
    project_assets_col,
    projects_col,
)
from datetime import datetime
from bson import ObjectId



# ---------- CHATS ----------

def create_chat(user_id: str, title: str, description: str):
    chat = {
        "user_id": user_id,
        "title": title,
        "description": description,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    res = chats_col.insert_one(chat)
    return str(res.inserted_id)

def get_user_chats(user_id: str):
    cursor = chats_col.find({"user_id": user_id}).sort("created_at", -1)

    chats = []
    for p in cursor:
        p["_id"] = str(p["_id"])
        chats.append(p)

    return chats


def update_chat_title(chat_id: str, user_id: str, title: str) -> bool:
    try:
        oid = ObjectId(chat_id)
    except Exception:
        return False
    title = (title or "").strip()
    if not title:
        return False
    res = chats_col.update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"title": title, "updated_at": datetime.utcnow()}},
    )
    return res.matched_count > 0


def delete_chat_cascade(chat_id: str, user_id: str) -> bool:
    """
    Remove chat, its messages, linked projects, and project files.
    """
    try:
        oid = ObjectId(chat_id)
    except Exception:
        return False
    chat = chats_col.find_one({"_id": oid})
    if not chat or chat.get("user_id") != user_id:
        return False

    projs = list(projects_col.find({"chat_id": chat_id}))
    pids = [p["_id"] for p in projs]
    if pids:
        files_col.delete_many({"project_id": {"$in": pids}})
        project_assets_col.delete_many({"project_id": {"$in": pids}})
    projects_col.delete_many({"chat_id": chat_id})
    messages_col.delete_many({"chat_id": chat_id})
    chats_col.delete_one({"_id": oid})
    return True



def update_project_timestamp(chat_id: str):
    chats_col.update_one(
        {"_id": ObjectId(chat_id)},
        {"$set": {"updated_at": datetime.utcnow()}}
    )



# ---------- CHAT MESSAGES ----------
def convert_messages_to_text(messages):
    lines = []
    for m in messages:
        role = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)

def save_message(
    chat_id: str,
    role: str,
    content: str,
    agent: str = None,
    **extra_fields,
):
    msg = {
        "chat_id": chat_id,
        "role": role,              # "user" or "assistant"
        "content": content,
        "agent": agent,            # optional: planner / developer / debugger / chat
        "created_at": datetime.utcnow()
    }

    for key, value in extra_fields.items():
        if value is not None:
            msg[key] = value

    messages_col.insert_one(msg)
    return True

def format_for_gemini(messages):
    formatted = []

    for m in messages:
        formatted.append({
            "role": m["role"],
            "content": m["content"]
        })

    return formatted


def format_chat_messages(messages):
    """Provider-agnostic alias (same shape: role + content)."""
    return format_for_gemini(messages)



def get_chat_messages(chat_id: str):
    try:
        msgs = list(
            messages_col.find(
                {"chat_id": chat_id}
            ).sort("created_at", 1)
        )
        print(f"Loaded {len(msgs)} messages for chat_id {chat_id}") 

        for m in msgs:
            m["_id"] = str(m["_id"])

        return msgs

    except Exception as e:
        print("Error loading messages:", e)
        return []


# ---------- PROJECTS ----------
def get_project_by_chat_id(chat_id: str):
    """
    Latest project document linked to this chat (by created_at desc).
    """
    try:
        p = projects_col.find_one(
            {"chat_id": chat_id},
            sort=[("created_at", -1)],
        )
        if not p:
            return None
        p["_id"] = str(p["_id"])
        return p
    except Exception as e:
        print("get_project_by_chat_id error:", e)
        return None


def get_project_by_id(project_id: str):
    try:
        oid = ObjectId(project_id)
    except Exception:
        return None
    try:
        project = projects_col.find_one({"_id": oid})
        if not project:
            return None
        project["_id"] = str(project["_id"])
        return project
    except Exception as e:
        print("get_project_by_id error:", e)
        return None


def save_project(
    user_id: str,
    title: str,
    description: str,
    chat_id: str,
    plan: dict = None,
    *,
    project_type: str = "fullstack",
):
    project = {
    "user_id": user_id,
    "title": title,
    "description": description,
    "plan": plan,                     # planner steps (optional but useful)
    "chat_id": chat_id,               # link chat ↔ project
    "status": "generated",            # generated | editing | completed
    "project_type": project_type,     # frontend | backend | fullstack | small_project
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow()

    }

    res = projects_col.insert_one(project)
    print("Saved project with ID:", str(res.inserted_id))
    return str(res.inserted_id)



def get_user_projects(user_id: str):
    cursor = projects_col.find({"user_id": user_id}).sort("created_at", -1)

    projects = []
    for p in cursor:
        p["_id"] = str(p["_id"])
        projects.append(p)

    return projects


def update_project_title(project_id: str, user_id: str, title: str) -> bool:
    try:
        oid = ObjectId(project_id)
    except Exception:
        return False
    title = (title or "").strip()
    if not title:
        return False
    res = projects_col.update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"title": title, "updated_at": datetime.utcnow()}},
    )
    return res.matched_count > 0


def delete_project_cascade(project_id: str, user_id: str) -> bool:
    """
    Remove project and its associated files.
    """
    try:
        oid = ObjectId(project_id)
    except Exception:
        return False
    project = projects_col.find_one({"_id": oid})
    if not project or project.get("user_id") != user_id:
        return False

    # Delete associated files
    files_col.delete_many({"project_id": oid})
    project_assets_col.delete_many({"project_id": oid})
    # Delete the project
    projects_col.delete_one({"_id": oid})
    return True


def upsert_project_asset(
    project_id: str,
    asset_type: str,
    file_path: str,
    *,
    diagram_type: str | None = None,
    source_hash: str | None = None,
    meta: dict | None = None,
):
    try:
        oid = ObjectId(project_id)
    except Exception:
        return None

    selector = {
        "project_id": oid,
        "type": asset_type,
    }
    if diagram_type:
        selector["diagram_type"] = diagram_type

    now = datetime.utcnow()
    update_fields = {
        "project_id": oid,
        "type": asset_type,
        "file_path": file_path,
        "updated_at": now,
    }
    if diagram_type:
        update_fields["diagram_type"] = diagram_type
    if source_hash:
        update_fields["source_hash"] = source_hash
    if meta is not None:
        update_fields["meta"] = meta

    project_assets_col.update_one(
        selector,
        {
            "$set": update_fields,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return get_project_asset(project_id, asset_type, diagram_type=diagram_type)


def get_project_asset(
    project_id: str,
    asset_type: str,
    *,
    diagram_type: str | None = None,
):
    try:
        oid = ObjectId(project_id)
    except Exception:
        return None

    query = {
        "project_id": oid,
        "type": asset_type,
    }
    if diagram_type:
        query["diagram_type"] = diagram_type

    doc = project_assets_col.find_one(query, sort=[("updated_at", -1)])
    if not doc:
        return None

    doc["_id"] = str(doc["_id"])
    doc["project_id"] = str(doc["project_id"])
    return doc


def list_project_assets(project_id: str, asset_type: str | None = None):
    try:
        oid = ObjectId(project_id)
    except Exception:
        return []

    query = {"project_id": oid}
    if asset_type:
        query["type"] = asset_type

    docs = list(project_assets_col.find(query).sort("updated_at", -1))
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        doc["project_id"] = str(doc["project_id"])
    return docs
