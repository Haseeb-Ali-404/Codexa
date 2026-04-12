"""
Project file state keyed by chat → latest project document and files in MongoDB.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from utils.database_models_util import get_project_by_chat_id, update_project_timestamp
from utils.database_util import files_col, projects_col
from utils.file_utils import normalize_project_path


def get_project(chat_id: str) -> dict[str, Any] | None:
    return get_project_by_chat_id(chat_id)


def list_files_for_project(project_id: str) -> list[dict[str, Any]]:
    try:
        oid = ObjectId(project_id)
    except InvalidId:
        return []
    docs = list(
        files_col.find({"project_id": oid}, {"path": 1, "content": 1}).sort("path", 1)
    )
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def get_project_files(chat_id: str) -> tuple[str | None, list[dict[str, Any]]]:
    proj = get_project(chat_id)
    if not proj:
        return None, []
    pid = proj["_id"]
    return pid, list_files_for_project(pid)


def save_project(chat_id: str, project: dict[str, Any]) -> None:
    """
    In-memory shape helper (not used for persistence — router uses save_project + save_files).
    Kept for API symmetry with the architecture doc.
    """
    raise NotImplementedError("Persist via database_models_util.save_project and save_files")


def update_file(project_id: str, file_path: str, new_content: str) -> bool:
    path = normalize_project_path(file_path)
    try:
        oid = ObjectId(project_id)
    except InvalidId:
        return False
    res = files_col.update_one(
        {"project_id": oid, "path": path},
        {"$set": {"content": new_content, "updated_at": datetime.utcnow()}},
    )
    return res.matched_count > 0


def insert_file(project_id: str, file_path: str, content: str) -> str | None:
    path = normalize_project_path(file_path)
    try:
        oid = ObjectId(project_id)
    except InvalidId:
        return None
    now = datetime.utcnow()
    r = files_col.insert_one(
        {
            "project_id": oid,
            "path": path,
            "content": content,
            "created_at": now,
            "updated_at": now,
        }
    )
    return str(r.inserted_id)


def find_file_doc(project_id: str, file_path: str) -> dict[str, Any] | None:
    path = normalize_project_path(file_path)
    try:
        oid = ObjectId(project_id)
    except InvalidId:
        return None
    doc = files_col.find_one({"project_id": oid, "path": path})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def apply_change_record(
    project_id: str,
    change: dict[str, Any],
    *,
    chat_id: str | None = None,
) -> dict[str, Any]:
    """
    Apply one structured change: { file, type, before, after }.
    Returns normalized record including success flag.
    """
    path = (change.get("file") or "").strip()
    before = change.get("before")
    if before is None:
        before = ""
    after = change.get("after")
    if after is None:
        after = ""
    ctype = (change.get("type") or "modify").lower()

    result = {
        "file": path,
        "type": ctype,
        "before": before,
        "after": after,
        "ok": False,
        "error": None,
    }

    if not path:
        result["error"] = "empty path"
        return result

    doc = find_file_doc(project_id, path)

    if doc:
        current = doc.get("content") or ""
        result["before"] = current
        update_file(project_id, path, after)
        result["ok"] = True
        if before and before != current and current.strip() != (before or "").strip():
            result["warning"] = "model before snapshot differed; applied using live file content as baseline"
    else:
        if ctype == "add" or before == "":
            new_id = insert_file(project_id, path, after)
            result["ok"] = bool(new_id)
            result["before"] = ""
            if not new_id:
                result["error"] = "insert failed"
        else:
            result["error"] = "file not found"

    if chat_id:
        try:
            update_project_timestamp(chat_id)
        except Exception:
            pass
    try:
        projects_col.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"updated_at": datetime.utcnow()}},
        )
    except Exception:
        pass

    return result
