import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers.auth_router import router as auth_router
from routers.chat_router import router as chat_router
from routers.projects_router import router as projects_router
from routers.project_files_router import router as files_router
from routers.preview import router as preview_router
from routers.metrics_router import router as metrics_router
from fastapi.middleware.cors import CORSMiddleware


_REPO_ROOT = Path(__file__).resolve().parent.parent
_STORAGE_ROOT = Path(os.getenv("CODEXA_STORAGE_ROOT", _REPO_ROOT / "storage"))


def create_app():
    app = FastAPI()
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(projects_router)
    app.include_router(files_router)
    app.include_router(preview_router)
    app.include_router(metrics_router)
    app.mount("/storage", StaticFiles(directory=str(_STORAGE_ROOT)), name="storage")

    return app
