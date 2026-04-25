"""
Five-stage planning pipeline. Each stage makes a focused LLM call and returns
{"success": bool, "output": dict, "errors": list[str]}.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Callable


async def _llm_json(
    prompt: str,
    required_keys: list[str],
    *,
    max_tokens: int = 4096,
    overrides: dict | None = None,
) -> dict:
    """Call the planner LLM, parse JSON, validate required keys."""
    from core.factory.agent_factory import build_llm_client_for_agent
    from core.providers.base import ChatMessage, LLMCallOptions

    client, _ = build_llm_client_for_agent("planner")
    opts = LLMCallOptions(temperature=0.1, max_tokens=max_tokens, timeout_seconds=90)
    if overrides:
        for k, v in overrides.items():
            if hasattr(opts, k):
                setattr(opts, k, v)

    result = await asyncio.to_thread(
        client.complete, [ChatMessage(role="user", content=prompt)], opts
    )
    raw = (result.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e} — snippet={raw[:200]}")

    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValueError(f"Missing required keys: {missing}")

    return data


async def run_stage_1(
    user_input: str,
    attempt: int,
    api_key_getter: Callable,
    overrides: dict | None,
) -> dict:
    """Stage 1: Understand user intent → user_plan."""
    prompt = f"""You are an expert product analyst. Analyze this project request.

USER REQUEST:
{user_input}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "app_name": "short name for the app",
  "app_type": "saas|marketplace|dashboard|social|ecommerce|productivity|tools|other",
  "description": "2-3 sentence description of what the app does and its value",
  "target_users": "who will use this app",
  "features": [
    "Specific feature 1 with detail",
    "Specific feature 2 with detail",
    "... (5-10 concrete, implementable features)"
  ],
  "entities": ["User", "EntityName1", "EntityName2"],
  "auth_required": true,
  "key_workflows": [
    "User can register, login, and manage their profile",
    "User can create, view, edit, and delete [main entity]",
    "... (3-5 main user journeys)"
  ]
}}"""

    try:
        output = await _llm_json(prompt, ["app_name", "features", "entities"], overrides=overrides)
        if not output.get("features"):
            raise ValueError("features list is empty")
        return {"success": True, "output": output, "errors": []}
    except Exception as e:
        return {"success": False, "output": {}, "errors": [str(e)]}


async def run_stage_2(
    user_plan: dict,
    attempt: int,
    api_key_getter: Callable,
    overrides: dict | None,
) -> dict:
    """Stage 2: Design project structure → structure dict with steps."""
    entities_str = json.dumps(user_plan.get("entities", []))
    features_str = json.dumps(user_plan.get("features", []))

    prompt = f"""You are a senior software architect. Design the technical structure for this app.

APP: {user_plan.get("app_name", "App")}
DESCRIPTION: {user_plan.get("description", "")}
FEATURES: {features_str}
ENTITIES: {entities_str}
AUTH REQUIRED: {user_plan.get("auth_required", True)}

Stack rules:
- Default stack: FastAPI (Python) backend + React/Vite (TypeScript) frontend + MongoDB
- Only use nextjs if the user explicitly requested it
- Always use: Zustand for state, react-hook-form+zod for forms, axios for HTTP, lucide-react for icons

Return ONLY valid JSON:
{{
  "title": "Full Project Title",
  "steps": [
    "Set up FastAPI backend with MongoDB and JWT authentication",
    "Implement user registration, login, and profile management",
    "Create EntityName CRUD API endpoints with JWT protection",
    "Build React frontend with Zustand stores and react-hook-form",
    "Implement EntityName list, create, edit, and delete pages",
    "Add responsive layout with Sidebar, Header, and navigation"
  ],
  "stack": {{
    "frontend": "react-vite",
    "backend": "fastapi",
    "database": "mongodb"
  }},
  "backend_modules": [
    {{"name": "auth", "description": "JWT auth: register, login, get current user"}},
    {{"name": "EntityName", "description": "CRUD for EntityName: list, create, update, delete"}}
  ],
  "frontend_modules": [
    {{"name": "auth", "description": "LoginPage, RegisterPage, authStore with JWT persist"}},
    {{"name": "EntityName", "description": "EntityNamePage, EntityNameStore, EntityName forms"}}
  ],
  "auth_strategy": "JWT Bearer token, stored in Zustand with persist name auth-storage-v2",
  "state_management": "zustand"
}}

