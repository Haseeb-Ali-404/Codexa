import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter
from fastapi import Body
from fastapi.responses import StreamingResponse
from bson import ObjectId
from models.schemas import PreviewStartPayload
from utils.database_util import files_col
import psutil
from core.agents.debugger_agent import DebuggerAgent
from core.validation.code_validator import validate_python, validate_typescript
from core.validation.auto_fixer import fix_errors


def _strip_md_fences(content: str) -> str:
    """Remove markdown code fences LLMs sometimes add around file contents."""
    s = content.strip()
    if not s.startswith("```"):
        return content
    lines = s.splitlines()
    end = len(lines)
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip() == "```":
            end = i
            break
    return "\n".join(lines[1:end])


router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
BASE_PREVIEW_DIR = Path("/tmp/codexa")
FRONTEND_PORT = 5959
BACKEND_PORT = 7979

# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL PROCESS STATE
# ──────────────────────────────────────────────────────────────────────────────
CURRENT_FRONTEND_PROCESS = None
CURRENT_BACKEND_PROCESS = None
CURRENT_PROJECT_ID = None

# ──────────────────────────────────────────────────────────────────────────────
# REAL-TIME BUILD STATE  (SSE + status endpoint)
# ──────────────────────────────────────────────────────────────────────────────
_PREVIEW_STATE: dict = {
    "phase": "idle",       # idle | starting | ready | error
    "step": None,
    "steps_done": [],
    "error": None,
    "frontend_url": None,
    "backend_url": None,
    "started_at": None,
    "elapsed": None,
    "project_id": None,
    "execution_mode": "local",
}
_LOG_LINES: list = []
_STATE_LOCK = threading.Lock()
_PROCESS_LOG_PIDS: set[int] = set()
_PROJECT_FILE_HASHES: dict = {}   # project_id → MD5 of last-built file set
_RUNTIME_REPORT_HISTORY: dict[str, float] = {}

_PREVIEW_RUNTIME_PROBE_MARKER = "window.__codexaPreviewMonitorInstalled"
_PREVIEW_RUNTIME_PROBE_SNIPPET = """<script>
(() => {
  if (window.__codexaPreviewMonitorInstalled) return;
  window.__codexaPreviewMonitorInstalled = true;
  const queue = [];
  const signatures = [];

  const formatValue = (value) => {
    if (typeof value === "string") return value;
    if (value instanceof Error) return value.stack || value.message || String(value);
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  };

  const pushIssue = (type, rawMessage) => {
    const message = String(rawMessage || "").trim();
    if (!message) return;
    const signature = `${type}:${message.slice(0, 280)}`;
    if (signatures.includes(signature)) return;
    signatures.push(signature);
    if (signatures.length > 40) signatures.shift();
    queue.push({ type, message: message.slice(0, 4000), ts: Date.now() });
  };

  window.addEventListener("error", (event) => {
    pushIssue("window-error", event.message || formatValue(event.error) || "Unknown window error");
  });

  window.addEventListener("unhandledrejection", (event) => {
    pushIssue("unhandledrejection", formatValue(event.reason) || "Unhandled promise rejection");
  });

  const originalConsoleError = console.error.bind(console);
  console.error = (...args) => {
    try {
      pushIssue("console-error", args.map(formatValue).join(" "));
    } catch {}
    return originalConsoleError(...args);
  };

  if (typeof window.fetch === "function") {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      try {
        const response = await originalFetch(...args);
        const url = typeof args[0] === "string" ? args[0] : args[0]?.url || response.url || "";
        if (response.status >= 500 || (url.includes("/api/") && response.status >= 400)) {
          let body = "";
          try {
            body = await response.clone().text();
          } catch {}
          pushIssue("fetch-response", `${response.status} ${url} ${body.slice(0, 700)}`);
        }
        return response;
      } catch (error) {
        pushIssue("fetch-error", formatValue(error));
        throw error;
      }
    };
  }

  if (typeof XMLHttpRequest !== "undefined") {
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      this.__codexaMeta = { method, url: String(url || "") };
      return originalOpen.call(this, method, url, ...rest);
    };

    XMLHttpRequest.prototype.send = function(...args) {
      this.addEventListener("loadend", () => {
        try {
          const meta = this.__codexaMeta || {};
          const url = String(meta.url || this.responseURL || "");
          if (this.status >= 500 || (url.includes("/api/") && this.status >= 400)) {
            const body = typeof this.responseText === "string" ? this.responseText.slice(0, 700) : "";
            pushIssue("xhr-response", `${this.status} ${meta.method || "GET"} ${url} ${body}`);
          }
        } catch {}
      });
      return originalSend.apply(this, args);
    };
  }

  const flush = () => {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(
          {
            source: "codexa-preview-monitor",
            kind: "heartbeat",
            href: window.location.href,
            ts: Date.now(),
          },
          "*",
        );
      }

      if (!queue.length || !window.parent || window.parent === window) return;
      const issues = queue.splice(0, queue.length);
      window.parent.postMessage(
        {
          source: "codexa-preview-monitor",
          kind: "issues",
          href: window.location.href,
          ts: Date.now(),
          issues,
        },
        "*",
      );
    } catch {}
  };

  window.setInterval(flush, 1000);
  window.setTimeout(flush, 100);
})();
</script>"""

STEP_LABELS: dict = {
    "init":             "Initializing",
    "copying":          "Copying project files",
    "fixing":           "Auto-fixing code",
    "dependencies":     "Installing dependencies",
    "validate_python":  "Validating Python",
    "validate_ts":      "Checking TypeScript",
    "start_backend":    "Starting API server",
    "build_frontend":   "Building React app",
    "start_frontend":   "Starting preview server",
    "ready":            "Preview ready",
}
STEP_ORDER = list(STEP_LABELS.keys())


def _normalize_execution_mode(mode: str | None) -> str:
    return "docker" if (mode or "").strip().lower() == "docker" else "local"


def _log(msg: str) -> None:
    print(msg)
    with _STATE_LOCK:
        _LOG_LINES.append({"t": time.time(), "msg": msg})
        while len(_LOG_LINES) > 500:
            _LOG_LINES.pop(0)


def _debugger_log_reporter(message: str, payload: dict) -> None:
    scope = payload.get("scope")
    prefix = "[Preview][Debugger]"
    if scope == "frontend":
        prefix = "[Preview][Debugger][Frontend]"
    elif scope == "backend":
        prefix = "[Preview][Debugger][Backend]"
    _log(f"{prefix} {message}")


def _attach_process_log_streams(process: subprocess.Popen | None, label: str, line_handler=None) -> None:
    if process is None:
        return
    pid = getattr(process, "pid", None)
    if not isinstance(pid, int) or pid <= 0 or pid in _PROCESS_LOG_PIDS:
        return
    _PROCESS_LOG_PIDS.add(pid)

    def _pump(stream, stream_name: str) -> None:
        if stream is None:
            return
        try:
            while True:
                raw = stream.readline()
                if not raw:
                    break
                text = (
                    raw.decode("utf-8", errors="ignore").strip()
                    if isinstance(raw, bytes)
                    else str(raw).strip()
                )
                if text:
                    _log(f"[{label}][{stream_name}] {text}")
                    if line_handler:
                        try:
                            line_handler(text, stream_name)
                        except Exception:
                            pass
        except Exception:
            return

    threading.Thread(target=_pump, args=(process.stdout, "stdout"), daemon=True).start()
    threading.Thread(target=_pump, args=(process.stderr, "stderr"), daemon=True).start()


def _is_static_html_frontend(frontend_path: Path) -> bool:
    return (frontend_path / "index.html").exists() and not (frontend_path / "package.json").exists()


def _advance(step_id: str) -> None:
    with _STATE_LOCK:
        _PREVIEW_STATE["step"] = step_id
        if step_id not in _PREVIEW_STATE["steps_done"]:
            _PREVIEW_STATE["steps_done"].append(step_id)


def _set_error(msg: str) -> None:
    with _STATE_LOCK:
        _PREVIEW_STATE["phase"] = "error"
        _PREVIEW_STATE["error"] = msg
        started = _PREVIEW_STATE.get("started_at") or time.time()
        _PREVIEW_STATE["elapsed"] = round(time.time() - started, 1)


def _set_ready(frontend_url: str, backend_url: str) -> None:
    with _STATE_LOCK:
        _PREVIEW_STATE["phase"] = "ready"
        _PREVIEW_STATE["frontend_url"] = frontend_url
        _PREVIEW_STATE["backend_url"] = backend_url
        _PREVIEW_STATE["step"] = "ready"
        if "ready" not in _PREVIEW_STATE["steps_done"]:
            _PREVIEW_STATE["steps_done"].append("ready")
        started = _PREVIEW_STATE.get("started_at") or time.time()
        _PREVIEW_STATE["elapsed"] = round(time.time() - started, 1)


def _kill_port(port: int) -> None:
    """Force-kill any process listening on a TCP port."""
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.pid:
                try:
                    psutil.Process(conn.pid).kill()
                    time.sleep(0.1)
                except Exception:
                    pass
    except Exception:
        pass


def _port_alive(port: int) -> bool:
    """Return True if something is listening on the port right now."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False


def _is_project_running(project_id: str) -> bool:
    """True if this exact project's frontend is live (backend optional)."""
    return CURRENT_PROJECT_ID == project_id and _port_alive(FRONTEND_PORT)


def _hash_project_files(project_id: str) -> str:
    """Stable MD5 of all DB file paths+contents for a project."""
    import hashlib
    try:
        docs = list(files_col.find(
            {"project_id": ObjectId(project_id)},
            {"path": 1, "content": 1, "_id": 0},
        ))
        docs.sort(key=lambda d: d.get("path", ""))
        h = hashlib.md5()
        for d in docs:
            h.update((d.get("path") or "").encode())
            h.update((d.get("content") or "").encode())
        return h.hexdigest()
    except Exception:
        return ""


