import os
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request

from models.schemas import AssetGenerationPayload
from services.ppt_service import default_ppt_service
from services.uml_service import default_uml_service
from utils.database_models_util import (
    delete_project_cascade,
    get_project_by_id,
    get_project_asset,
    get_user_projects,
    list_project_assets,
    update_project_title,
)

router = APIRouter(prefix="/projects")


def _public_base_url(request: Request) -> str:
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def _storage_url(request: Request, relative_path: str) -> str:
    clean_path = relative_path.replace("\\", "/").lstrip("/")
    return f"{_public_base_url(request)}/storage/{clean_path}"


def _can_embed_with_google(url: str) -> bool:
    lowered = url.lower()
    return not any(host in lowered for host in ("localhost", "127.0.0.1", "::1"))

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


@router.get("/{project_id}/assets")
def get_project_assets(project_id: str, request: Request):
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        uml_assets = []
        for asset in list_project_assets(project_id, asset_type="uml"):
            file_path = (asset.get("file_path") or "").strip()
            diagram_type = (asset.get("diagram_type") or "").strip()
            if not file_path or not diagram_type:
                continue
            uml_assets.append(
                {
                    "diagram_type": diagram_type,
                    "file_path": file_path,
                    "url": _storage_url(request, file_path),
                }
            )

        ppt_asset = get_project_asset(project_id, "ppt")
        ppt_url = None
        if ppt_asset:
            gcs_url = ppt_asset.get("meta", {}).get("gcs_url")
            print("GCS URL from asset:", gcs_url)
            file_path = ppt_asset.get("file_path")
            ppt_url = gcs_url or (_storage_url(request, file_path) if file_path else None)

        viewer_url = None
        if ppt_url and _can_embed_with_google(ppt_url):
            viewer_url = f"https://docs.google.com/gview?url={quote(ppt_url, safe='/:')}&embedded=true"

        return {
            "ok": True,
            "uml_images": [item["url"] for item in uml_assets],
            "diagrams": uml_assets,
            "ppt_url": ppt_url,
            "viewer_url": viewer_url,
        }
    except Exception as e:
        print(f"Error getting project assets: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting project assets: {str(e)}")


@router.post("/{project_id}/generate-uml")
def generate_project_uml(
    project_id: str,
    request: Request,
    body: AssetGenerationPayload | None = None,
):
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        payload = body or AssetGenerationPayload()
        result = default_uml_service.generate_uml(
            project_id,
            project_description=payload.description,
            diagram_types=payload.diagram_types,
            force=payload.force,
        )
        diagrams = [
            {
                "diagram_type": item["diagram_type"],
                "file_path": item["file_path"],
                "url": _storage_url(request, item["file_path"]),
            }
            for item in result["diagrams"]
        ]
        return {
            "ok": True,
            "cached": result["cached"],
            "uml_images": [item["url"] for item in diagrams],
            "diagrams": diagrams,
        }
    except Exception as e:
        print(f"Error generating UML diagrams: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating UML diagrams: {str(e)}")


@router.post("/{project_id}/generate-ppt")
def generate_project_ppt(
    project_id: str,
    request: Request,
    body: AssetGenerationPayload | None = None,
):
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        payload = body or AssetGenerationPayload()
        result = default_ppt_service.generate_ppt(
            project_id,
            project_description=payload.description,
            force=payload.force,
            include_uml=payload.include_uml,
        )
        gcs_url = result.get("gcs_url")
        print("GCS URL from PPT service:", gcs_url)
        ppt_url = gcs_url or _storage_url(request, result["file_path"])
        
        viewer_url = None
        if _can_embed_with_google(ppt_url):
            viewer_url = f"https://docs.google.com/gview?url={quote(ppt_url, safe='/:')}&embedded=true"
        
        return {
            "ok": True,
            "cached": result["cached"],
            "ppt_url": ppt_url,
            "viewer_url": viewer_url,
            "slides": result.get("slides", []),
            "uses_uml": result.get("uses_uml", False),
            "slide_count": len(result.get("slides", [])),
        }
    except Exception as e:
        print(f"Error generating PPT: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating PPT: {str(e)}")

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


