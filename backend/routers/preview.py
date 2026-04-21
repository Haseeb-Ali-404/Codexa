import json
import os
import re
import socket
import subprocess
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from bson import ObjectId
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
}
_LOG_LINES: list = []
_STATE_LOCK = threading.Lock()
_PROJECT_FILE_HASHES: dict = {}   # project_id → MD5 of last-built file set

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


def _log(msg: str) -> None:
    print(msg)
    with _STATE_LOCK:
        _LOG_LINES.append({"t": time.time(), "msg": msg})
        while len(_LOG_LINES) > 500:
            _LOG_LINES.pop(0)


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
            # Inject preview proxy so `vite preview` forwards /api to the backend
            if "preview:" not in content:
                content = content.replace(
                    "export default defineConfig({",
                    "export default defineConfig({\n  preview: { host: '127.0.0.1', proxy: { '/api': { target: 'http://localhost:7979', changeOrigin: true } } },",
                )

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

    return frontend_path, written


# ──────────────────────────────────────────────────────────────────────────────
# REBUILD BACKEND FILES
# ──────────────────────────────────────────────────────────────────────────────
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
        raise RuntimeError("No backend files found")

    # Create .env from .env.example if missing
    env_file = backend_path / ".env"
    env_example = backend_path / ".env.example"
    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")

    # Sanitize placeholder values so services don't crash on startup
    _sanitize_env_file(env_file)

    return backend_path


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
                ["npm.cmd", "install", "--prefer-offline"],
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
        })
        _LOG_LINES.clear()

    if is_warm_restart:
        _log(f"[Preview] 🔄 Warm restart for project {project_id} — skipping debugger/fix loops")
    else:
        _log(f"[Preview] Full build for project {project_id}")

    stop_current_project()
    _kill_port(FRONTEND_PORT)
    _kill_port(BACKEND_PORT)

    # ── Step: Copy files — ALWAYS run so regex-fixes in rebuild_frontend apply ──
    # _write_if_changed makes this cheap: if nothing's different on disk, zero writes.
    # frontend_changed > 0 means the dist/ cache is stale and vite build must re-run.
    _advance("copying")
    try:
        with ThreadPoolExecutor(max_workers=2) as _rb_pool:
            _fe_fut = _rb_pool.submit(rebuild_frontend, project_id)
            _be_fut = _rb_pool.submit(rebuild_backend, project_id)
            frontend_path, frontend_changed = _fe_fut.result()
            backend_path = _be_fut.result()
    except RuntimeError as e:
        _log(f"[Preview] Rebuild failed: {e}")
        _set_error(str(e))
        return {"ok": False, "error": str(e)}

    if is_warm_restart and frontend_changed == 0:
        _log("[Preview] 🔄 Warm restart — no source changes detected")
    elif is_warm_restart:
        _log(f"[Preview] 🔄 Warm restart — {frontend_changed} frontend file(s) re-fixed; dist cache invalidated")

    project_path = BASE_PREVIEW_DIR / project_id

    # ── Step: Auto-fix + validation (skipped on warm restart) ───────────────
    fix_result: dict = {"total_files_fixed": 0}
    if not is_warm_restart:
        _advance("fixing")
        debugger = DebuggerAgent(verbose=False)
        try:
            fix_result = debugger.fix_entire_project(project_path)
            _log(f"[Preview] Debugger: {fix_result['total_files_fixed']} files fixed")
        except Exception as e:
            _log(f"[Preview] Debugger error (non-fatal): {e}")

        _advance("validate_python")
        try:
            _run_python_fix_loop(backend_path, max_rounds=1)
        except Exception as e:
            _log(f"[Preview] Python fix loop error (non-fatal): {e}")
    else:
        _advance("fixing")
        _advance("validate_python")
        _log("[Preview] Skipped — dependencies and fixes already applied")

    # ── Step: pip + npm install IN PARALLEL (hash-cached — instant if unchanged)
    _advance("dependencies")
    with ThreadPoolExecutor(max_workers=2) as pool:
        pip_f = pool.submit(_pip_install, backend_path)
        npm_f = pool.submit(_npm_install, frontend_path)
        pip_ok = pip_f.result()
        npm_ok = npm_f.result()
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

    try:
        _log(f"[Preview] Starting backend ({uvicorn_module}) on :{BACKEND_PORT}…")
        CURRENT_BACKEND_PROCESS = subprocess.Popen(
            ["uvicorn", uvicorn_module, "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
            cwd=str(backend_path), shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except Exception as e:
        _log(f"[Preview] Backend start error (non-fatal): {e}")

    # ── Step: Build React app — runs while backend is starting up ─────────────
    _advance("build_frontend")
    vite_bin = frontend_path / "node_modules" / ".bin" / "vite.cmd"
    dist_index = frontend_path / "dist" / "index.html"
    use_static = False

    if is_warm_restart and dist_index.exists() and frontend_changed == 0:
        _log("[Preview] 🔄 Warm restart — dist already built, skipping vite build")
        use_static = True
    else:
        _log("[Preview] Running vite build (production bundle)…")
        try:
            build_cmd_list = [str(vite_bin), "build"] if vite_bin.exists() else ["npx.cmd", "vite", "build"]
            br = subprocess.run(
                build_cmd_list, cwd=str(frontend_path), shell=True,
                capture_output=True, text=True, timeout=120,
                encoding="utf-8", errors="replace",
            )
            # Always persist full output to a debug file for diagnosis
            try:
                (frontend_path / ".vite-build.log").write_text(
                    f"=== STDOUT ===\n{br.stdout or ''}\n=== STDERR ===\n{br.stderr or ''}",
                    encoding="utf-8",
                )
            except Exception:
                pass
            if br.returncode == 0 and dist_index.exists():
                _log("[Preview] vite build successful — static files ready")
                use_static = True
            else:
                # Strip ANSI color codes (they mangle the log readability)
                ansi_re = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
                clean_err = ansi_re.sub("", (br.stderr or ""))
                clean_out = ansi_re.sub("", (br.stdout or ""))
                # Combined output — stderr first (usually the real error), then stdout tail
                combined = (clean_err + "\n" + clean_out).strip()
                _log(f"[Preview] vite build failed rc={br.returncode} (falling back to dev server):\n{combined[-1800:]}")
                _log(f"[Preview] Full build log saved to: {frontend_path / '.vite-build.log'}")
        except subprocess.TimeoutExpired:
            _log("[Preview] vite build timed out — falling back to dev server")
        except Exception as e:
            _log(f"[Preview] vite build error — falling back to dev server: {e}")

    # ── Step: Launch frontend server (also non-blocking) ─────────────────────
    _advance("start_frontend")
    vite_env = os.environ.copy()
    vite_env["FORCE_COLOR"] = "0"

    try:
        if use_static:
            _log(f"[Preview] Starting vite preview (static) on :{FRONTEND_PORT}…")
            preview_cmd = ([str(vite_bin), "preview"] if vite_bin.exists()
                           else ["npx.cmd", "vite", "preview"])
            preview_cmd += ["--port", str(FRONTEND_PORT), "--host", "127.0.0.1", "--strictPort"]
            CURRENT_FRONTEND_PROCESS = subprocess.Popen(
                preview_cmd, cwd=str(frontend_path), shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=vite_env,
            )
        else:
            _log(f"[Preview] Starting Vite dev server on :{FRONTEND_PORT}…")
            dev_cmd = ([str(vite_bin), "--port", str(FRONTEND_PORT), "--host", "127.0.0.1", "--strictPort"]
                       if vite_bin.exists()
                       else ["npm.cmd", "run", "dev", "--",
                             "--port", str(FRONTEND_PORT), "--host", "127.0.0.1", "--strictPort"])
            CURRENT_FRONTEND_PROCESS = subprocess.Popen(
                dev_cmd, cwd=str(frontend_path), shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=vite_env,
            )
    except Exception as e:
        _set_error(f"Frontend start error: {e}")
        return {"ok": False, "error": f"Frontend start error: {e}"}

    # ── Wait for backend AND frontend simultaneously ───────────────────────────
    fe_timeout = 30.0 if use_static else 90.0
    with ThreadPoolExecutor(max_workers=2) as pool:
        fe_f = pool.submit(_wait_for_port, FRONTEND_PORT, "127.0.0.1", fe_timeout)
        be_f = pool.submit(_wait_for_port, BACKEND_PORT, "127.0.0.1", 35.0)
        frontend_port_ok = fe_f.result()
        backend_port_ok  = be_f.result()

    # Handle frontend result
    if not frontend_port_ok:
        if use_static:
            # vite preview failed — kill it and try dev server
            _log("[Preview] vite preview failed to start — falling back to dev server")
            if CURRENT_FRONTEND_PROCESS and CURRENT_FRONTEND_PROCESS.poll() is None:
                CURRENT_FRONTEND_PROCESS.terminate()
            CURRENT_FRONTEND_PROCESS = None
            _kill_port(FRONTEND_PORT)
            try:
                dev_cmd = ([str(vite_bin), "--port", str(FRONTEND_PORT), "--host", "127.0.0.1", "--strictPort"]
                           if vite_bin.exists()
                           else ["npm.cmd", "run", "dev", "--",
                                 "--port", str(FRONTEND_PORT), "--host", "127.0.0.1", "--strictPort"])
                CURRENT_FRONTEND_PROCESS = subprocess.Popen(
                    dev_cmd, cwd=str(frontend_path), shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=vite_env,
                )
                frontend_port_ok = _wait_for_port(FRONTEND_PORT, timeout=90)
            except Exception as e:
                _set_error(f"Frontend start error: {e}")
                return {"ok": False, "error": f"Frontend start error: {e}"}

        if not frontend_port_ok:
            err_text = "timed out"
            if CURRENT_FRONTEND_PROCESS and CURRENT_FRONTEND_PROCESS.poll() is not None:
                _, se = CURRENT_FRONTEND_PROCESS.communicate()
                err_text = se.decode("utf-8", errors="ignore")[-400:]
            _set_error(f"Frontend failed to start: {err_text}")
            return {"ok": False, "error": f"Frontend failed: {err_text}"}

    _wait_for_http(f"http://127.0.0.1:{FRONTEND_PORT}", timeout=10)
    _log(f"[Preview] Frontend ready on :{FRONTEND_PORT}")

    # Handle backend result
    backend_started = backend_port_ok
    if backend_port_ok:
        _log(f"[Preview] Backend ready on :{BACKEND_PORT}")
    else:
        _log(f"[Preview] Backend not ready on :{BACKEND_PORT} (non-fatal, continuing frontend-only)")

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
        "debugger_summary": {"files_fixed": fix_result.get("total_files_fixed", 0)},
    }


# ──────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/preview/start/{project_id}")
def preview_start(project_id: str):
    """Start preview build in a background thread. Returns immediately."""
    thread = threading.Thread(target=run_project, args=(project_id,), daemon=True)
    thread.start()
    return {"ok": True, "status": "starting", "project_id": project_id}


@router.post("/preview/full/{project_id}")
def preview_full(project_id: str):
    """Blocking preview start — waits until ready. Kept for backwards compat."""
    result = run_project(project_id)
    return {"project_id": project_id, **result}


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
    stop_current_project()
    with _STATE_LOCK:
        _PREVIEW_STATE.update({"phase": "idle", "step": None, "steps_done": [], "error": None,
                                "frontend_url": None, "backend_url": None, "project_id": None})
    return {"ok": True, "status": "stopped"}


@router.get("/preview/status")
def preview_status():
    with _STATE_LOCK:
        state = dict(_PREVIEW_STATE)
    return {
        **state,
        "step_labels": STEP_LABELS,
        "step_order": STEP_ORDER,
        # Legacy fields kept for backwards compat
        "status": state["phase"],
        "frontend_port": FRONTEND_PORT,
        "backend_port": BACKEND_PORT,
    }