def _promote_project_env_templates(project_id: str) -> list[str]:
    """
    Promote root-level backend/frontend `.env*.example` files into real env
    files before preview starts, then persist those files back to Mongo so the
    code panel can show them immediately.
    """
    try:
        project_oid = ObjectId(project_id)
    except Exception:
        return []

    docs = list(
        files_col.find(
            {"project_id": project_oid},
            {"path": 1, "content": 1},
        )
    )
    if not docs:
        return []

    env_example_docs = [
        doc
        for doc in docs
        if isinstance(doc.get("path"), str)
        and re.fullmatch(r"(backend|frontend)/\.env[^/]*\.example", doc["path"])
    ]
    if not env_example_docs:
        return []

    existing_paths = {
        str(doc.get("path"))
        for doc in docs
        if isinstance(doc.get("path"), str)
    }

    sync_root = BASE_PREVIEW_DIR / project_id / "_env_prepare"
    shutil.rmtree(sync_root, ignore_errors=True)
    promoted_paths: list[str] = []
    debugger = DebuggerAgent(verbose=False)

    try:
        for scope in ("backend", "frontend"):
            scope_dir = sync_root / scope
            scope_dir.mkdir(parents=True, exist_ok=True)

            for doc in env_example_docs:
                source_path = doc["path"]
                if not source_path.startswith(f"{scope}/"):
                    continue

                file_name = source_path.split("/", 1)[1]
                promoted_path = f"{scope}/{file_name[: -len('.example')]}"
                if promoted_path in existing_paths:
                    continue

                (scope_dir / file_name).write_text(
                    str(doc.get("content") or ""),
                    encoding="utf-8",
                )

            created_names = debugger._promote_env_example_files(scope_dir)
            if not created_names:
                continue

            now = datetime.utcnow()
            for target_name in created_names:
                target_path = f"{scope}/{target_name}"
                target_file = scope_dir / target_name
                try:
                    target_content = target_file.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                except Exception:
                    continue

                files_col.update_one(
                    {"project_id": project_oid, "path": target_path},
                    {
                        "$set": {
                            "content": target_content,
                            "updated_at": now,
                        },
                        "$setOnInsert": {
                            "project_id": project_oid,
                            "path": target_path,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
                existing_paths.add(target_path)
                promoted_paths.append(target_path)
    finally:
        shutil.rmtree(sync_root, ignore_errors=True)

    return promoted_paths


def _persist_changed_preview_files(
    project_id: str,
    scope_root: Path,
    scope_prefix: str,
    changed_files: list[str] | None,
) -> list[str]:
    if not changed_files:
        return []

    try:
        project_oid = ObjectId(project_id)
    except Exception:
        return []

    persisted_paths: list[str] = []
    now = datetime.utcnow()
    for rel_path in changed_files:
        rel = str(rel_path or "").strip().replace("\\", "/")
        if not rel:
            continue
        full_path = scope_root / rel
        if not full_path.exists() or not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        db_path = f"{scope_prefix}/{rel}"
        files_col.update_one(
            {"project_id": project_oid, "path": db_path},
            {
                "$set": {
                    "content": content,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "project_id": project_oid,
                    "path": db_path,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        persisted_paths.append(db_path)
    return persisted_paths


def _inject_preview_runtime_probe(frontend_path: Path) -> bool:
    index_file = frontend_path / "index.html"
    if not index_file.exists():
        return False

    try:
        original = index_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False

    if _PREVIEW_RUNTIME_PROBE_MARKER in original:
        return False

    if "</body>" in original:
        updated = original.replace("</body>", f"{_PREVIEW_RUNTIME_PROBE_SNIPPET}\n</body>", 1)
    else:
        updated = original + "\n" + _PREVIEW_RUNTIME_PROBE_SNIPPET + "\n"

    if updated == original:
        return False

    try:
        index_file.write_text(updated, encoding="utf-8")
        return True
    except Exception:
        return False


def _runtime_issue_signature(project_id: str, issue_type: str, message: str) -> str:
    normalized = f"{project_id}|{issue_type}|{message.strip().lower()[:400]}"
    return normalized


def _runtime_issue_on_cooldown(project_id: str, issue_type: str, message: str, cooldown_seconds: float = 8.0) -> bool:
    signature = _runtime_issue_signature(project_id, issue_type, message)
    now = time.time()
    last_seen = _RUNTIME_REPORT_HISTORY.get(signature)
    _RUNTIME_REPORT_HISTORY[signature] = now
    if last_seen is None:
        return False
    return (now - last_seen) < cooldown_seconds


def _fix_esm_config(rel: str, content: str) -> str:
    """
    Convert CommonJS config files to ES module syntax when they will be loaded
    inside a package that has "type": "module" in package.json.

    Covers postcss.config.js, tailwind.config.js, and any other root-level .js
    config file that the LLM commonly generates with `module.exports`.
    """
    _ESM_CONFIG_TARGETS = {
        "postcss.config.js",
        "tailwind.config.js",
        "tailwind.config.cjs",   # sometimes generated with wrong ext
        "prettier.config.js",
        "babel.config.js",
    }
    filename = rel.split("/")[-1] if "/" in rel else rel
    if filename not in _ESM_CONFIG_TARGETS:
        return content

    # 1. Convert `const X = require('Y')` / `const { X } = require('Y')`
    #    → `import X from 'Y'` / `import { X } from 'Y'`
    content = re.sub(
        r"const\s+\{([^}]+)\}\s*=\s*require\(['\"]([^'\"]+)['\"]\)\s*;?",
        lambda m: f"import {{ {m.group(1).strip()} }} from '{m.group(2)}';",
        content,
    )
    content = re.sub(
        r"const\s+(\w+)\s*=\s*require\(['\"]([^'\"]+)['\"]\)\s*;?",
        lambda m: f"import {m.group(1)} from '{m.group(2)}';",
        content,
    )

    # 2. Convert `module.exports = ` → `export default `
    content = re.sub(r"\bmodule\.exports\s*=\s*", "export default ", content)

    return content


def _strip_preview_runtime_probe(content: str) -> str:
    if not content or _PREVIEW_RUNTIME_PROBE_MARKER not in content:
        return content
    return (
        content
        .replace(f"{_PREVIEW_RUNTIME_PROBE_SNIPPET}\n", "")
        .replace(f"\n{_PREVIEW_RUNTIME_PROBE_SNIPPET}", "")
        .replace(_PREVIEW_RUNTIME_PROBE_SNIPPET, "")
    )


def _write_if_changed(path: Path, content: str) -> bool:
    """Write only if content differs from what's on disk. Returns True if written."""
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == content:
                return False
        except Exception:
            pass
    path.write_text(content, encoding="utf-8")
    return True


def _build_hash_file(project_id: str) -> Path:
    return BASE_PREVIEW_DIR / project_id / ".build_hash"


def _load_build_hash(project_id: str) -> str:
    """Load the hash of the last successfully-built version from disk."""
    try:
        f = _build_hash_file(project_id)
        return f.read_text(encoding="utf-8").strip() if f.exists() else ""
    except Exception:
        return ""


def _save_build_hash(project_id: str, hash_val: str) -> None:
    """Persist the build hash so warm-restart can skip heavy steps next time."""
    try:
        _build_hash_file(project_id).write_text(hash_val, encoding="utf-8")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# STOP RUNNING PROJECT
# ──────────────────────────────────────────────────────────────────────────────
def stop_current_project():
    global CURRENT_FRONTEND_PROCESS, CURRENT_BACKEND_PROCESS, CURRENT_PROJECT_ID

    if CURRENT_PROJECT_ID:
        frontend_path = BASE_PREVIEW_DIR / CURRENT_PROJECT_ID / "frontend"
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

        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == BACKEND_PORT:
                try:
                    psutil.Process(conn.pid).kill()
                except Exception:
                    continue

    if CURRENT_FRONTEND_PROCESS:
        CURRENT_FRONTEND_PROCESS.terminate()
        CURRENT_FRONTEND_PROCESS = None

    if CURRENT_BACKEND_PROCESS:
        CURRENT_BACKEND_PROCESS.terminate()
        CURRENT_BACKEND_PROCESS = None

    CURRENT_PROJECT_ID = None


# ──────────────────────────────────────────────────────────────────────────────
# REBUILD FRONTEND FILES
# ──────────────────────────────────────────────────────────────────────────────
def rebuild_frontend(project_id: str) -> tuple[Path, int]:
    """Returns (frontend_path, number_of_files_actually_written_or_changed)."""
    files = list(files_col.find({"project_id": ObjectId(project_id)}))
    frontend_path = BASE_PREVIEW_DIR / project_id / "frontend"
    frontend_path.mkdir(parents=True, exist_ok=True)

    count = 0
    written = 0
    for file in files:
        if not file["path"].startswith("frontend/"):
            continue

        rel = file["path"].replace("frontend/", "")
        full = frontend_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)

        content = file["content"]

        # Fix missing Vite proxy configuration
        if rel == "vite.config.ts" and "proxy:" not in content:
            content = content.replace(
                "server: {\n    port: 5173,\n  },",
                "server: {\n    port: 5173,\n    proxy: {\n      '/api': {\n        target: 'http://localhost:7979',\n        changeOrigin: true,\n      },\n    },\n  },",
            )

        # Fix incorrect proxy target port
        if rel == "vite.config.ts" and "target: 'http://localhost:8000'" in content:
            content = content.replace("target: 'http://localhost:8000'", "target: 'http://localhost:7979'")

        # Fix hardcoded backend URLs in source files
        if rel != "vite.config.ts":
            content = content.replace("http://localhost:8000/api", "/api")
            content = content.replace("http://localhost:8000", "")
            content = content.replace("'http://localhost:7979/api'", "'/api'")
            content = content.replace('"http://localhost:7979/api"', '"/api"')
            content = content.replace("baseURL: 'http://localhost:8000'", "baseURL: '/api'")
            content = content.replace('baseURL: "http://localhost:8000"', 'baseURL: "/api"')
            content = content.replace("baseURL: 'http://localhost:7979'", "baseURL: '/api'")
            content = content.replace('baseURL: "http://localhost:7979"', 'baseURL: "/api"')

        # Ensure vite.config.ts proxy target is correct
        if rel == "vite.config.ts":
            content = content.replace("target: ''", "target: 'http://localhost:7979'")
            content = content.replace('target: ""', "target: 'http://localhost:7979'")
            content = content.replace("target: 'http://localhost:8000'", "target: 'http://localhost:7979'")
            content = content.replace('target: "http://localhost:8000"', "target: 'http://localhost:7979'")
            # Inject preview block so `vite preview` forwards /api and listens on 0.0.0.0
            if "preview:" not in content:
                content = content.replace(
                    "export default defineConfig({",
                    "export default defineConfig({\n  preview: { host: '0.0.0.0', port: 5959, strictPort: true, proxy: { '/api': { target: 'http://localhost:7979', changeOrigin: true } } },",
                )
            # Fix any hardcoded 127.0.0.1 host in preview/server blocks
            content = content.replace("host: '127.0.0.1'", "host: '0.0.0.0'")
            content = content.replace('host: "127.0.0.1"', 'host: "0.0.0.0"')

        # Fix SVG imports used as React components
        if rel.endswith((".ts", ".tsx")) and re.search(r'import \w+ from ["\'][^"\']+\.svg(?:\?react)?["\']', content):
            svg_vars = re.findall(r'import (\w+) from ["\'][^"\']+\.svg(?:\?react)?["\']', content)
            content = re.sub(r'import \w+ from ["\'][^"\']+\.svg(?:\?react)?["\'];?\n?', '', content)
            for var in svg_vars:
                content = re.sub(rf'<{var}(\s[^>]*)?\s*/>', f'<span className="brand-logo">{var}</span>', content)
                content = re.sub(rf'<{var}(\s[^>]*)?>.*?</{var}>', f'<span className="brand-logo">{var}</span>', content, flags=re.DOTALL)

        # Fix unsafe .split() calls
        if rel.endswith((".ts", ".tsx")) and ".split(" in content:
            content = re.sub(
                r'(?<![?!])\b((?:[a-zA-Z_$][a-zA-Z0-9_$]*\.)+[a-zA-Z_$][a-zA-Z0-9_$]*)\.split\(',
                r'(\1 ?? "").split(',
                content,
            )

        # Fix corrupted JSX where a `key` attr was injected inside a dotted component name.
        # Three known forms produced by the auto-key-injector:
        #  A) <motion key={INJECTED}.div key={REAL} ...>  →  <motion.div key={REAL} ...>
        #  B) <motion key={INJECTED}.div\n               →  <motion.div key={INJECTED}\n
        #  C) <TAG key={A} key={B} ...>                  →  <TAG key={B} ...>  (plain duplicate)
        if rel.endswith((".ts", ".tsx")) and (
            re.search(r'<\w+\s+key=\{[^}]+\}\.\w+', content)
            or re.search(r'key=\{[^}]+\}\s+key=\{', content)
        ):
            # A: has second key after the dotted subcomponent name → keep second key
            content = re.sub(
                r'<(\w+)\s+key=\{[^}]+\}\.(\w+)\s+key=\{([^}]+)\}',
                r'<\1.\2 key={\3}',
                content,
            )
            # B: no second key on the same line → promote injected key to subcomponent attr
            content = re.sub(
                r'<(\w+)\s+key=\{([^}]+)\}\.(\w+)',
                r'<\1.\3 key={\2}',
                content,
            )
            # C: plain duplicate key on any tag → keep the last one
            content = re.sub(
                r'(<\w+(?:\.\w+)?)\s+key=\{[^}]+\}(\s+key=\{[^}]+\})',
                r'\1\2',
                content,
            )

        # Ensure vite server/preview binds to 0.0.0.0 so browser can reach it on Windows
        # (Windows 11 resolves `localhost` to ::1/IPv6 but 127.0.0.1-only servers don't answer on ::1)
        if rel == "vite.config.ts":
            content = content.replace("host: '127.0.0.1'", "host: '0.0.0.0'")
            content = content.replace('host: "127.0.0.1"', 'host: "0.0.0.0"')
            # Inject host into server block if missing
            content = re.sub(r'(server:\s*\{)(?![^}]*host:)', r"\1 host: '0.0.0.0',", content)

        # Inject axios auth interceptor if missing
        if rel in ("src/services/api.ts", "src/services/apiService.ts", "src/api/index.ts") \
                and "axios.create" in content and "interceptors.request" not in content:
            interceptor = """
# Auto-injected: attach JWT token from localStorage to every request
const _AUTH_KEYS = ['auth-storage-v2', 'auth-storage', 'authStore'];
api.interceptors.request.use((config) => {
  for (const key of _AUTH_KEYS) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      const token = JSON.parse(raw)?.state?.token;
      if (token) { config.headers.Authorization = `Bearer ${token}`; break; }
    } catch {}
  }
  return config;
});
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      _AUTH_KEYS.forEach(k => localStorage.removeItem(k));
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);
"""
            if "export default" in content:
                content = content.replace("export default", interceptor + "\nexport default", 1)
            else:
                content += interceptor

        # Fix mockData import name mismatch: LLM sometimes generates getProductBySlug
        # in mockData.ts but getProductById in ProductDetailPage.tsx (or vice-versa).
        # Normalise everything to getProductBySlug which is what mockData always exports.
        if rel.endswith((".ts", ".tsx")) and "getProductById" in content:
            content = content.replace("getProductById", "getProductBySlug")

        # Strip markdown fences
        if content.strip().startswith("```"):
            content = _strip_md_fences(content)

        # Convert CommonJS config syntax → ES module syntax
        # (LLMs frequently generate `module.exports` inside packages with "type":"module")
        content = _fix_esm_config(rel, content)

        # Fix tsconfig.json paths alias
        if rel == "tsconfig.json":
            import json as _j
            try:
                ts = _j.loads(content)
                if "compilerOptions" in ts and "references" not in ts:
                    co = ts["compilerOptions"]
                    if "paths" not in co:
                        co["paths"] = {"@/*": ["./src/*"]}
                    if "baseUrl" not in co:
                        co["baseUrl"] = "."
                    content = _j.dumps(ts, indent=2)
                elif "references" not in ts:
                    ts = {"files": [], "references": [{"path": "./tsconfig.app.json"}, {"path": "./tsconfig.node.json"}]}
                    content = _j.dumps(ts, indent=2)
            except Exception:
                pass

        # Ensure @/ imports resolve via vite alias
        _main_tsx = full.parent / "src" / "main.tsx"
        _has_alias_import = _main_tsx.exists() and "@/" in _main_tsx.read_text(encoding="utf-8", errors="ignore")
        if rel == "vite.config.ts" and _has_alias_import:
            if "resolve:" not in content and "alias:" not in content:
                content = content.replace(
                    "plugins: [react()]",
                    "plugins: [react()],\n  resolve: { alias: { '@': path.resolve(__dirname, './src') } }",
                )
            if "import path from 'path'" not in content and "alias:" in content:
                content = "import path from 'path'\n" + content

        if rel == "index.html" and full.exists():
            try:
                existing_content = full.read_text(encoding="utf-8", errors="replace")
                if _strip_preview_runtime_probe(existing_content) == content:
                    count += 1
                    continue
            except Exception:
                pass

        if _write_if_changed(full, content):
            written += 1
        count += 1

    if count == 0:
        raise RuntimeError("No frontend files found")

    import json as _json

    _tsconfig_node_content = _json.dumps({
        "compilerOptions": {
            "composite": True, "skipLibCheck": True,
            "module": "ESNext", "moduleResolution": "bundler",
            "allowSyntheticDefaultImports": True, "strict": True,
        },
        "include": ["vite.config.ts"],
    }, indent=2)
    (frontend_path / "tsconfig.node.json").write_text(_tsconfig_node_content, encoding="utf-8")

    _tsconfig_app_content = _json.dumps({
        "compilerOptions": {
            "target": "ES2020", "useDefineForClassFields": True,
            "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "module": "ESNext", "skipLibCheck": True,
            "moduleResolution": "bundler", "allowImportingTsExtensions": True,
            "isolatedModules": True, "moduleDetection": "force", "noEmit": True,
            "jsx": "react-jsx", "strict": True,
            "noUnusedLocals": False, "noUnusedParameters": False,
            "noFallthroughCasesInSwitch": False,
            "paths": {"@/*": ["./src/*"]}, "baseUrl": ".",
        },
        "include": ["src"],
    }, indent=2)
    (frontend_path / "tsconfig.app.json").write_text(_tsconfig_app_content, encoding="utf-8")

    (frontend_path / "tsconfig.json").write_text(_json.dumps({
        "files": [],
        "references": [
            {"path": "./tsconfig.app.json"},
            {"path": "./tsconfig.node.json"},
        ],
    }, indent=2), encoding="utf-8")
    _log("[Preview] tsconfig files written")

    # Guarantee index.html exists at frontend root — vite dev/build both need it.
    # If the LLM omitted it, inject a safe default so the server doesn't 404.
    _index_html = frontend_path / "index.html"
    if not _index_html.exists():
        _index_html.write_text(
            '<!doctype html>\n<html lang="en">\n  <head>\n'
            '    <meta charset="UTF-8" />\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
            '    <title>App</title>\n'
            '  </head>\n  <body>\n'
            '    <div id="root"></div>\n'
            '    <script type="module" src="/src/main.tsx"></script>\n'
            '  </body>\n</html>\n',
            encoding="utf-8",
        )
        _log("[Preview] index.html was missing — injected default")
        written += 1

    if _inject_preview_runtime_probe(frontend_path):
        _log("[Preview] Injected runtime monitor into preview index.html")

    return frontend_path, written


# ──────────────────────────────────────────────────────────────────────────────
# REBUILD BACKEND FILES
# ──────────────────────────────────────────────────────────────────────────────
def rebuild_backend(project_id: str) -> tuple[Path, bool]:
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

        content = file["content"]

        # Fix HTTP status code typos
        content = content.replace("HTTP_24_NO_CONTENT", "HTTP_204_NO_CONTENT")
        content = content.replace("HTTP_20_OK", "HTTP_200_OK")
        content = content.replace("HTTP_20_CREATED", "HTTP_201_CREATED")
        content = content.replace("HTTP_40_NO_CONTENT", "HTTP_204_NO_CONTENT")
        content = content.replace("HTTP_404_NO", "HTTP_404_NOT_FOUND")

        # Fix Python syntax typos
        content = content.replace("as def ", "async def ")
        content = content.replace("ascontextmanager", "asynccontextmanager")

        # Rewrite deprecated @app.on_event("startup"/"shutdown") → lifespan pattern
        # so uvicorn doesn't print deprecation errors that fill stderr and confuse diagnosis.
        # Only patch if there's no lifespan already.
        if "main.py" in rel and "@app.on_event" in content and "lifespan" not in content:
            # Collect startup/shutdown bodies
            startup_body = ""
            shutdown_body = ""
            _on_startup = re.search(
                r'@app\.on_event\(["\']startup["\']\)\s*\nasync def \w+\([^)]*\):\s*\n((?:[ \t]+[^\n]*\n)*)',
                content)
            _on_shutdown = re.search(
                r'@app\.on_event\(["\']shutdown["\']\)\s*\nasync def \w+\([^)]*\):\s*\n((?:[ \t]+[^\n]*\n)*)',
                content)
            if _on_startup:
                startup_body = _on_startup.group(1).rstrip()
            if _on_shutdown:
                shutdown_body = _on_shutdown.group(1).rstrip()
            # Remove the old event handlers
            content = re.sub(
                r'@app\.on_event\(["\']startup["\']\)\s*\nasync def \w+\([^)]*\):\s*\n(?:[ \t]+[^\n]*\n)*',
                '', content)
            content = re.sub(
                r'@app\.on_event\(["\']shutdown["\']\)\s*\nasync def \w+\([^)]*\):\s*\n(?:[ \t]+[^\n]*\n)*',
                '', content)
            # Inject lifespan before `app = FastAPI(`
            lifespan_code = (
                "from contextlib import asynccontextmanager\n\n"
                "@asynccontextmanager\nasync def lifespan(_app):\n"
            )
            lifespan_code += f"    try:\n{startup_body}\n    except Exception as _e:\n        print(f'Startup warning: {{_e}}')\n" if startup_body else "    pass\n"
            lifespan_code += "    yield\n"
            if shutdown_body:
                lifespan_code += f"    try:\n{shutdown_body}\n    except Exception: pass\n"
            lifespan_code += "\n"
            content = re.sub(
                r'(app\s*=\s*FastAPI\()',
                lifespan_code + r'\1lifespan=lifespan, ',
                content, count=1)
            if "asynccontextmanager" not in content.split("@asynccontextmanager")[0]:
                pass  # already injected above
            _log(f"[Preview] Patched deprecated @app.on_event in {rel}")

        # Fix CORS — ensure 5959 is always allowed
        if "main.py" in rel and "CORSMiddleware" in content and "5959" not in content:
            content = content.replace(
                '"http://localhost:5173"',
                '"http://localhost:5959", "http://localhost:5173"',
            )
            content = content.replace(
                "'http://localhost:5173'",
                "'http://localhost:5959', 'http://localhost:5173'",
            )

        # Patch database.py: wrap connect_db in try/except so app starts without MongoDB
        if "database.py" in rel and "AsyncIOMotorClient" in content and "try:" not in content:
            content = re.sub(
                r'(async def connect_db\([^)]*\):)\s*\n((?:[ \t]+[^\n]*\n)+)',
                lambda m: (
                    m.group(1) + "\n"
                    "    try:\n"
                    + "\n".join("    " + l for l in m.group(2).splitlines()) + "\n"
                    "    except Exception as _e:\n"
                    "        print(f'[DB] MongoDB unavailable (frontend-only mode): {_e}')\n"
                ),
                content,
            )
            _log(f"[Preview] Wrapped connect_db in try/except in {rel}")

        # Fix circular import in security.py
        if "from app.services.user_service import" in content and "app/utils/security.py" in rel:
            content = re.sub(
                r'^from app\.services\.user_service import [^\n]+\n',
                '# Lazy import moved inside function to prevent circular dependency\n',
                content,
                flags=re.MULTILINE,
            )

        if "app/utils/security.py" in rel and "get_current_user" in content:
            content = content.replace(
                "# Lazy import moved inside function to prevent circular dependency\n", ""
            )
            if ("from app.services.user_service import get_user_by_id" not in content
                    and "user = await get_user_by_id(" in content):
                content = content.replace(
                    "    user = await get_user_by_id(",
                    "    from app.services.user_service import get_user_by_id\n    user = await get_user_by_id(",
                )

        # Fix passlib + bcrypt 4.x incompatibility
        if "from passlib.context import CryptContext" in content and "pwd_context" in content:
            content = content.replace("from passlib.context import CryptContext\n", "import bcrypt as _bcrypt_lib\n")
            content = re.sub(r'pwd_context\s*=\s*CryptContext\([^\n]+\)\n', '', content)
            content = content.replace(
                "def verify_password(plain_password: str, hashed_password: str) -> bool:\n    return pwd_context.verify(plain_password, hashed_password)",
                "def verify_password(plain_password: str, hashed_password: str) -> bool:\n    pw = plain_password.encode('utf-8')[:72]\n    return _bcrypt_lib.checkpw(pw, hashed_password.encode('utf-8'))",
            )
            content = re.sub(
                r'def get_password_hash\(password: str\) -> str:.*?(?=\ndef |\nasync def |\Z)',
                "def get_password_hash(password: str) -> str:\n    pw = password.encode('utf-8')[:72]\n    return _bcrypt_lib.hashpw(pw, _bcrypt_lib.gensalt()).decode('utf-8')\n",
                content,
                flags=re.DOTALL,
            )

        # Fix Pydantic v2 Annotated[ObjectId, ...] pattern — ObjectId cannot be
        # used as the base type in Annotated for Pydantic v2. Replace with str.
        if "Annotated" in content and "ObjectId" in content and "BaseModel" in content:
            # PyObjectId = Annotated[\n    ObjectId, ...] (multi-line)
            content = re.sub(
                r'(PyObjectId\s*=\s*Annotated\[\s*\n?\s*)ObjectId\b',
                r'\1str',
                content,
            )
            # PyObjectId = Annotated[ObjectId, ...] (single-line)
            content = re.sub(
                r'(=\s*Annotated\[)ObjectId\b',
                r'\1str',
                content,
            )

        # Fix deprecated Pydantic v1 PyObjectId validators
        if "__get_validators__" in content and "PyObjectId" in content:
            content = content.replace(
                "    @classmethod\n    def __get_validators__(cls):\n        yield cls.validate\n\n    @classmethod\n    def validate(cls, v, _):\n        if not ObjectId.is_valid(v):\n            raise ValueError(\"Invalid ObjectId\")\n        return ObjectId(v)\n\n    @classmethod\n    def __get_pydantic_json_schema__(cls, field_schema):\n        field_schema.update(type=\"string\")",
                "    @classmethod\n    def __get_pydantic_core_schema__(cls, source_type, handler):\n        from pydantic_core import core_schema\n        return core_schema.union_schema([\n            core_schema.str_schema(),\n            core_schema.is_instance_schema(ObjectId),\n        ], serialization=core_schema.to_string_schema())\n\n    @classmethod\n    def validate(cls, v):\n        if isinstance(v, ObjectId):\n            return v\n        if not ObjectId.is_valid(v):\n            raise ValueError(\"Invalid ObjectId\")\n        return ObjectId(v)",
            )

        # Fix PyObjectId in schemas.py
        if "PyObjectId" in content and rel == "app/schemas.py":
            content = content.replace("from app.models import PyObjectId", "")
            content = content.replace(": PyObjectId", ": str")
            content = content.replace("PyObjectId: str", "str")

        # Fix PyObjectId in models.py
        if "PyObjectId" in content and rel == "app/models.py":
            content = re.sub(
                r'class PyObjectId\(ObjectId\):.*?(?=\n# ---|\nclass )',
                '',
                content,
                flags=re.DOTALL,
            )
            content = content.replace(": PyObjectId", ": str")
            content = content.replace("PyObjectId = Field(", "str = Field(")
            content = content.replace("PyObjectId(", "str(")
            content = content.replace("default_factory=PyObjectId", "default_factory=lambda: str(ObjectId())")
            content = content.replace("arbitrary_types_allowed = True", "")

        # Fix raw ObjectId used as Pydantic v2 field type — Pydantic v2 can't
        # generate a schema for bson.ObjectId without arbitrary_types_allowed.
        # Replace all `: ObjectId` type annotations with `: str` and leave
        # ObjectId() *calls* (in defaults/validators) untouched.
        if "BaseModel" in content and "ObjectId" in content:
            # `: ObjectId` and `Optional[ObjectId]` in field annotations
            content = re.sub(r':\s*ObjectId\b(?!\s*\()', ': str', content)
            content = re.sub(r'\bOptional\[ObjectId\]', 'Optional[str]', content)
            content = re.sub(r'\bList\[ObjectId\]', 'List[str]', content)
            content = re.sub(r'\bUnion\[ObjectId,', 'Union[str,', content)
            content = re.sub(r',\s*ObjectId\]', ', str]', content)

        # Fix missing ObjectId import
        if "ObjectId" in content and "from bson import ObjectId" not in content:
            if "from datetime import datetime" in content:
                content = content.replace("from datetime import datetime", "from datetime import datetime\nfrom bson import ObjectId")
            elif "import datetime" in content:
                content = content.replace("import datetime", "import datetime\nfrom bson import ObjectId")
            else:
                content = "from bson import ObjectId\n" + content

        # Strip markdown fences
        if content.strip().startswith("```"):
            content = _strip_md_fences(content)

        _write_if_changed(full, content)
        count += 1

    if count == 0:
        stub_main = backend_path / "main.py"
        stub_main.write_text(
            "\n".join(
                [
                    "from fastapi import FastAPI",
                    "",
                    'app = FastAPI(title="CODEXA Preview Backend")',
                    "",
                    '@app.get("/health")',
                    "async def health():",
                    '    return {"ok": True, "mode": "frontend_only_preview"}',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        _log("[Preview] No backend files detected - generated preview-only backend stub")
        return backend_path, True

    # Create .env from .env.example if missing
    env_file = backend_path / ".env"
    env_example = backend_path / ".env.example"
    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")

    # Sanitize placeholder values so services don't crash on startup
    _sanitize_env_file(env_file)

    return backend_path, True


def _sanitize_env_file(env_file: Path) -> None:
    """Replace unset placeholder values in .env with safe local defaults."""
    if not env_file.exists():
        return

    PLACEHOLDER_RE = re.compile(r"^<.+>$|^your[-_]|^YOUR[-_]|^CHANGE[-_]ME|^REPLACE[-_]ME|^example|^EXAMPLE", re.IGNORECASE)
    CONTAINS_ANGLE = re.compile(r"<[^>]+>")

    lines = env_file.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = []
    changed = False

    for line in lines:
        stripped = line.rstrip("\n\r")
        if not stripped or stripped.lstrip().startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key, _, val = stripped.partition("=")
        key_upper = key.strip().upper()
        val = val.strip()

        if key_upper.startswith("VITE_"):
            changed = True
            continue

        new_val = None

        # MongoDB URI with angle-bracket placeholder
        if CONTAINS_ANGLE.search(val) and any(k in key_upper for k in ("MONGO", "DATABASE_URL")):
            new_val = "mongodb://localhost:27017/preview_db"

        # Generic mongodb+srv with placeholder host
        elif val.startswith("mongodb+srv://") and CONTAINS_ANGLE.search(val):
            new_val = "mongodb://localhost:27017/preview_db"

        # Any value that is entirely a placeholder token
        elif CONTAINS_ANGLE.match(val) or PLACEHOLDER_RE.match(val):
            # Give sensible defaults for common keys
            if any(k in key_upper for k in ("SECRET", "JWT_SECRET", "SECRET_KEY")):
                new_val = "preview_secret_key_do_not_use_in_production"
            elif any(k in key_upper for k in ("MONGO", "DATABASE_URL", "DB_URL")):
                new_val = "mongodb://localhost:27017/preview_db"
            elif "PORT" in key_upper:
                new_val = "8000"
            else:
                new_val = "preview_placeholder"

        if new_val is not None:
            new_lines.append(f"{key.strip()}={new_val}\n")
            changed = True
        else:
            new_lines.append(line)

    if changed:
        env_file.write_text("".join(new_lines), encoding="utf-8")
        _log("[Preview] .env placeholders sanitized for local preview")





# ──────────────────────────────────────────────────────────────────────────────
# VALIDATION + LLM AUTO-FIX LOOPS
# ──────────────────────────────────────────────────────────────────────────────
def _make_llm_caller():
    try:
        from core.factory.agent_factory import build_llm_client_for_agent
        from core.providers.base import ChatMessage
        client, opts = build_llm_client_for_agent("integrator")

        def call(prompt: str) -> str:
            msgs = [ChatMessage(role="user", content=prompt)]
            response = client.complete(msgs, opts)
            return response.text if hasattr(response, "text") else str(response)

        return call
    except Exception as e:
        _log(f"[ValidationLoop] Could not build LLM caller: {e}")
        return None


def _run_python_fix_loop(backend_path: Path, max_rounds: int = 3):
    llm_call = _make_llm_caller()
    if not llm_call:
        return
    for round_num in range(1, max_rounds + 1):
        py_errors = validate_python(backend_path)
        if not py_errors:
            _log(f"[ValidationLoop] Python OK (round {round_num})")
            return
        _log(f"[ValidationLoop] Python errors round {round_num}: {len(py_errors)} in {len({e.path for e in py_errors})} files")
        fixed = fix_errors(py_errors, backend_path, llm_call, max_rounds=1)
        if not fixed:
            return


def _run_ts_fix_loop(frontend_path: Path, max_rounds: int = 2):
    if not (frontend_path / "node_modules").exists():
        _log("[ValidationLoop] node_modules missing, skipping TS check")
        return
    llm_call = _make_llm_caller()
    if not llm_call:
        return
    for round_num in range(1, max_rounds + 1):
        ts_errors = validate_typescript(frontend_path)
        if not ts_errors:
            _log(f"[ValidationLoop] TypeScript OK (round {round_num})")
            return
        _log(f"[ValidationLoop] TS errors round {round_num}: {len(ts_errors)}")
        fixed = fix_errors(ts_errors, frontend_path, llm_call, max_rounds=1)
        if not fixed:
            return


# ──────────────────────────────────────────────────────────────────────────────
# DEPENDENCY INSTALL (with hash caching)
# ──────────────────────────────────────────────────────────────────────────────
def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    start = time.time()
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (OSError, ConnectionRefusedError):
            # Tight polling for first 3s to catch fast startups; back off after.
            time.sleep(0.1 if (time.time() - start) < 3.0 else 0.3)
    return False


def _wait_for_http(url: str, timeout: float = 15.0) -> bool:
    """Wait until url responds with a non-5xx status (server is actually serving)."""
    import urllib.request as _req
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with _req.urlopen(_req.Request(url, headers={"User-Agent": "codexa-check"}), timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False



def _pip_install(backend_path: Path) -> bool:
    import hashlib
    req_file = backend_path / "requirements.txt"
    if not req_file.exists():
        return True

    req_hash = hashlib.md5(req_file.read_bytes()).hexdigest()
    hash_file = backend_path / ".pip_hash"

    if hash_file.exists() and hash_file.read_text(encoding="utf-8").strip() == req_hash:
        _log("[Preview] pip: requirements unchanged, skipping install")
        return True

    _log("[Preview] pip install -r requirements.txt ...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q", "--disable-pip-version-check"],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode == 0:
            hash_file.write_text(req_hash, encoding="utf-8")
            _log("[Preview] pip install successful")
            return True
        _log(f"[Preview] pip install warnings: {r.stderr[:300]}")
        return False
    except Exception as e:
        _log(f"[Preview] pip install error (non-fatal): {e}")
        return False


def _npm_install(frontend_path: Path) -> bool:
    import hashlib
    pkg_file = frontend_path / "package.json"
    node_modules = frontend_path / "node_modules"

    if not pkg_file.exists():
        return True

    pkg_hash = hashlib.md5(pkg_file.read_bytes()).hexdigest()
    hash_file = frontend_path / ".npm_hash"

    # Skip install if package.json unchanged and node_modules present
    if node_modules.exists() and hash_file.exists():
        if hash_file.read_text(encoding="utf-8").strip() == pkg_hash:
            _log("[Preview] npm: packages unchanged, skipping install")
            return True

    for attempt in range(3):
        try:
            _log(f"[Preview] npm install attempt {attempt + 1}/3")
            r = subprocess.run(
                ["npm.cmd", "install", "--prefer-offline", "--no-audit", "--no-fund"],
                cwd=str(frontend_path), shell=True,
                capture_output=True, text=True, timeout=240,
            )
            if r.returncode == 0:
                hash_file.write_text(pkg_hash, encoding="utf-8")
                _log("[Preview] npm install successful")
                return True
            _log(f"[Preview] npm install failed (attempt {attempt + 1}): {r.stderr[-300:]}")
            subprocess.run(["rmdir", "/s", "/q", "node_modules"], cwd=str(frontend_path), shell=True, timeout=30)
            subprocess.run(["del", "/f", "/q", "package-lock.json"], cwd=str(frontend_path), shell=True, timeout=10)
        except subprocess.TimeoutExpired:
            _log(f"[Preview] npm install timed out (attempt {attempt + 1})")
            subprocess.run(["rmdir", "/s", "/q", "node_modules"], cwd=str(frontend_path), shell=True, timeout=30)
        except Exception as e:
            _log(f"[Preview] npm install error: {e}")

    _log("[Preview] npm install failed after 3 attempts")
    return False


# ──────────────────────────────────────────────────────────────────────────────
# POST-DEBUGGER SAFETY PATCHES
# ──────────────────────────────────────────────────────────────────────────────

_MOTION_KEY_PATTERNS = [
    # Pattern A: <motion key={x}.div key={y}> — has second (real) key attr
    (
        re.compile(r'<motion\s+key=\{[^}]+\}\.(\w+)((?:\s+[^>]*?)?\s+key=\{[^}]+\}[^>]*)>', re.DOTALL),
        lambda m: f'<motion.{m.group(1)}{m.group(2)}>',
    ),
    # Pattern B: <motion key={x}.div> — no second key attr (insert nothing)
    (
        re.compile(r'<motion\s+key=\{([^}]+)\}\.(\w+)(\s*(?:[^>]*?)?)>', re.DOTALL),
        lambda m: f'<motion.{m.group(2)} key={{{m.group(1)}}}{m.group(3)}>',
    ),
    # Pattern C: </motion key={x}.div> closing tags
    (
        re.compile(r'</motion\s+key=\{[^}]+\}\.(\w+)\s*>'),
        lambda m: f'</motion.{m.group(1)}>',
    ),
]


def _repair_jsx_after_debugger(
    frontend_path: Path,
    debugger: DebuggerAgent | None = None,
) -> int:
    """
    Run a last safety sweep after debugger edits so preview can recover from
    malformed motion JSX, duplicate key props, and missing optional Tailwind
    plugins before retrying Vite.
    """
    debugger = debugger or DebuggerAgent(verbose=False)
    src = frontend_path / "src"
    fixed = 0

    if src.is_dir():
        for jsx_file in [*src.rglob("*.tsx"), *src.rglob("*.jsx")]:
            try:
                original = jsx_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            text = original
            for pattern, repl in _MOTION_KEY_PATTERNS:
                text = pattern.sub(repl, text)
            text = debugger._repair_motion_jsx(text)
            text = debugger._dedupe_jsx_key_attributes(text)

            if text != original:
                try:
                    jsx_file.write_text(text, encoding="utf-8")
                    fixed += 1
                    _log(f"[Preview] JSX repair: fixed {jsx_file.name}")
                except Exception as e:
                    _log(f"[Preview] JSX repair write error {jsx_file.name}: {e}")

    for config_name in ("tailwind.config.js", "tailwind.config.cjs", "tailwind.config.mjs", "tailwind.config.ts"):
        config_file = frontend_path / config_name
        if not config_file.exists():
            continue
        try:
            original = config_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        text = debugger._repair_tailwind_plugin_requires(original)
        if text != original:
            try:
                config_file.write_text(text, encoding="utf-8")
                fixed += 1
                _log(f"[Preview] Tailwind config repair: fixed {config_file.name}")
            except Exception as e:
                _log(f"[Preview] Tailwind config repair write error {config_file.name}: {e}")

    return fixed


_CONFIG_PY_TEMPLATE = """\
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "app_db"
    SECRET_KEY: str = "changeme-in-production"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
"""

_DATABASE_PY_TEMPLATE = """\
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = None
db = None


async def connect_db():
    global client, db
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=3000)
        db = client[settings.DB_NAME]
        await client.server_info()
    except Exception as e:
        print(f"[DB] MongoDB unavailable: {e} — running without database")


async def close_db():
    global client
    if client:
        client.close()
"""

_MAIN_LIFESPAN_PATCH = '''\
from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.database import connect_db
        await connect_db()
    except Exception as e:
        print(f"[Startup] DB connect skipped: {e}")
    yield
    try:
        from app.database import close_db
        await close_db()
    except Exception:
        pass


app = FastAPI(lifespan=lifespan)
'''


def _ensure_backend_essentials(backend_path: Path) -> None:
    """
    Guarantee that the backend has the minimum files needed so uvicorn can
    start even when the orchestrator skipped generating them.
    """
    app_dir = backend_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    init_file = app_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")
        _log("[Preview] Created backend/app/__init__.py")

    config_file = app_dir / "config.py"
    if not config_file.exists():
        config_file.write_text(_CONFIG_PY_TEMPLATE, encoding="utf-8")
        _log("[Preview] Created backend/app/config.py (fallback)")
    else:
        try:
            config_src = config_file.read_text(encoding="utf-8", errors="replace")
            patched_src = config_src

            if "BaseSettings" in patched_src and "SettingsConfigDict" not in patched_src:
                patched_src = patched_src.replace(
                    "from pydantic_settings import BaseSettings",
                    "from pydantic_settings import BaseSettings, SettingsConfigDict",
                )

            if "BaseSettings" in patched_src and "extra" not in patched_src:
                patched_src = re.sub(
                    r'class Config:\s*\n(?:\s+env_file\s*=\s*["\']\.env["\']\s*\n)?(?:\s+case_sensitive\s*=\s*\w+\s*\n)?',
                    'model_config = SettingsConfigDict(env_file=".env", extra="ignore")\n',
                    patched_src,
                    count=1,
                )

            if patched_src != config_src:
                config_file.write_text(patched_src, encoding="utf-8")
                _log("[Preview] Patched backend/app/config.py to ignore extra env keys")
        except Exception as e:
            _log(f"[Preview] config.py patch error: {e}")

    database_file = app_dir / "database.py"
    if not database_file.exists():
        database_file.write_text(_DATABASE_PY_TEMPLATE, encoding="utf-8")
        _log("[Preview] Created backend/app/database.py (fallback)")

    # Patch main.py if it still uses deprecated @app.on_event
    main_py = backend_path / "main.py"
    if main_py.exists():
        try:
            src = main_py.read_text(encoding="utf-8", errors="replace")
            if "@app.on_event" in src and "lifespan" not in src:
                # Remove on_event startup/shutdown blocks and inject lifespan
                src = re.sub(
                    r'@app\.on_event\(["\']startup["\']\)\s*\nasync def [^\n]+\n(?:[ \t]+[^\n]*\n)*',
                    "",
                    src,
                )
                src = re.sub(
                    r'@app\.on_event\(["\']shutdown["\']\)\s*\nasync def [^\n]+\n(?:[ \t]+[^\n]*\n)*',
                    "",
                    src,
                )
                # Replace bare `app = FastAPI()` with lifespan version
                src = re.sub(
                    r'app\s*=\s*FastAPI\(\)',
                    "app = FastAPI(lifespan=lifespan)",
                    src,
                )
                if "lifespan" not in src:
                    src = _MAIN_LIFESPAN_PATCH + "\n" + src
                main_py.write_text(src, encoding="utf-8")
                _log("[Preview] Patched main.py: replaced @app.on_event with lifespan")
        except Exception as e:
            _log(f"[Preview] main.py patch error: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# CORE: RUN PROJECT
# ──────────────────────────────────────────────────────────────────────────────
def run_project(project_id: str) -> dict:
    global CURRENT_FRONTEND_PROCESS, CURRENT_BACKEND_PROCESS, CURRENT_PROJECT_ID

    frontend_url = f"http://localhost:{FRONTEND_PORT}"
    backend_url  = f"http://localhost:{BACKEND_PORT}"

    # ── ⚡ FAST PATH: servers still running + files unchanged ────────────────
    new_hash = _hash_project_files(project_id)
    if _is_project_running(project_id) and (
        _PROJECT_FILE_HASHES.get(project_id) == new_hash or _load_build_hash(project_id) == new_hash
    ):
        _log("[Preview] ⚡ Fast path — project unchanged and already running")
        with _STATE_LOCK:
            _PREVIEW_STATE.update({
                "phase": "ready", "step": "ready",
                "steps_done": list(STEP_LABELS.keys()),
                "error": None,
                "frontend_url": frontend_url,
                "backend_url": backend_url,
                "started_at": time.time(),
                "elapsed": 0.0,
                "project_id": project_id,
                "execution_mode": "local",
            })
        return {"ok": True, "frontend": frontend_url, "backend": backend_url}

    # ── 🔄 WARM RESTART: previously built, files unchanged → skip heavy steps ─
    # (disk hash survives backend restarts and project switches)
    is_warm_restart = _load_build_hash(project_id) == new_hash and new_hash != ""

    with _STATE_LOCK:
        _PREVIEW_STATE.update({
            "phase": "starting",
            "step": "init",
            "steps_done": ["init"],
            "error": None,
            "frontend_url": None,
            "backend_url": None,
            "started_at": time.time(),
            "elapsed": None,
            "project_id": project_id,
            "execution_mode": "local",
        })
        _LOG_LINES.clear()
    if is_warm_restart:
        _log(f"[Preview] 🔄 Warm restart for project {project_id} — skipping debugger/fix loops")
    else:
        _log(f"[Preview] Full build for project {project_id}")

    stop_current_project()
    _kill_port(FRONTEND_PORT)
    _kill_port(BACKEND_PORT)
    # Wait until ports are actually free — on Windows process termination is async
    # and `--strictPort` will immediately fail if the port is still occupied.
    _deadline = time.time() + 6.0
    while time.time() < _deadline:
        if not _port_alive(FRONTEND_PORT) and not _port_alive(BACKEND_PORT):
            break
        _kill_port(FRONTEND_PORT)
        _kill_port(BACKEND_PORT)
        time.sleep(0.3)
    _log(f"[Preview] Ports cleared: fe={not _port_alive(FRONTEND_PORT)} be={not _port_alive(BACKEND_PORT)}")

    # ── Step: Copy files — ALWAYS run so regex-fixes in rebuild_frontend apply ──
    # _write_if_changed makes this cheap: if nothing's different on disk, zero writes.
    # frontend_changed > 0 means the dist/ cache is stale and vite build must re-run.
    _advance("copying")
    try:
        with ThreadPoolExecutor(max_workers=2) as _rb_pool:
            _fe_fut = _rb_pool.submit(rebuild_frontend, project_id)
            _be_fut = _rb_pool.submit(rebuild_backend, project_id)
            frontend_path, frontend_changed = _fe_fut.result()
            backend_path, has_backend = _be_fut.result()
    except RuntimeError as e:
        _log(f"[Preview] Rebuild failed: {e}")
        _set_error(str(e))
        return {"ok": False, "error": str(e)}

    if is_warm_restart and frontend_changed == 0:
        _log("[Preview] 🔄 Warm restart — no source changes detected")
    elif is_warm_restart:
        _log(f"[Preview] 🔄 Warm restart — {frontend_changed} frontend file(s) re-fixed; dist cache invalidated")

    # Fast preview path: skip expensive whole-project debugger passes and rely on
    # targeted build/runtime recovery when a concrete issue is detected.
    fix_result: dict = {"total_files_fixed": 0}
    preview_debugger = DebuggerAgent(verbose=False, reporter=_debugger_log_reporter)
    if not is_warm_restart:
        _advance("fixing")
        _log("[Preview] Fast preview mode - skipping full debugger pre-pass")
        _jsx_n = _repair_jsx_after_debugger(frontend_path, preview_debugger)
        if _jsx_n:
            _log(f"[Preview] Frontend safety sweep cleaned {_jsx_n} file(s)")

        _advance("validate_python")
        if has_backend:
            _log("[Preview] Preflight Python fix loop skipped - runtime recovery remains active")
        else:
            _log("[Preview] Python validation skipped - no backend files found")
    else:
        _advance("fixing")
        _advance("validate_python")
        _log("[Preview] Skipped - dependencies and fixes already applied")

    # Always ensure backend essentials exist (config.py, database.py, __init__.py)
    # regardless of warm/cold path — the orchestrator may have skipped generating them.
    if has_backend:
        _ensure_backend_essentials(backend_path)
    else:
        _log("[Preview] Backend essentials skipped - project is frontend-only")

    # ── Step: pip + npm install IN PARALLEL (hash-cached — instant if unchanged)
    _advance("dependencies")
    if has_backend:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pip_f = pool.submit(_pip_install, backend_path)
            npm_f = pool.submit(_npm_install, frontend_path)
            pip_ok = pip_f.result()
            npm_ok = npm_f.result()
    else:
        pip_ok = True
        npm_ok = _npm_install(frontend_path)
    _log(f"[Preview] Installs done — pip:{pip_ok}  npm:{npm_ok}")

    # ── Step: TypeScript check runs IN BACKGROUND after servers are up ───────
    _advance("validate_ts")

    # ── Step: Start backend (non-blocking — waits in parallel with frontend) ──
    _advance("start_backend")
    uvicorn_module = "main:app"
    if not (backend_path / "main.py").exists():
        for candidate in ["app/main.py", "src/main.py"]:
            if (backend_path / candidate).exists():
                uvicorn_module = candidate.replace("/", ".").replace(".py", "") + ":app"
                break
        else:
            found = list(backend_path.rglob("main.py"))
            if found:
                rel = found[0].relative_to(backend_path)
                uvicorn_module = str(rel.with_suffix("")).replace("\\", ".").replace("/", ".") + ":app"

    backend_start_excerpt = ""
    backend_runtime_recovery = {"attempted": False, "buffer": []}

    def _spawn_backend(extra_args: list[str] | None = None, label: str = "Starting backend") -> None:
        nonlocal backend_start_excerpt
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            uvicorn_module,
            "--host",
            "0.0.0.0",
            "--port",
            str(BACKEND_PORT),
            "--log-level",
            "warning",
        ]
        if extra_args:
            cmd.extend(extra_args)
        _log(f"[Preview] {label} ({uvicorn_module}) on :{BACKEND_PORT}...")
        globals()["CURRENT_BACKEND_PROCESS"] = subprocess.Popen(
            cmd,
            cwd=str(backend_path),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            CURRENT_BACKEND_PROCESS.wait(timeout=3.0)
            _, _be_err = CURRENT_BACKEND_PROCESS.communicate()
            backend_start_excerpt = _be_err.decode("utf-8", errors="ignore")[-1200:]
            _log(f"[Preview] Backend exited immediately - stderr:\n{backend_start_excerpt}")
            globals()["CURRENT_BACKEND_PROCESS"] = None
        except subprocess.TimeoutExpired:
            _log("[Preview] Backend process alive after 3 s - waiting for port bind...")

    def _backend_runtime_line_handler(text: str, stream_name: str) -> None:
        if stream_name != "stderr":
            return
        buffer = backend_runtime_recovery["buffer"]
        buffer.append(text)
        if len(buffer) > 80:
            del buffer[:-80]
        if backend_runtime_recovery["attempted"]:
            return

        excerpt = "\n".join(buffer[-40:])
        lower_excerpt = excerpt.lower()
        is_mongo_validation_error = (
            "validationerror" in lower_excerpt
            and "field required" in lower_excerpt
            and "\nid\n" in lower_excerpt
            and "_id" in excerpt
        )
        if not is_mongo_validation_error:
            return

        backend_runtime_recovery["attempted"] = True

        def _recover_backend_runtime() -> None:
            global CURRENT_BACKEND_PROCESS
            try:
                retry_summary = preview_debugger.quick_fix_backend_runtime_error(
                    backend_path,
                    excerpt,
                )
                if not retry_summary.get("files_fixed"):
                    _log("[Preview] Backend runtime error detected, but debugger found no automatic fix")
                    return

                persisted = _persist_changed_preview_files(
                    project_id,
                    backend_path,
                    "backend",
                    retry_summary.get("changed_files"),
                )
                if persisted:
                    _log("[Preview] Persisted backend runtime recovery file(s): " + ", ".join(persisted))
                _log(
                    f"[Preview] Debugger detected backend runtime error and fixed {retry_summary['files_fixed']} file(s) - restarting backend"
                )
                if CURRENT_BACKEND_PROCESS and CURRENT_BACKEND_PROCESS.poll() is None:
                    CURRENT_BACKEND_PROCESS.terminate()
                    time.sleep(0.8)
                _kill_port(BACKEND_PORT)
                _spawn_backend(["--lifespan", "off"], label="Recovering backend")
                if _wait_backend_port(20.0):
                    if CURRENT_BACKEND_PROCESS and CURRENT_BACKEND_PROCESS.poll() is None:
                        _attach_process_log_streams(
                            CURRENT_BACKEND_PROCESS,
                            "Preview][Backend",
                            _backend_runtime_line_handler,
                        )
                    _log(f"[Preview] Backend runtime recovery successful on :{BACKEND_PORT}")
                else:
                    _log("[Preview] Backend runtime recovery failed to rebind the port")
            except Exception as runtime_fix_error:
                _log(f"[Preview] Backend runtime recovery failed (non-fatal): {runtime_fix_error}")

        threading.Thread(target=_recover_backend_runtime, daemon=True).start()

    try:
        _spawn_backend()
        if CURRENT_BACKEND_PROCESS is None:
            _log(f"[Preview] Retrying backend start ({uvicorn_module}) on :{BACKEND_PORT}…")
        # Use sys.executable -m uvicorn so we always find uvicorn in the current
        # Python environment regardless of PATH (shell=False + absolute interpreter).
        CURRENT_BACKEND_PROCESS = CURRENT_BACKEND_PROCESS or subprocess.Popen(
            [sys.executable, "-m", "uvicorn", uvicorn_module,
             "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
             "--log-level", "warning"],
            cwd=str(backend_path), shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if CURRENT_BACKEND_PROCESS is not None:
            _log("[Preview] Backend process check complete - waiting for port bind...")
    except Exception as e:
        _log(f"[Preview] Backend start error (non-fatal): {e}")
        CURRENT_BACKEND_PROCESS = None

    # ── Step: Build React app — runs while backend is starting up ─────────────
    _advance("build_frontend")
    vite_bin = frontend_path / "node_modules" / ".bin" / "vite.cmd"
    dist_index = frontend_path / "dist" / "index.html"
    is_static_frontend = _is_static_html_frontend(frontend_path)
    use_static = False

    if is_static_frontend:
        _log("[Preview] Static HTML frontend detected - skipping Vite build")
        use_static = True
    else:
        _log("[Preview] Fast preview mode - skipping production Vite build and starting dev server directly")

    # Launch frontend server without blocking on a production bundle build.
    _advance("start_frontend")
    vite_env = os.environ.copy()
    vite_env["FORCE_COLOR"] = "0"

    try:
        if is_static_frontend:
            _log(f"[Preview] Starting static HTML server on :{FRONTEND_PORT}...")
            CURRENT_FRONTEND_PROCESS = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "http.server",
                    str(FRONTEND_PORT),
                    "--bind",
                    "0.0.0.0",
                ],
                cwd=str(frontend_path),
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            _log(f"[Preview] Starting Vite dev server on :{FRONTEND_PORT}...")
            dev_cmd = ([str(vite_bin), "--port", str(FRONTEND_PORT), "--host", "0.0.0.0"]
                       if vite_bin.exists()
                       else ["npm.cmd", "run", "dev", "--",
                             "--port", str(FRONTEND_PORT), "--host", "0.0.0.0"] )
            CURRENT_FRONTEND_PROCESS = subprocess.Popen(
                dev_cmd, cwd=str(frontend_path), shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=vite_env,
            )
    except Exception as e:
        _set_error(f"Frontend start error: {e}")
        return {"ok": False, "error": f"Frontend start error: {e}"}

    # ── Wait for backend AND frontend simultaneously ───────────────────────────
    fe_timeout = 20.0 if is_static_frontend else 45.0

    def _wait_backend_port(timeout: float = 35.0) -> bool:
        """Wait for backend port, but bail early if the process has already died."""
        if CURRENT_BACKEND_PROCESS is None:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _port_alive(BACKEND_PORT):
                return True
            if CURRENT_BACKEND_PROCESS.poll() is not None:
                try:
                    _, _se = CURRENT_BACKEND_PROCESS.communicate(timeout=2)
                    _log(f"[Preview] Backend process died - stderr: {_se.decode('utf-8', errors='ignore')[-2000:]}")
                except Exception:
                    pass
                return False
            time.sleep(0.4)
        if CURRENT_BACKEND_PROCESS and CURRENT_BACKEND_PROCESS.poll() is None:
            _log("[Preview] Backend port wait timed out (process alive but not binding port)")
        return False

    def _wait_frontend_port(timeout: float = fe_timeout) -> bool:
        """Wait for frontend port and bail quickly if the process dies."""
        if CURRENT_FRONTEND_PROCESS is None:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _port_alive(FRONTEND_PORT):
                return True
            if CURRENT_FRONTEND_PROCESS.poll() is not None:
                try:
                    _, _se = CURRENT_FRONTEND_PROCESS.communicate(timeout=2)
                    _log(f"[Preview] Frontend process died - stderr: {_se.decode('utf-8', errors='ignore')[-2000:]}")
                except Exception:
                    pass
                return False
            time.sleep(0.2 if is_static_frontend else 0.35)
        if CURRENT_FRONTEND_PROCESS and CURRENT_FRONTEND_PROCESS.poll() is None:
            _log("[Preview] Frontend port wait timed out (process alive but not binding port)")
        return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        fe_f = pool.submit(_wait_frontend_port, fe_timeout)
        be_f = pool.submit(_wait_backend_port, 35.0)
        frontend_port_ok = fe_f.result()
        backend_port_ok = be_f.result()

    if not frontend_port_ok:
        err_text = "timed out"
        if CURRENT_FRONTEND_PROCESS and CURRENT_FRONTEND_PROCESS.poll() is not None:
            try:
                _, se = CURRENT_FRONTEND_PROCESS.communicate(timeout=2)
                err_text = se.decode("utf-8", errors="ignore")[-1200:]
            except Exception:
                pass
        _set_error(f"Frontend failed to start: {err_text}")
        return {"ok": False, "error": f"Frontend failed: {err_text}"}

    if CURRENT_FRONTEND_PROCESS and CURRENT_FRONTEND_PROCESS.poll() is None:
        _attach_process_log_streams(CURRENT_FRONTEND_PROCESS, "Preview][Frontend")
    _log(f"[Preview] Frontend ready on :{FRONTEND_PORT}")

    # Handle backend result
    backend_started = backend_port_ok
    if backend_port_ok:
        if CURRENT_BACKEND_PROCESS and CURRENT_BACKEND_PROCESS.poll() is None:
            _attach_process_log_streams(
                CURRENT_BACKEND_PROCESS,
                "Preview][Backend",
                _backend_runtime_line_handler,
            )
        _log(f"[Preview] Backend ready on :{BACKEND_PORT}")
    else:
        _log(f"[Preview] Backend not ready on :{BACKEND_PORT} (non-fatal, continuing frontend-only)")
        try:
            retry_summary = preview_debugger.quick_fix_backend_runtime_error(
                backend_path,
                backend_start_excerpt,
            )
            if retry_summary.get("files_fixed"):
                persisted = _persist_changed_preview_files(
                    project_id,
                    backend_path,
                    "backend",
                    retry_summary.get("changed_files"),
                )
                if persisted:
                    _log("[Preview] Persisted backend startup recovery file(s): " + ", ".join(persisted))
                _log(f"[Preview] Debugger applied {retry_summary['files_fixed']} fast backend fix(es) - retrying once with lifespan off")
                if CURRENT_BACKEND_PROCESS and CURRENT_BACKEND_PROCESS.poll() is None:
                    CURRENT_BACKEND_PROCESS.terminate()
                    time.sleep(0.8)
                _kill_port(BACKEND_PORT)
                _spawn_backend(["--lifespan", "off"], label="Retrying backend")
                backend_started = _wait_backend_port(20.0)
                if backend_started:
                    if CURRENT_BACKEND_PROCESS and CURRENT_BACKEND_PROCESS.poll() is None:
                        _attach_process_log_streams(
                            CURRENT_BACKEND_PROCESS,
                            "Preview][Backend",
                            _backend_runtime_line_handler,
                        )
                    _log(f"[Preview] Backend recovery successful on :{BACKEND_PORT}")
        except Exception as backend_retry_error:
            _log(f"[Preview] Backend recovery failed (non-fatal): {backend_retry_error}")

    # ── Done ─────────────────────────────────────────────────────────────────
    CURRENT_PROJECT_ID = project_id
    _PROJECT_FILE_HASHES[project_id] = new_hash        # in-memory fast-path cache
    _save_build_hash(project_id, new_hash)             # persist to disk for warm restarts
    _set_ready(frontend_url, backend_url if backend_started else None)
    _log(f"[Preview] ✓ Running — {frontend_url}" + ("" if backend_started else " (frontend-only, backend unavailable)"))

    # TS validation now runs in background (won't delay preview)
    def _bg_ts():
        try:
            _run_ts_fix_loop(frontend_path, max_rounds=1)
        except Exception as ex:
            _log(f"[ValidationLoop] TS background error: {ex}")
    threading.Thread(target=_bg_ts, daemon=True).start()

    return {
        "ok": True,
        "frontend": frontend_url,
        "backend": backend_url,
        "execution_mode": "local",
        "debugger_summary": {"files_fixed": fix_result.get("total_files_fixed", 0)},
    }


# ──────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

def _recent_log_text() -> str:
    with _STATE_LOCK:
        return "\n".join(entry["msg"] for entry in _LOG_LINES[-120:])


def _stop_docker_preview(project_id: str | None) -> None:
    if not project_id:
        return
    try:
        DebuggerAgent(verbose=False).stop_execution(project_id=project_id, mode="docker")
    except Exception as exc:
        _log(f"[Preview] Docker cleanup warning: {exc}")


def run_project_for_mode(project_id: str, execution_mode: str = "local") -> dict:
    global CURRENT_PROJECT_ID

    selected_mode = _normalize_execution_mode(execution_mode)
    if selected_mode == "local":
        _stop_docker_preview(None)
        result = run_project(project_id)
        with _STATE_LOCK:
            _PREVIEW_STATE["execution_mode"] = "local"
        result["execution_mode"] = "local"
        return result

    with _STATE_LOCK:
        active_docker_project = (
            _PREVIEW_STATE.get("project_id")
            if _PREVIEW_STATE.get("execution_mode") == "docker"
            else None
        )
        _PREVIEW_STATE.update({
            "phase": "starting",
            "step": "init",
            "steps_done": ["init"],
            "error": None,
            "frontend_url": None,
            "backend_url": None,
            "started_at": time.time(),
            "elapsed": None,
            "project_id": project_id,
            "execution_mode": selected_mode,
        })
        _LOG_LINES.clear()

    _log(f"[Preview] Docker execution selected for project {project_id}")
    stop_current_project()
    _stop_docker_preview(active_docker_project)
    _kill_port(FRONTEND_PORT)
    _kill_port(BACKEND_PORT)

    preview_debugger = DebuggerAgent(verbose=False, reporter=_debugger_log_reporter)
    try:
        result = preview_debugger.execute_preview(
            project_id,
            mode=selected_mode,
            step_callback=_advance,
        )
        docker_logs = ""
        if not result.get("logs_streamed"):
            docker_logs = result.get("logs") or preview_debugger.collect_execution_logs(
                project_id,
                mode=selected_mode,
                timeout=6,
            )
    except Exception as exc:
        error_text = str(exc)
        _log(f"[Preview] Docker execution failed: {error_text}")
        try:
            docker_logs = preview_debugger.collect_execution_logs(
                project_id,
                mode=selected_mode,
                timeout=6,
            )
        except Exception:
            docker_logs = ""
        if docker_logs:
            for line in docker_logs.splitlines()[-80:]:
                _log(f"[Docker] {line}")
        _set_error(error_text)
        with _STATE_LOCK:
            _PREVIEW_STATE["execution_mode"] = selected_mode
        return {"ok": False, "error": error_text, "execution_mode": selected_mode}

    if docker_logs:
        for line in docker_logs.splitlines()[-80:]:
            _log(f"[Docker] {line}")

    frontend_url = result.get("frontend") or f"http://localhost:{FRONTEND_PORT}"
    backend_url = result.get("backend")
    CURRENT_PROJECT_ID = project_id
    _set_ready(frontend_url, backend_url)
    with _STATE_LOCK:
        _PREVIEW_STATE["execution_mode"] = selected_mode
    _log(
        f"[Preview] Docker preview ready - {frontend_url}"
        + ("" if backend_url else " (frontend-only, backend unavailable)")
    )

    return {
        "ok": True,
        "frontend": frontend_url,
        "backend": backend_url,
        "execution_mode": selected_mode,
    }


@router.post("/preview/start/{project_id}")
def preview_start(project_id: str, payload: PreviewStartPayload | None = Body(default=None)):
    """Start preview build in a background thread. Returns immediately."""
    execution_mode = _normalize_execution_mode(payload.mode if payload else None)
    _log(f"[Preview] Start request received for project {project_id} mode={execution_mode}")
    promoted_env_paths = _promote_project_env_templates(project_id)
    if promoted_env_paths:
        _log(
            "[Preview] Promoted env template(s) before preview: "
            + ", ".join(promoted_env_paths)
        )
    thread = threading.Thread(
        target=run_project_for_mode,
        args=(project_id, execution_mode),
        daemon=True,
    )
    thread.start()
    return {
        "ok": True,
        "status": "starting",
        "project_id": project_id,
        "execution_mode": execution_mode,
        "promoted_env_paths": promoted_env_paths,
    }


@router.post("/preview/full/{project_id}")
def preview_full(project_id: str, payload: PreviewStartPayload | None = Body(default=None)):
    """Blocking preview start — waits until ready. Kept for backwards compat."""
    execution_mode = _normalize_execution_mode(payload.mode if payload else None)
    _log(f"[Preview] Full start request received for project {project_id} mode={execution_mode}")
    promoted_env_paths = _promote_project_env_templates(project_id)
    if promoted_env_paths:
        _log(
            "[Preview] Promoted env template(s) before blocking preview: "
            + ", ".join(promoted_env_paths)
        )
    result = run_project_for_mode(project_id, execution_mode)
    return {"project_id": project_id, "promoted_env_paths": promoted_env_paths, **result}


@router.post("/preview/runtime-report/{project_id}")
def preview_runtime_report(project_id: str, payload: dict | None = Body(default=None)):
    execution_mode = _normalize_execution_mode((payload or {}).get("mode"))
    issues = (payload or {}).get("issues") or []
    if not isinstance(issues, list) or not issues:
        return {"ok": True, "accepted": False, "files_fixed": 0}

    with _STATE_LOCK:
        current_phase = _PREVIEW_STATE.get("phase")
        current_project_id = _PREVIEW_STATE.get("project_id")

    if current_phase == "starting":
        return {"ok": True, "accepted": False, "files_fixed": 0, "reason": "preview_starting"}

    if current_project_id and current_project_id != project_id:
        return {"ok": True, "accepted": False, "files_fixed": 0, "reason": "inactive_project"}

    frontend_runtime_lines: list[str] = []
    backend_runtime_lines: list[str] = []
    accepted_count = 0

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("type") or "runtime")
        message = str(issue.get("message") or "").strip()
        if not message:
            continue
        if _runtime_issue_on_cooldown(project_id, issue_type, message):
            continue

        accepted_count += 1
        runtime_line = f"{issue_type}: {message}"
        lower_line = runtime_line.lower()

        if (
            issue_type in {"fetch-response", "fetch-error", "xhr-response"}
            or "/api/" in lower_line
            or "database connection is not available" in lower_line
            or "database unavailable" in lower_line
            or "service unavailable" in lower_line
            or "status=503" in lower_line
        ):
            backend_runtime_lines.append(runtime_line)

        if (
            issue_type in {"console-error", "window-error", "unhandledrejection"}
            or "react is not defined" in lower_line
            or "does not provide an export named" in lower_line
            or "uncaught" in lower_line
            or "syntaxerror" in lower_line
            or "typeerror" in lower_line
            or "referenceerror" in lower_line
        ):
            frontend_runtime_lines.append(runtime_line)

    if accepted_count == 0:
        return {"ok": True, "accepted": False, "files_fixed": 0, "reason": "cooldown"}

    _log(
        f"[Preview] Runtime report received for {project_id}: "
        + " | ".join((frontend_runtime_lines + backend_runtime_lines)[:2])[:600]
    )

    preview_debugger = DebuggerAgent(verbose=False, reporter=_debugger_log_reporter)
    frontend_path = BASE_PREVIEW_DIR / project_id / "frontend"
    backend_path = BASE_PREVIEW_DIR / project_id / "backend"

    total_files_fixed = 0
    persisted_paths: list[str] = []
    restart_required = False

    if frontend_runtime_lines and frontend_path.exists():
        frontend_summary = preview_debugger.quick_fix_frontend_runtime_error(
            frontend_path,
            "\n".join(frontend_runtime_lines),
        )
        if frontend_summary.get("files_fixed"):
            total_files_fixed += int(frontend_summary.get("files_fixed", 0))
            restart_required = True
            persisted = _persist_changed_preview_files(
                project_id,
                frontend_path,
                "frontend",
                frontend_summary.get("changed_files") or [],
            )
            persisted_paths.extend(persisted)
            if persisted:
                _log("[Preview] Persisted frontend runtime fix(es): " + ", ".join(persisted))

    if backend_runtime_lines and backend_path.exists():
        backend_summary = preview_debugger.quick_fix_backend_request_error(
            backend_path,
            "\n".join(backend_runtime_lines),
        )
        if backend_summary.get("files_fixed"):
            total_files_fixed += int(backend_summary.get("files_fixed", 0))
            restart_required = True
            persisted = _persist_changed_preview_files(
                project_id,
                backend_path,
                "backend",
                backend_summary.get("changed_files") or [],
            )
            persisted_paths.extend(persisted)
            if persisted:
                _log("[Preview] Persisted backend runtime fix(es): " + ", ".join(persisted))

    if restart_required:
        _log(
            f"[Preview] Debugger repaired {total_files_fixed} runtime issue file(s) - restarting preview automatically"
        )
        threading.Thread(
            target=run_project_for_mode,
            args=(project_id, execution_mode),
            daemon=True,
        ).start()
    else:
        _log("[Preview] Runtime issue observed, but debugger found no automatic repair")

    return {
        "ok": True,
        "accepted": True,
        "files_fixed": total_files_fixed,
        "persisted_paths": persisted_paths,
        "restarting": restart_required,
    }


@router.get("/preview/events")
async def preview_events():
    """SSE stream delivering real-time build status and logs."""
    import asyncio

    async def generate():
        prev_payload = None
        while True:
            with _STATE_LOCK:
                state = {**_PREVIEW_STATE, "steps_done": list(_PREVIEW_STATE["steps_done"])}
                logs = [entry["msg"] for entry in _LOG_LINES[-50:]]

            data = {
                "phase": state["phase"],
                "step": state["step"],
                "steps_done": state["steps_done"],
                "step_labels": STEP_LABELS,
                "step_order": STEP_ORDER,
                "error": state["error"],
                "frontend_url": state["frontend_url"],
                "backend_url": state["backend_url"],
                "elapsed": state["elapsed"],
                "started_at": state["started_at"],
                "project_id": state["project_id"],
                "execution_mode": state.get("execution_mode", "local"),
                "logs": logs,
            }
            payload = json.dumps(data)
            if payload != prev_payload:
                yield f"data: {payload}\n\n"
                prev_payload = payload

            await asyncio.sleep(0.25)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/preview/logs")
def preview_logs():
    """Return recent build log lines."""
    with _STATE_LOCK:
        return {"logs": [entry["msg"] for entry in _LOG_LINES[-100:]]}

@router.post("/preview/stop/{project_id}")
def stop_preview(project_id: str):
    _log(f"[Preview] Stop request received for project {project_id}")
    active_mode = _normalize_execution_mode(_PREVIEW_STATE.get("execution_mode"))
    active_project_id = _PREVIEW_STATE.get("project_id") or project_id
    stop_current_project()
    _stop_docker_preview(active_project_id if active_mode == "docker" else None)
    with _STATE_LOCK:
        _PREVIEW_STATE.update({"phase": "idle", "step": None, "steps_done": [], "error": None,
                                "frontend_url": None, "backend_url": None, "project_id": None,
                                "execution_mode": "local"})
    return {"ok": True, "status": "stopped"}


@router.get("/preview/status")
def preview_status():
    with _STATE_LOCK:
        state = dict(_PREVIEW_STATE)
    return {
        **state,
        "step_labels": STEP_LABELS,
        "step_order": STEP_ORDER,
        "execution_mode": state.get("execution_mode", "local"),
        # Legacy fields kept for backwards compat
        "status": state["phase"],
        "frontend_port": FRONTEND_PORT,
        "backend_port": BACKEND_PORT,
    }