Replace EntityName with actual entity names from: {entities_str}"""

    try:
        output = await _llm_json(prompt, ["title", "steps", "stack"], overrides=overrides)
        if not output.get("steps"):
            raise ValueError("steps list is empty")
        return {"success": True, "output": output, "errors": []}
    except Exception as e:
        return {"success": False, "output": {}, "errors": [str(e)]}


async def run_stage_3(
    user_plan: dict,
    structure: dict,
    attempt: int,
    api_key_getter: Callable,
    overrides: dict | None,
) -> dict:
    """Stage 3: Define contracts → TypeScript interfaces + API routes + Pydantic models."""
    entities = user_plan.get("entities", ["Item"])
    stack = structure.get("stack", {})
    entity_list = ", ".join(entities)

    prompt = f"""You are a full-stack TypeScript/Python expert. Define precise contracts for this project.

APP: {user_plan.get("app_name", "App")}
ENTITIES: {json.dumps(entities)}
BACKEND: {stack.get("backend", "fastapi")}
FRONTEND: {stack.get("frontend", "react-vite")}

Return ONLY valid JSON.
Keep the payload compact and deterministic:
- Include auth contracts plus at most 3 core domain entities from: {entity_list}
- Keep each interface/model limited to fields needed for auth, CRUD, analytics, and status handling
- Keep api_contracts to the most important endpoints only (max 12)
- Use plain JSON string values only, with no comments and no markdown

Replace ENTITY with actual entity names from: {entity_list}
{{
  "interfaces": [
    {{
      "name": "User",
      "fields": {{"id": "string", "email": "string", "name": "string", "createdAt": "string"}},
      "description": "Authenticated user object"
    }},
    {{
      "name": "ENTITY",
      "fields": {{"id": "string", "title": "string", "description": "string", "userId": "string", "createdAt": "string"}},
      "description": "Main data entity"
    }},
    {{
      "name": "LoginRequest",
      "fields": {{"email": "string", "password": "string"}},
      "description": "Login form payload"
    }},
    {{
      "name": "RegisterRequest",
      "fields": {{"email": "string", "password": "string", "name": "string"}},
      "description": "Register form payload"
    }},
    {{
      "name": "AuthResponse",
      "fields": {{"access_token": "string", "token_type": "string", "user": "User"}},
      "description": "Auth endpoint response"
    }},
    {{
      "name": "CreateENTITYRequest",
      "fields": {{"title": "string", "description": "string"}},
      "description": "Create entity payload"
    }}
  ],
  "api_contracts": [
    {{"method": "POST", "path": "/api/auth/register", "request": "RegisterRequest", "response": "AuthResponse", "auth": false, "status": 201}},
    {{"method": "POST", "path": "/api/auth/login", "request": "LoginRequest", "response": "AuthResponse", "auth": false, "status": 200}},
    {{"method": "GET", "path": "/api/auth/me", "response": "User", "auth": true, "status": 200}},
    {{"method": "GET", "path": "/api/ENTITY", "response": "ENTITY[]", "auth": true, "status": 200}},
    {{"method": "POST", "path": "/api/ENTITY", "request": "CreateENTITYRequest", "response": "ENTITY", "auth": true, "status": 201}},
    {{"method": "PUT", "path": "/api/ENTITY/{{id}}", "request": "UpdateENTITYRequest", "response": "ENTITY", "auth": true, "status": 200}},
    {{"method": "DELETE", "path": "/api/ENTITY/{{id}}", "response": null, "auth": true, "status": 204}}
  ],
  "models": [
    {{
      "name": "User",
      "fields": {{"email": "str", "name": "str", "hashed_password": "str", "created_at": "datetime", "is_active": "bool"}},
      "collection": "users"
    }},
    {{
      "name": "ENTITY",
      "fields": {{"title": "str", "description": "Optional[str]", "user_id": "str", "created_at": "datetime"}},
      "collection": "entity_plural"
    }}
  ]
}}"""

    try:
        output = await _llm_json(
            prompt,
            ["interfaces", "api_contracts", "models"],
            max_tokens=6144,
            overrides=overrides,
        )
        return {"success": True, "output": output, "errors": []}
    except Exception as e:
        return {"success": False, "output": {}, "errors": [str(e)]}


async def run_stage_4(
    structure: dict,
    contracts: dict,
    attempt: int,
    api_key_getter: Callable,
    overrides: dict | None,
) -> dict:
    """Stage 4: Map module connections → dependency graph + data flow."""
    backend_modules = structure.get("backend_modules", [])
    frontend_modules = structure.get("frontend_modules", [])
    api_contracts = contracts.get("api_contracts", [])[:8]

    prompt = f"""You are a systems architect. Map the connections between modules.

