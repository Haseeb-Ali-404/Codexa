from fastapi import APIRouter, HTTPException
from utils.database_util import files_col
from bson import ObjectId
import os

router = APIRouter(prefix="/files")


@router.get("/{project_id}")
def get_project_files(project_id: str):
    files = list(
        files_col.find(
            {"project_id": ObjectId(project_id)},
            {"content": 1, "path": 1}
        )
    )

    if not files:
        raise HTTPException(status_code=404, detail="No files found")

    for f in files:
        f["_id"] = str(f["_id"])

    return {
        "ok": True,
        "files": files
    }




@router.put("/{file_id}/file")
def update_file(file_id: str, payload: dict):
    project_id = payload.get("project_id")
    path = payload.get("path")
    content = payload.get("content")

    # ✅ 1. Update MongoDB using file_id
    db = files_col.update_one(
        {"_id": ObjectId(file_id)},
        {"$set": {"content": content}}
    )
    print(f"MongoDB update result: {db.raw_result}")
    print(f"Updated file in DB with ID: {file_id}")
    # ✅ 2. Update local filesystem
    BASE_PATH = f"C:\\tmp\\codexa\\{project_id}"

    full_path = os.path.normpath(
        os.path.join(BASE_PATH, path)
    )
    print(f"Updating file at: {full_path}")
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"ok": True}
