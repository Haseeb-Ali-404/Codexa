from fastapi import APIRouter, HTTPException, Query
from utils.database_models_util import get_user_projects, update_project_title, delete_project_cascade

router = APIRouter(prefix="/projects")

@router.get("/{user_id}")
def list_projects(user_id: str):
    """
    Return all projects created by a user.
    """
    projects = get_user_projects(user_id)

    return {
        "ok": True,
        "count": len(projects),
        "projects": projects
    }

@router.patch("/{project_id}")
def rename_project(project_id: str, user_id: str = Query(...), title: str = Query(...)):
    """
    Rename a project by ID.
    """
    success = update_project_title(project_id, user_id, title)
    if success:
        return {"ok": True}
    else:
        raise HTTPException(status_code=400, detail="Failed to rename project")

@router.delete("/{project_id}")
def delete_project(project_id: str, user_id: str = Query(...)):
    """
    Delete a project by ID.
    """
    success = delete_project_cascade(project_id, user_id)
    if success:
        return {"ok": True}
    else:
        raise HTTPException(status_code=400, detail="Failed to delete project")


