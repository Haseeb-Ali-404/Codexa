from __future__ import annotations

import re
from typing import Any, Callable, List


class IntegratorAgent:
    """
    Scans generated project file contents to detect and fix frontend/backend integration issues.
    Replaces the old filename-only checker with real content analysis.
    """

    def __init__(
        self,
        config_path: str | None = None,
        env_getter: Callable[[str], str | None] | None = None,
        verbose: bool = True,
        **kwargs: Any,
    ) -> None:
        self._config_path = config_path
        self._env_getter = env_getter
        self.verbose = verbose
        self.integration_errors: List[str] = []
        self.integration_fixes: List[str] = []

    def _child_kwargs(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self._config_path is not None:
            out["config_path"] = self._config_path
        if self._env_getter is not None:
            out["env_getter"] = self._env_getter
        return out

    def _flatten(self, structure: list, prefix: str = "") -> list[dict]:
        """Recursively flatten nested structure into list of {path, content}."""
        files = []
        for node in structure:
            name = node.get("name", "")
            path = f"{prefix}/{name}".lstrip("/")
            if node.get("type") == "file":
                files.append({"path": path, "content": node.get("content", "")})
            elif node.get("type") == "folder":
                files.extend(self._flatten(node.get("children", []), path))
        return files

    def _extract_backend_routes(self, files: list[dict]) -> set[str]:
        """Extract all API route paths from backend Python files."""
        routes = set()
        pattern = re.compile(
            r'@\w+\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']'
        )
        for f in files:
            if not f["path"].startswith("backend/"):
                continue
            if not f["path"].endswith(".py"):
                continue
            for m in pattern.finditer(f["content"]):
                routes.add(m.group(2))
        return routes

    def _extract_frontend_api_calls(self, files: list[dict]) -> set[str]:
        """Extract all API paths called from frontend."""
        calls = set()
        # Match api.get('/foo'), axios.post('/bar'), fetch('/api/baz')
        pattern = re.compile(
            r'(?:api|axios|instance)\s*\.\s*(?:get|post|put|patch|delete)\s*\(\s*["`\']([^"`\']+)["`\']'
        )
        fetch_pattern = re.compile(
            r'fetch\s*\(\s*["`\']([/][^"`\']+)["`\']'
        )
        for f in files:
            if not f["path"].startswith("frontend/"):
                continue
            if not f["path"].endswith((".ts", ".tsx")):
                continue
            for m in pattern.finditer(f["content"]):
                path = m.group(1)
                # Normalize: strip /api prefix since backend routes don't include it
                path = re.sub(r'^/api', '', path)
                # Strip dynamic segments like /tasks/123 → /tasks
                path = re.sub(r'/[0-9a-f]{24}$', '', path)
                if path:
                    calls.add(path)
            for m in fetch_pattern.finditer(f["content"]):
                path = m.group(1)
                path = re.sub(r'^/api', '', path)
                if path:
                    calls.add(path)
        return calls

    def _extract_router_prefixes(self, files: list[dict]) -> dict[str, str]:
        """Extract include_router prefix mappings from main.py."""
        prefix_map = {}
        main_files = [f for f in files if f["path"] in ("backend/main.py", "main.py")]
        pattern = re.compile(
            r'include_router\s*\(\s*(\w+)\.router.*?prefix\s*=\s*["\']([^"\']+)["\']',
            re.DOTALL
        )
        for f in main_files:
            for m in pattern.finditer(f["content"]):
                prefix_map[m.group(1)] = m.group(2)
        return prefix_map

    def _check_auth_interceptor(self, files: list[dict]) -> list[str]:
        """Check that frontend api.ts has an axios interceptor."""
        errors = []
        api_files = [
            f for f in files
            if f["path"].startswith("frontend/") and
               any(f["path"].endswith(x) for x in ("api.ts", "apiService.ts", "api/index.ts"))
        ]
        for f in api_files:
            if "axios.create" in f["content"] and "interceptors.request" not in f["content"]:
                errors.append(
                    f"MISSING auth interceptor in {f['path']} — "
                    "all authenticated API calls will return 401 after login"
                )
        return errors

    def _check_cors_port(self, files: list[dict]) -> list[str]:
        """Check that backend main.py CORS allows port 5959."""
        errors = []
        for f in files:
            if "main.py" in f["path"] and "CORSMiddleware" in f["content"]:
                if "5959" not in f["content"]:
                    errors.append(
                        "Backend CORS missing port 5959 — frontend requests will be blocked by CORS"
                    )
        return errors

    def _check_route_files_included(self, files: list[dict]) -> list[str]:
        """Check that all route files are registered in main.py."""
        errors = []
        route_files = [
            f for f in files
            if re.search(r'backend/app/routes/\w+\.py$', f["path"])
            and not f["path"].endswith("__init__.py")
        ]
        main_content = ""
        for f in files:
            if f["path"] in ("backend/main.py",):
                main_content = f["content"]
                break

        if not main_content:
            return errors

        for rf in route_files:
            module = rf["path"].split("/")[-1].replace(".py", "")
            # Check if this router is included (rough check)
            if module not in main_content and f"routes.{module}" not in main_content:
                errors.append(f"Route file {rf['path']} may not be included in main.py")

        return errors

    def fix_project(self, project_json: dict) -> dict:
        """
        Scan and auto-fix integration issues in the project JSON.
        Returns {fixes_applied: [...], errors_remaining: [...]}.
        """
        if not project_json or "structure" not in project_json:
            return {"fixes_applied": [], "errors_remaining": ["Invalid project structure"]}

        files = self._flatten(project_json["structure"])
        fixes = []
        errors = []

        # Check auth interceptor
        auth_errors = self._check_auth_interceptor(files)
        errors.extend(auth_errors)

        # Inject auth interceptor into api.ts if missing
        for f in files:
            if (f["path"].startswith("frontend/") and
                    any(f["path"].endswith(x) for x in ("api.ts", "apiService.ts")) and
                    "axios.create" in f["content"] and
                    "interceptors.request" not in f["content"]):
                interceptor = '''
// Auto-fix: attach JWT token to every request
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
'''
                if "export default" in f["content"]:
                    f["content"] = f["content"].replace("export default", interceptor + "\nexport default", 1)
                else:
                    f["content"] += interceptor
                fixes.append(f"Injected axios auth interceptor into {f['path']}")
                # Write back into structure
                self._write_back(project_json["structure"], f["path"], f["content"])

        # Check and fix CORS
        cors_errors = self._check_cors_port(files)
        for f in files:
            if "main.py" in f["path"] and "CORSMiddleware" in f["content"] and "5959" not in f["content"]:
                f["content"] = f["content"].replace(
                    '"http://localhost:5173"',
                    '"http://localhost:5959", "http://localhost:5173"'
                )
                f["content"] = f["content"].replace(
                    "'http://localhost:5173'",
                    "'http://localhost:5959', 'http://localhost:5173'"
                )
                fixes.append(f"Added port 5959 to CORS in {f['path']}")
                self._write_back(project_json["structure"], f["path"], f["content"])

        # Check and auto-fix missing route registrations in main.py
        route_errors = self._check_route_files_included(files)
        for f in files:
            if f["path"] not in ("backend/main.py",):
                continue
            for rf in [x for x in files if re.search(r'backend/app/routes/\w+\.py$', x["path"])
                       and not x["path"].endswith("__init__.py")]:
                module = rf["path"].split("/")[-1].replace(".py", "")
                if module not in f["content"] and f"routes.{module}" not in f["content"]:
                    # Auto-inject the include_router call
                    import_line = f"from app.routes import {module}"
                    router_line = f'app.include_router({module}.router, prefix="/api/{module}", tags=["{module}"])'
                    if import_line not in f["content"]:
                        f["content"] = f["content"].replace(
                            "from app.routes import auth",
                            f"from app.routes import auth\n{import_line}"
                        )
                    if router_line not in f["content"]:
                        # Inject after auth router line
                        f["content"] = re.sub(
                            r'(app\.include_router\(auth\.router[^\n]+\n)',
                            r'\1' + router_line + '\n',
                            f["content"]
                        )
                    fixes.append(f"Auto-registered {module} router in main.py")
                    self._write_back(project_json["structure"], f["path"], f["content"])

        errors.extend(route_errors)

        # Cross-check API endpoints
        backend_routes = self._extract_backend_routes(files)
        frontend_calls = self._extract_frontend_api_calls(files)

        mismatches = frontend_calls - backend_routes
        if mismatches and self.verbose:
            print(f"[Integrator] Potential missing backend routes: {mismatches}")

        if self.verbose:
            print(f"[Integrator] Fixes applied: {len(fixes)}")
            print(f"[Integrator] Remaining errors: {len(errors)}")

        self.integration_fixes = fixes
        self.integration_errors = errors

        return {
            "fixes_applied": fixes,
            "errors_remaining": errors,
            "backend_routes": list(backend_routes),
            "frontend_calls": list(frontend_calls),
            "missing_backend_routes": list(mismatches),
        }

    def _write_back(self, structure: list, target_path: str, content: str, prefix: str = "") -> bool:
        for node in structure:
            path = f"{prefix}/{node['name']}".lstrip("/")
            if node["type"] == "file" and path == target_path:
                node["content"] = content
                return True
            elif node["type"] == "folder":
                if self._write_back(node.get("children", []), target_path, content, path):
                    return True
        return False

    def verify_routing_integration(self, project_json: dict) -> List[str]:
        files = self._flatten(project_json.get("structure", []))
        return self._check_auth_interceptor(files) + self._check_cors_port(files)

    def verify_api_integration(self, project_json: dict) -> List[str]:
        files = self._flatten(project_json.get("structure", []))
        backend_routes = self._extract_backend_routes(files)
        frontend_calls = self._extract_frontend_api_calls(files)
        mismatches = frontend_calls - backend_routes
        return [f"Frontend calls missing backend route: {r}" for r in mismatches]

    def verify_data_flow_integration(self, project_json: dict) -> List[str]:
        files = self._flatten(project_json.get("structure", []))
        return self._check_route_files_included(files)

    def generate_project(self, name: str, user_message: str | None = None) -> dict:
        from core.factory.agent_factory import create_agent
        kw = self._child_kwargs()
        um = user_message or name

        planner = create_agent("planner", **kw)
        plan = planner.plan(um)
        if not plan or "steps" not in plan:
            raise RuntimeError("Planner failed")

        developer = create_agent("developer", **kw)
        project_json = developer.generate_project(
            plan.get("title", name),
            plan["steps"],
            um,
            developer_plan=plan.get("developer_plan"),
        )
        if not project_json or "structure" not in project_json:
            raise RuntimeError("Developer failed")

        # Run real integration fixes
        fix_result = self.fix_project(project_json)

        debugger = create_agent("debugger", **kw)
        ok = debugger.validate(project_json)

        return {
            "title": plan.get("title", name),
            "plan": plan["steps"],
            "project": project_json,
            "valid": ok,
            "integration_fixes": fix_result["fixes_applied"],
            "integration_errors": fix_result["errors_remaining"],
            "missing_backend_routes": fix_result.get("missing_backend_routes", []),
        }
