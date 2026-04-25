import importlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional


Reporter = Optional[Callable[[str], None]]
StepCallback = Optional[Callable[[str], None]]
_DOCKER_SDK = None
_FRONTEND_BASE_IMAGE = "node:20-alpine"
_BACKEND_BASE_IMAGE = "python:3.11-slim"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _emit(reporter: Reporter, message: str) -> None:
    if reporter:
        try:
            reporter(message)
            return
        except Exception:
            pass
    print(f"[DockerRunner] {message}")


def _safe_resolve(entry: str) -> Optional[Path]:
    try:
        return Path(entry or ".").resolve()
    except Exception:
        return None


def _module_inside_workspace(module_obj: Any, workspace_root: Path) -> bool:
    module_file = getattr(module_obj, "__file__", None)
    if module_file:
        try:
            return workspace_root in Path(module_file).resolve().parents
        except Exception:
            return False

    module_paths = getattr(module_obj, "__path__", None) or []
    for module_path in module_paths:
        try:
            if workspace_root in Path(module_path).resolve().parents:
                return True
        except Exception:
            continue
    return False


def _load_docker_sdk():
    global _DOCKER_SDK
    if _DOCKER_SDK is not None:
        return _DOCKER_SDK

    workspace_root = _workspace_root().resolve()
    backend_root = (workspace_root / "backend").resolve()
    original_sys_path = list(sys.path)
    cached_module = sys.modules.get("docker")

    try:
        if cached_module is not None and _module_inside_workspace(cached_module, workspace_root):
            sys.modules.pop("docker", None)

        sys.path = [
            entry for entry in sys.path
            if _safe_resolve(entry) not in {workspace_root, backend_root}
        ]

        _DOCKER_SDK = importlib.import_module("docker")
        return _DOCKER_SDK
    finally:
        sys.path = original_sys_path


def _docker_client():
    docker_sdk = _load_docker_sdk()
    client = docker_sdk.from_env()
    try:
        client.ping()
    except Exception as exc:
        raise RuntimeError(f"Docker daemon is unavailable: {exc}") from exc
    return client


def _is_windows() -> bool:
    return os.name == "nt"


def _docker_desktop_exe() -> Optional[Path]:
    candidate = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
    return candidate if candidate.exists() else None


