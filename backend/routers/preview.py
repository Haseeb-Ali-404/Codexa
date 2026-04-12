import os
import subprocess
import signal
from pathlib import Path
from fastapi import APIRouter
from bson import ObjectId
from utils.database_util import files_col
import psutil

router = APIRouter()

# ---------------------------------------
# CONFIG
# ---------------------------------------
BASE_PREVIEW_DIR = Path("/tmp/codexa")
FRONTEND_PORT = 5959
BACKEND_PORT = 7979

# ---------------------------------------
# GLOBAL PROCESS STATE (SINGLE PROJECT)
# ---------------------------------------
CURRENT_FRONTEND_PROCESS = None
CURRENT_BACKEND_PROCESS = None
CURRENT_PROJECT_ID = None


# ---------------------------------------
# UTIL: STOP ANY RUNNING PROJECT
# ---------------------------------------
def stop_current_project():
    global CURRENT_FRONTEND_PROCESS, CURRENT_BACKEND_PROCESS, CURRENT_PROJECT_ID

    # Kill all Node/Vite processes running in the frontend project directory
    # and any process listening on the backend port
    if CURRENT_PROJECT_ID:
        from pathlib import Path
        import psutil
        frontend_path = BASE_PREVIEW_DIR / CURRENT_PROJECT_ID / "frontend"
        # Kill Node/Vite (frontend)
        for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
            try:
                if (
                    proc.info["name"] and "node" in proc.info["name"].lower()
                    and proc.info["cwd"]
                    and Path(proc.info["cwd"]).resolve() == frontend_path.resolve()
                ):
                    proc.kill()
            except Exception:
                continue

        # Kill any process listening on the backend port
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == BACKEND_PORT:
                try:
                    p = psutil.Process(conn.pid)
                    p.kill()
                except Exception:
                    continue

    if CURRENT_FRONTEND_PROCESS:
        CURRENT_FRONTEND_PROCESS.terminate()
        CURRENT_FRONTEND_PROCESS = None

    if CURRENT_BACKEND_PROCESS:
        CURRENT_BACKEND_PROCESS.terminate()
        CURRENT_BACKEND_PROCESS = None

    CURRENT_PROJECT_ID = None


# ---------------------------------------
# REBUILD FRONTEND
# ---------------------------------------
def rebuild_frontend(project_id: str) -> Path:
    files = list(files_col.find({"project_id": ObjectId(project_id)}))
    frontend_path = BASE_PREVIEW_DIR / project_id / "frontend"
    frontend_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for file in files:
        if not file["path"].startswith("frontend/"):
            continue

        rel = file["path"].replace("frontend/", "")
        full = frontend_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(file["content"], encoding="utf-8")
        count += 1

    if count == 0:
        raise RuntimeError("No frontend files found")

    return frontend_path


# ---------------------------------------
# REBUILD BACKEND
# ---------------------------------------
def rebuild_backend(project_id: str) -> Path:
    files = list(files_col.find({"project_id": ObjectId(project_id)}))
    backend_path = BASE_PREVIEW_DIR / project_id / "backend"
    backend_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for file in files:
        if not file["path"].startswith("backend/"):
            continue

        rel = file["path"].replace("backend/", "")
        full = backend_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(file["content"], encoding="utf-8")
        count += 1

    if count == 0:
        raise RuntimeError("No backend files found")

    return backend_path


# ---------------------------------------
# RUN FRONTEND + BACKEND
# ---------------------------------------
def run_project(project_id: str):
    global CURRENT_FRONTEND_PROCESS, CURRENT_BACKEND_PROCESS, CURRENT_PROJECT_ID

    # 🔥 Stop previous project (important)
    stop_current_project()

    frontend_path = rebuild_frontend(project_id)
    backend_path = rebuild_backend(project_id)

    # ---------------- FRONTEND ----------------
    node_modules = frontend_path / "node_modules"
    if not node_modules.exists():
        subprocess.run(
            ["npm.cmd", "install"],
            cwd=str(frontend_path),
            shell=True,
            check=True
        )

    import time
    import threading

    def monitor_and_fix_frontend(proc, frontend_path):
        try:
            # Read stderr line by line for up to 10 seconds
            start = time.time()
            while time.time() - start < 10:
                line = proc.stderr.readline()
                if not line:
                    break
                if b"Cannot find module" in line:
                    # Remove node_modules and package-lock.json, then reinstall
                    subprocess.run(["rmdir", "/s", "/q", "node_modules"], cwd=str(frontend_path), shell=True)
                    subprocess.run(["del", "/f", "/q", "package-lock.json"], cwd=str(frontend_path), shell=True)
                    subprocess.run(["npm.cmd", "install"], cwd=str(frontend_path), shell=True, check=True)
                    # Restart frontend process
                    proc.terminate()
                    new_proc = subprocess.Popen(
                        ["npm.cmd", "run", "dev", "--", "--port", str(FRONTEND_PORT)],
                        cwd=str(frontend_path),
                        shell=True
                    )
                    return new_proc
        except Exception:
            pass
        return proc

    CURRENT_FRONTEND_PROCESS = subprocess.Popen(
        ["npm.cmd", "run", "dev", "--", "--port", str(FRONTEND_PORT)],
        cwd=str(frontend_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True
    )

    # Start a thread to monitor and fix 'Cannot find module' errors
    t = threading.Thread(target=monitor_and_fix_frontend, args=(CURRENT_FRONTEND_PROCESS, frontend_path))
    t.daemon = True
    t.start()


    # ---------------- BACKEND ----------------
    CURRENT_BACKEND_PROCESS = subprocess.Popen(
        [
            "uvicorn",
            "main:app",
            "--host", "127.0.0.1",
            "--port", str(BACKEND_PORT)
        ],
        cwd=str(backend_path),
        shell=True
    )

    CURRENT_PROJECT_ID = project_id

    return {
        "frontend": f"http://localhost:{FRONTEND_PORT}",
        "backend": f"http://localhost:{BACKEND_PORT}"
    }


# ---------------------------------------
# API: RUN FULL PROJECT
# ---------------------------------------
@router.post("/preview/full/{project_id}")
def preview_full(project_id: str):
    urls = run_project(project_id)
    return {
        "ok": True,
        "project_id": project_id,
        **urls
    }


# ---------------------------------------
# API: STOP PROJECT
# ---------------------------------------
@router.post("/preview/stop/{project_id}")
def stop_preview(project_id: str):
    """
    Stop the currently running project (frontend and backend) in the terminal.
    """
    stop_current_project()
    return {"ok": True, "status": "stopped"}


# ---------------------------------------
# API: STATUS
# ---------------------------------------
@router.get("/preview/status")
def preview_status():
    if CURRENT_PROJECT_ID:
        return {
            "status": "running",
            "project_id": CURRENT_PROJECT_ID,
            "frontend_port": FRONTEND_PORT,
            "backend_port": BACKEND_PORT
        }
    return {"status": "idle"}