BACKEND MODULES: {json.dumps(backend_modules)}
FRONTEND MODULES: {json.dumps(frontend_modules)}
API CONTRACTS: {json.dumps(api_contracts)}

Return ONLY valid JSON:
{{
  "dependency_graph": [
    {{"from": "frontend/auth", "to": "backend/auth", "type": "api", "via": ["/api/auth/login", "/api/auth/register"]}},
    {{"from": "frontend/entity", "to": "backend/entity", "type": "api", "via": ["/api/entity"]}},
    {{"from": "backend/auth", "to": "backend/database", "type": "db", "collection": "users"}},
    {{"from": "backend/entity", "to": "backend/database", "type": "db", "collection": "entities"}},
    {{"from": "frontend/entity", "to": "frontend/auth", "type": "auth_guard", "via": "ProtectedRoute"}}
  ],
  "flow": "User authenticates → JWT stored in Zustand (auth-storage-v2) → axios interceptor attaches Bearer token → backend validates JWT via Depends(get_current_user) → data returned",
  "critical_paths": [
    "Register/Login → JWT token → authStore.token → ProtectedRoute → Dashboard",
    "EntityPage → entityStore.fetchAll() → GET /api/entity → MongoDB → render list"
  ]
}}"""

    try:
        output = await _llm_json(prompt, ["dependency_graph", "flow"], overrides=overrides)
        return {"success": True, "output": output, "errors": []}
    except Exception as e:
        return {"success": False, "output": {}, "errors": [str(e)]}


async def run_stage_5(
    outputs: dict,
    attempt: int,
    api_key_getter: Callable,
    overrides: dict | None,
) -> dict:
    """Stage 5: Safety & completeness → rules, env vars, error boundaries."""
    user_plan = outputs.get("user_plan", {})
    structure = outputs.get("structure", {})

    # Pre-compute to avoid f-string brace conflicts
    app_name = user_plan.get("app_name", "App")
    stack_json = json.dumps(structure.get("stack", {}))
    entities_json = json.dumps(user_plan.get("entities", []))
    auth_required = user_plan.get("auth_required", True)

    prompt = f"""You are a senior engineer doing a final quality review. Define safety rules and env config.

APP: {app_name}
STACK: {stack_json}
ENTITIES: {entities_json}
AUTH: {auth_required}

Return ONLY valid JSON:
{{
  "rules": [
    "All protected API endpoints use Depends(get_current_user)",
    "Passwords always hashed with bcrypt before storage — never plain text",
    "All forms use react-hook-form + zodResolver — no bare useState for form state",
    "All shared state lives in Zustand stores — no prop drilling across components",
    "Every async function fully implemented — zero TODO, pass, or NotImplementedError",
    "TypeScript: no 'any' types — all interfaces defined in src/types/index.ts",
    "Every list view has: loading skeleton → error state → empty state → data table",
    "Error responses: HTTPException with clear detail messages for 400/401/404"
  ],
  "completeness": true,
  "env_example": {{
    "MONGO_URL": "mongodb://localhost:27017",
    "DATABASE_NAME": "app_db",
    "SECRET_KEY": "change-this-to-a-secure-random-string-in-production",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30"
  }},
  "error_boundaries": [
    "Wrap all page-level async operations in try/catch with toast error feedback",
    "API errors display user-friendly toast notification (not raw error object)",
    "Empty state component with icon + call-to-action for all list views",
    "Loading skeleton placeholders while data fetches"
  ],
  "test_stubs": [],
  "update_strategy": {{
    "on_entity_add": "Create EntityStore (Zustand) + EntityPage + add route in App.tsx",
    "on_field_change": "Update TypeScript interface + Pydantic model + zod schema + form fields"
  }}
}}"""

    try:
        output = await _llm_json(prompt, ["rules", "env_example", "error_boundaries"], overrides=overrides)
        return {"success": True, "output": output, "errors": []}
    except Exception as e:
        return {"success": False, "output": {}, "errors": [str(e)]}
