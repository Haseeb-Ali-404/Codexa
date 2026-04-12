from datetime import datetime
from bson import ObjectId
from utils.database_util import files_col


def normalize_project_path(path: str) -> str:
    """
    Normalize LLM-generated paths into Codexa-valid structure.
    """

    normalized = path.strip()

    # 🔥 Fix Vite HTML entry
    if normalized == "frontend/public/index.html":
        return "frontend/index.html"

    return normalized


def flatten_structure(structure, base_path=""):
    files = []

    for node in structure:
        current_path = f"{base_path}/{node['name']}".lstrip("/")

        if node["type"] == "file":
            files.append({
                "path": current_path,
                "content": node.get("content", "")
            })

        elif node["type"] == "folder":
            files.extend(
                flatten_structure(
                    node.get("children", []),
                    current_path
                )
            )

    return files


def save_files(project_id: str, structure):
    files = flatten_structure(structure)

    now = datetime.utcnow()

    for f in files:
        files_col.insert_one({
            "project_id": ObjectId(project_id),
            "path": normalize_project_path(f["path"]),
            "content": f["content"],
            "created_at": now,
            "updated_at": now
        })