def _run_docker_cli(
    args: list[str],
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(detail)
    return completed


def _docker_version_available() -> bool:
    try:
        _run_docker_cli(["version"], check=True)
        return True
    except Exception:
        return False


def _ensure_docker_desktop_running(reporter: Reporter = None) -> None:
    if not _is_windows():
        return
    if _docker_version_available():
        return

    docker_desktop = _docker_desktop_exe()
    if docker_desktop is not None:
        _emit(reporter, "Docker Desktop is not running - starting it automatically")
        try:
            subprocess.Popen([str(docker_desktop)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            raise RuntimeError(f"Unable to start Docker Desktop automatically: {exc}") from exc

    deadline = time.time() + 90
    last_error = "Docker daemon is unavailable"
    while time.time() < deadline:
        try:
            _run_docker_cli(["version"], check=True)
            _emit(reporter, "Docker Desktop is ready")
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)

    raise RuntimeError(
        "Docker Desktop is installed but the daemon is still unavailable after waiting. "
        f"Last error: {last_error}"
    )


def _docker_image_id_cli(tag: str) -> Optional[str]:
    try:
        result = _run_docker_cli(["image", "inspect", tag, "--format", "{{.Id}}"], check=True)
        value = (result.stdout or "").strip()
        return value or None
    except Exception:
        return None


def _docker_list_containers_cli(project_id: Optional[str] = None) -> list[tuple[str, str]]:
    args = [
        "ps",
        "-a",
        "--format",
        "{{.ID}}\t{{.Names}}",
        "--filter",
        "label=codexa.preview=true",
    ]
    if project_id:
        args.extend(["--filter", f"label=codexa.preview.project_id={project_id}"])
    result = _run_docker_cli(args, check=False)
    rows = []
    for line in (result.stdout or "").splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[0].strip():
            rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def _load_preview_module():
    backend_root = _workspace_root() / "backend"
    backend_root_str = str(backend_root)
    if backend_root_str not in sys.path:
        sys.path.insert(0, backend_root_str)
    return importlib.import_module("routers.preview")


def _sanitize_project_id(project_id: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in project_id)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:48] or "preview"


def _frontend_image_tag(project_id: str) -> str:
    return f"codexa-preview-{_sanitize_project_id(project_id)}-frontend:latest"


def _backend_image_tag(project_id: str) -> str:
    return f"codexa-preview-{_sanitize_project_id(project_id)}-backend:latest"


def _frontend_container_name(project_id: str) -> str:
    return f"codexa-fe-{_sanitize_project_id(project_id)}"


def _backend_container_name(project_id: str) -> str:
    return f"codexa-be-{_sanitize_project_id(project_id)}"


def _frontend_modules_volume_name(project_id: str) -> str:
    return f"codexa-fe-modules-{_sanitize_project_id(project_id)}"


def _backend_site_packages_volume_name(project_id: str) -> str:
    return f"codexa-be-site-{_sanitize_project_id(project_id)}"


def _backend_pip_cache_volume_name(project_id: str) -> str:
    return f"codexa-be-pip-cache-{_sanitize_project_id(project_id)}"


def _docker_bind_mount(path: Path, target: str) -> str:
    return f"type=bind,source={path.resolve()},target={target}"


def _docker_named_volume_mount(volume_name: str, target: str) -> str:
    return f"type=volume,source={volume_name},target={target}"


def _docker_build_hash_file(preview_module: Any, project_id: str) -> Path:
    return preview_module.BASE_PREVIEW_DIR / project_id / ".docker_build_hash"


def _load_docker_build_hash(preview_module: Any, project_id: str) -> str:
    try:
        hash_file = _docker_build_hash_file(preview_module, project_id)
        return hash_file.read_text(encoding="utf-8").strip() if hash_file.exists() else ""
    except Exception:
        return ""


def _save_docker_build_hash(preview_module: Any, project_id: str, hash_value: str) -> None:
    try:
        _docker_build_hash_file(preview_module, project_id).write_text(hash_value, encoding="utf-8")
    except Exception:
        pass


def _image_id_for_tag(client: Any, tag: str) -> Optional[str]:
    if _is_windows():
        return _docker_image_id_cli(tag)
    try:
        return client.images.get(tag).id
    except Exception:
        return None


def _remove_image_by_id(client: Any, image_id: Optional[str], reporter: Reporter = None) -> None:
    if not image_id:
        return
    if _is_windows():
        try:
            _run_docker_cli(["image", "rm", image_id], check=False)
            _emit(reporter, f"Removed stale image {image_id[:18]}")
        except Exception:
            pass
        return
    try:
        client.images.remove(image=image_id, force=False, noprune=False)
        _emit(reporter, f"Removed stale image {image_id[:18]}")
    except Exception:
        pass


def _resolve_backend_uvicorn_module(backend_path: Path) -> str:
    if (backend_path / "main.py").exists():
        return "main:app"

    for candidate in ["app/main.py", "src/main.py"]:
        if (backend_path / candidate).exists():
            return candidate.replace("/", ".").replace(".py", "") + ":app"

    discovered = sorted(backend_path.rglob("main.py"))
    if discovered:
        rel = discovered[0].relative_to(backend_path)
        return str(rel.with_suffix("")).replace("\\", ".").replace("/", ".") + ":app"

    return "main:app"


def _ensure_frontend_dockerfile(frontend_path: Path) -> Path:
    existing = frontend_path / "Dockerfile"
    if existing.exists():
        return existing

    generated = frontend_path / ".codexa.frontend.Dockerfile"
    generated.write_text(
        "\n".join(
            [
                "FROM node:20-alpine",
                "WORKDIR /app",
                "COPY package*.json ./",
                "RUN npm install",
                "COPY . .",
                "EXPOSE 5959",
                'CMD ["sh", "-lc", "npm run dev -- --host 0.0.0.0 --port 5959"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return generated


def _ensure_backend_dockerfile(backend_path: Path, uvicorn_module: str) -> Path:
    existing = backend_path / "Dockerfile"
    if existing.exists():
        return existing

    generated = backend_path / ".codexa.backend.Dockerfile"
    generated.write_text(
        "\n".join(
            [
                "FROM python:3.11-slim",
                "WORKDIR /app",
                "ENV PYTHONDONTWRITEBYTECODE=1",
                "ENV PYTHONUNBUFFERED=1",
                "COPY requirements.txt ./",
                'RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi',
                "COPY . .",
                "EXPOSE 7979",
                (
                    'CMD ["python", "-m", "uvicorn", '
                    f'"{uvicorn_module}", "--host", "0.0.0.0", "--port", "7979", "--lifespan", "off"]'
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return generated


def _container_filters(project_id: Optional[str] = None) -> dict[str, list[str]]:
    labels = ["codexa.preview=true"]
    if project_id:
        labels.append(f"codexa.preview.project_id={project_id}")
    return {"label": labels}


def stop_project_docker(project_id: Optional[str] = None, reporter: Reporter = None) -> list[Any]:
    if _is_windows():
        if reporter is not None:
            _ensure_docker_desktop_running(reporter=reporter)
        elif not _docker_version_available():
            return []
        containers = _docker_list_containers_cli(project_id)
        for container_id, container_name in containers:
            try:
                _emit(reporter, f"Stopping container {container_name}")
                _run_docker_cli(["rm", "-f", container_id], check=False)
            except Exception:
                pass
        return containers

    client = _docker_client()
    containers = client.containers.list(all=True, filters=_container_filters(project_id))
    for container in containers:
        try:
            _emit(reporter, f"Stopping container {container.name}")
            container.stop(timeout=8)
        except Exception:
            pass
        try:
            container.remove(force=True)
        except Exception:
            pass
    return containers


def _wait_for_port(port: int, timeout: int = 45) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.75):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def build_images(frontend_path: Path, backend_path: Path, project_id: str, reporter: Reporter = None) -> dict:
    _emit(reporter, "Skipping Docker image builds - using base runtime images with mounted project files")
    return {
        "frontend_tag": _FRONTEND_BASE_IMAGE,
        "backend_tag": _BACKEND_BASE_IMAGE,
        "frontend_image_id": None,
        "backend_image_id": None,
        "previous_frontend_image_id": None,
        "previous_backend_image_id": None,
        "frontend_dockerfile": None,
        "backend_dockerfile": None,
        "backend_uvicorn_module": _resolve_backend_uvicorn_module(backend_path),
        "build_skipped": True,
    }


def _start_container_log_stream_cli(container_name: str, reporter: Reporter = None) -> None:
    if reporter is None:
        return

    def _pump() -> None:
        proc: Optional[subprocess.Popen[str]] = None
        try:
            proc = subprocess.Popen(
                ["docker", "logs", "-f", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.stdout is None:
                return
            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                if line:
                    _emit(reporter, f"[Docker][{container_name}] {line}")
        except Exception:
            pass
        finally:
            try:
                if proc is not None and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass

    threading.Thread(target=_pump, daemon=True).start()


def _start_container_log_stream_sdk(container: Any, reporter: Reporter = None) -> None:
    if reporter is None:
        return

    def _pump() -> None:
        try:
            for chunk in container.logs(stdout=True, stderr=True, stream=True, follow=True):
                text = chunk.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue
                for line in text.splitlines():
                    if line:
                        _emit(reporter, f"[Docker][{container.name}] {line}")
        except Exception:
            pass

    threading.Thread(target=_pump, daemon=True).start()


def run_project_docker(
    project_id: str,
    reporter: Reporter = None,
    step_callback: StepCallback = None,
) -> dict:
    preview = _load_preview_module()
    client = None if _is_windows() else _docker_client()

    if step_callback:
        step_callback("copying")
    _emit(reporter, f"Preparing Docker execution for project {project_id}")
    frontend_path, _ = preview.rebuild_frontend(project_id)
    backend_path = preview.rebuild_backend(project_id)
    preview._ensure_backend_essentials(backend_path)

    _emit(reporter, "Removing previous Docker containers for this project")
    stop_project_docker(project_id, reporter=reporter)
    try:
        preview._kill_port(preview.FRONTEND_PORT)
        preview._kill_port(preview.BACKEND_PORT)
    except Exception:
        pass

    if step_callback:
        step_callback("dependencies")
    images = build_images(frontend_path, backend_path, project_id, reporter=reporter)

    common_labels = {
        "codexa.preview": "true",
        "codexa.preview.project_id": project_id,
    }
    backend_uvicorn_module = images.get("backend_uvicorn_module") or _resolve_backend_uvicorn_module(backend_path)
    frontend_command = (
        "FRONTEND_HASH=\"$(cat package-lock.json package.json 2>/dev/null | sha1sum | cut -d' ' -f1)\"; "
        "if [ ! -f node_modules/.codexa-hash ] || [ \"$(cat node_modules/.codexa-hash 2>/dev/null)\" != \"$FRONTEND_HASH\" ]; then "
        "npm install --no-audit --no-fund && "
        "mkdir -p node_modules && printf '%s' \"$FRONTEND_HASH\" > node_modules/.codexa-hash; "
        "fi && npm run dev -- --host 0.0.0.0 --port 5959"
    )
    backend_command = (
        "REQ_HASH=\"$(cat requirements.txt 2>/dev/null | sha1sum | cut -d' ' -f1)\"; "
        "REQ_MARKER=\"/usr/local/lib/python3.11/site-packages/.codexa-req-hash\"; "
        "if [ ! -f \"$REQ_MARKER\" ] || [ \"$(cat \"$REQ_MARKER\" 2>/dev/null)\" != \"$REQ_HASH\" ]; then "
        "pip install -r requirements.txt && "
        "printf '%s' \"$REQ_HASH\" > \"$REQ_MARKER\"; "
        "fi && "
        f"python -m uvicorn {backend_uvicorn_module} --host 0.0.0.0 --port 7979"
    )

    if step_callback:
        step_callback("start_backend")
    _emit(reporter, f"Starting backend container on :{preview.BACKEND_PORT}")
    if _is_windows():
        backend_run = _run_docker_cli(
            [
                "run",
                "-d",
                "--name",
                _backend_container_name(project_id),
                "-p",
                f"{preview.BACKEND_PORT}:{preview.BACKEND_PORT}",
                "--workdir",
                "/app",
                "--mount",
                _docker_bind_mount(backend_path, "/app"),
                "--mount",
                _docker_named_volume_mount(
                    _backend_site_packages_volume_name(project_id),
                    "/usr/local/lib/python3.11/site-packages",
                ),
                "--mount",
                _docker_named_volume_mount(
                    _backend_pip_cache_volume_name(project_id),
                    "/root/.cache/pip",
                ),
                "--label",
                "codexa.preview=true",
                "--label",
                f"codexa.preview.project_id={project_id}",
                "--label",
                "codexa.preview.role=backend",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-e",
                "PYTHONUNBUFFERED=1",
                images["backend_tag"],
                "sh",
                "-c",
                backend_command,
            ],
            check=True,
            timeout=900,
        )
        backend_container = (backend_run.stdout or "").strip() or _backend_container_name(project_id)
        _start_container_log_stream_cli(_backend_container_name(project_id), reporter=reporter)
    else:
        backend_container = client.containers.run(
            images["backend_tag"],
            name=_backend_container_name(project_id),
            detach=True,
            ports={f"{preview.BACKEND_PORT}/tcp": preview.BACKEND_PORT},
            working_dir="/app",
            command=["sh", "-c", backend_command],
            environment={
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            },
            volumes={
                str(backend_path.resolve()): {"bind": "/app", "mode": "rw"},
                _backend_site_packages_volume_name(project_id): {
                    "bind": "/usr/local/lib/python3.11/site-packages",
                    "mode": "rw",
                },
                _backend_pip_cache_volume_name(project_id): {
                    "bind": "/root/.cache/pip",
                    "mode": "rw",
                },
            },
            labels={**common_labels, "codexa.preview.role": "backend"},
        )
        _start_container_log_stream_sdk(backend_container, reporter=reporter)

    if step_callback:
        step_callback("start_frontend")
    _emit(reporter, f"Starting frontend container on :{preview.FRONTEND_PORT}")
    if _is_windows():
        frontend_run = _run_docker_cli(
            [
                "run",
                "-d",
                "--name",
                _frontend_container_name(project_id),
                "-p",
                f"{preview.FRONTEND_PORT}:{preview.FRONTEND_PORT}",
                "--workdir",
                "/app",
                "--mount",
                _docker_bind_mount(frontend_path, "/app"),
                "--mount",
                _docker_named_volume_mount(
                    _frontend_modules_volume_name(project_id),
                    "/app/node_modules",
                ),
                "--label",
                "codexa.preview=true",
                "--label",
                f"codexa.preview.project_id={project_id}",
                "--label",
                "codexa.preview.role=frontend",
                images["frontend_tag"],
                "sh",
                "-c",
                frontend_command,
            ],
            check=True,
            timeout=900,
        )
        frontend_container = (frontend_run.stdout or "").strip() or _frontend_container_name(project_id)
        _start_container_log_stream_cli(_frontend_container_name(project_id), reporter=reporter)
    else:
        frontend_container = client.containers.run(
            images["frontend_tag"],
            name=_frontend_container_name(project_id),
            detach=True,
            ports={f"{preview.FRONTEND_PORT}/tcp": preview.FRONTEND_PORT},
            working_dir="/app",
            command=["sh", "-c", frontend_command],
            volumes={
                str(frontend_path.resolve()): {"bind": "/app", "mode": "rw"},
                _frontend_modules_volume_name(project_id): {
                    "bind": "/app/node_modules",
                    "mode": "rw",
                },
            },
            labels={**common_labels, "codexa.preview.role": "frontend"},
        )
        _start_container_log_stream_sdk(frontend_container, reporter=reporter)

    backend_ready = _wait_for_port(preview.BACKEND_PORT, timeout=120)
    frontend_ready = _wait_for_port(preview.FRONTEND_PORT, timeout=120)

    if not frontend_ready:
        log_excerpt = capture_container_logs(project_id, timeout=6)
        raise RuntimeError(
            "Docker frontend container did not bind to port 5959."
            + (f" Logs: {log_excerpt[-1200:]}" if log_excerpt else "")
        )

    if not backend_ready:
        _emit(reporter, "Backend container did not bind to port 7979; continuing with frontend-only preview")

    return {
        "ok": True,
        "frontend": f"http://localhost:{preview.FRONTEND_PORT}",
        "backend": f"http://localhost:{preview.BACKEND_PORT}" if backend_ready else None,
        "frontend_ready": frontend_ready,
        "backend_ready": backend_ready,
        "frontend_container": frontend_container,
        "backend_container": backend_container,
        "images": images,
        "logs_streamed": True,
    }


def capture_container_logs(project_id: str, timeout: int = 10) -> str:
    if _is_windows():
        if not _docker_version_available():
            return ""
        containers = _docker_list_containers_cli(project_id)
        if not containers:
            return ""
        lines: list[str] = []
        for _, container_name in containers:
            try:
                result = _run_docker_cli(
                    ["logs", "--since", f"{int(timeout)}s", container_name],
                    check=False,
                )
                combined = "\n".join(
                    part for part in [result.stdout or "", result.stderr or ""] if part
                )
                for line in combined.splitlines():
                    text = line.strip()
                    if text:
                        lines.append(f"[{container_name}] {text}")
            except Exception as exc:
                lines.append(f"[{container_name}] Unable to read logs: {exc}")
        return "\n".join(lines)

    client = _docker_client()
    containers = client.containers.list(all=True, filters=_container_filters(project_id))
    if not containers:
        return ""

    since_ts = max(int(time.time()) - int(timeout), 0)
    lines: list[str] = []
    for container in containers:
        try:
            for chunk in container.logs(
                stdout=True,
                stderr=True,
                stream=True,
                follow=False,
                since=since_ts,
            ):
                text = chunk.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue
                for line in text.splitlines():
                    lines.append(f"[{container.name}] {line}")
        except Exception as exc:
            lines.append(f"[{container.name}] Unable to read logs: {exc}")
    return "\n".join(lines)
