import re
import time
import json
from typing import Any, Callable, Awaitable

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient
from .planner_stages import run_stage_1, run_stage_2, run_stage_3, run_stage_4, run_stage_5
from .planner_errors import PlannerStageError, PlannerCycleError





# ─────────────────────────────────────────────────────────────────────────────
# Multi-stage pipeline planner (extracted core + WebSocket adapter)
# ─────────────────────────────────────────────────────────────────────────────

def _api_key_getter(provider_id: str) -> str | None:
    """Resolve API key from environment using existing credentials util."""
    from core.utils.credentials import resolve_api_key_for_provider
    return resolve_api_key_for_provider(provider_id)


def _slug_to_title(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    if not words:
        return "Project"
    stop_words = {"build", "create", "make", "develop", "design", "full", "stack", "platform", "app", "application", "system", "saas"}
    kept = [w for w in words if w.lower() not in stop_words]
    target = kept or words
    return " ".join(word.capitalize() for word in target[:4]).strip() or "Project"


def _infer_app_type(user_input: str) -> str:
    text = (user_input or "").lower()
    if "ecommerce" in text or "commerce" in text or "store" in text:
        return "ecommerce"
    if "dashboard" in text or "admin" in text or "analytics" in text:
        return "dashboard"
    if "marketplace" in text:
        return "marketplace"
    if "social" in text:
        return "social"
    if "productivity" in text:
        return "productivity"
    if "saas" in text:
        return "saas"
    return "other"


def _extract_app_name(user_input: str) -> str:
    text = (user_input or "").strip()
    patterns = [
        r'named\s+"([^"]+)"',
        r"named\s+'([^']+)'",
        r"called\s+\"([^\"]+)\"",
        r"called\s+'([^']+)'",
        r"named\s+([A-Za-z0-9][A-Za-z0-9 &._-]{1,60})",
        r"called\s+([A-Za-z0-9][A-Za-z0-9 &._-]{1,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,:;")[:80] or "Project"
    return _slug_to_title(text)


def _extract_entities(user_input: str) -> list[str]:
    text = (user_input or "").lower()
    entities = ["User"]
    entity_keywords = [
        ("product", "Product"),
        ("order", "Order"),
        ("customer", "Customer"),
        ("coupon", "Coupon"),
        ("inventory", "InventoryItem"),
        ("category", "Category"),
        ("payment", "Payment"),
        ("notification", "Notification"),
        ("activity", "ActivityLog"),
    ]
    for keyword, label in entity_keywords:
        if keyword in text and label not in entities:
            entities.append(label)
    if len(entities) == 1:
        entities.extend(["Item", "Task"])
    return entities[:6]


def _fallback_features(user_input: str) -> list[str]:
    text = (user_input or "").lower()
    features: list[str] = []
    keyword_features = [
        ("auth", "Implement secure authentication and role-based access control"),
        ("role", "Implement secure authentication and role-based access control"),
        ("product", "Build complete product management with CRUD, pricing, stock, and status"),
        ("order", "Build order management with lifecycle status tracking and payment visibility"),
        ("customer", "Add customer management with profiles, history, and activity tracking"),
        ("coupon", "Support coupons with validation, expiry, and usage limits"),
        ("analytic", "Add analytics dashboard cards and charts for revenue, orders, and top products"),
        ("inventory", "Provide inventory monitoring and low-stock alerts"),
        ("notification", "Implement key notifications for important business events"),
        ("activity", "Record admin activity logs for operational auditing"),
    ]
    for keyword, feature in keyword_features:
        if keyword in text and feature not in features:
            features.append(feature)
    if not features:
        features = [
            "Set up authentication and protected application areas",
            "Build core CRUD workflows for the main business entities",
            "Create a responsive dashboard experience for desktop and mobile",
            "Integrate frontend views with backend APIs and validation",
            "Add analytics, status tracking, and operational visibility",
        ]
    return features[:8]


def _fallback_user_plan(user_input: str) -> dict:
    app_name = _extract_app_name(user_input)
    app_type = _infer_app_type(user_input)
    features = _fallback_features(user_input)
    entities = _extract_entities(user_input)
    return {
        "app_name": app_name,
        "app_type": app_type,
        "description": f"{app_name} is a {app_type} platform designed from the user's request.",
        "target_users": "Business operators, administrators, and internal staff",
        "features": features,
        "entities": entities,
        "auth_required": True,
        "key_workflows": [
            "Users authenticate and access protected areas based on role",
            "Operators manage core business records through dashboard workflows",
            "Teams monitor operations, status changes, and important alerts",
        ],
    }


def _fallback_steps(user_plan: dict) -> list[str]:
    entities = [entity for entity in (user_plan.get("entities") or []) if entity != "User"]
    primary_entity = entities[0] if entities else "Item"
    raw_steps = [
        "Set up FastAPI backend, React frontend, MongoDB database, and authentication",
        "Implement secure login, protected routes, and role-based access control",
        f"Build {primary_entity} management flows with validation, status handling, and CRUD APIs",
        "Create responsive dashboard pages, tables, filters, forms, and loading states",
        "Add analytics, notifications, and audit visibility for business operations",
        "Connect frontend and backend end-to-end, then verify key workflows",
    ]
    return raw_steps[:6]


def _fallback_structure(user_plan: dict) -> dict:
    app_name = (user_plan.get("app_name") or "Project").strip() or "Project"
    entities = [entity for entity in (user_plan.get("entities") or []) if entity != "User"]
    backend_modules = [{"name": "auth", "description": "Authentication, authorization, and current-user endpoints"}]
    frontend_modules = [{"name": "auth", "description": "Login, protected routes, and persisted auth state"}]
    for entity in entities[:4]:
        backend_modules.append(
            {"name": entity.lower(), "description": f"{entity} CRUD, validation, and service logic"}
        )
        frontend_modules.append(
            {"name": entity.lower(), "description": f"{entity} pages, state, forms, and table views"}
        )
    return {
        "title": f"{app_name} Platform",
        "steps": _fallback_steps(user_plan),
        "stack": {
            "frontend": "react-vite",
            "backend": "fastapi",
            "database": "mongodb",
        },
        "backend_modules": backend_modules,
        "frontend_modules": frontend_modules,
        "auth_strategy": "JWT Bearer token with role-based access control",
        "state_management": "zustand",
    }


def _fallback_contracts(user_plan: dict) -> dict:
    entities = [entity for entity in (user_plan.get("entities") or []) if entity != "User"]
    primary_entity = entities[0] if entities else "Item"
    entity_slug = re.sub(r"(?<!^)(?=[A-Z])", "-", primary_entity).replace("_", "-").lower()
    return {
        "interfaces": [
            {
                "name": "User",
                "fields": {"id": "string", "email": "string", "name": "string", "role": "string"},
                "description": "Authenticated user object",
            },
            {
                "name": primary_entity,
                "fields": {"id": "string", "name": "string", "status": "string", "createdAt": "string"},
                "description": f"Primary {primary_entity} record",
            },
        ],
        "api_contracts": [
            {"method": "POST", "path": "/api/auth/login", "request": "LoginRequest", "response": "AuthResponse", "auth": False, "status": 200},
            {"method": "GET", "path": "/api/auth/me", "response": "User", "auth": True, "status": 200},
            {"method": "GET", "path": f"/api/{entity_slug}", "response": f"{primary_entity}[]", "auth": True, "status": 200},
        ],
        "models": [
            {"name": "User", "fields": {"email": "str", "name": "str", "role": "str"}, "collection": "users"},
            {"name": primary_entity, "fields": {"name": "str", "status": "str", "created_at": "datetime"}, "collection": f"{entity_slug}s"},
        ],
    }


def _fallback_connections(structure: dict, contracts: dict) -> dict:
    api_contracts = contracts.get("api_contracts") or []
    first_path = api_contracts[0]["path"] if api_contracts else "/api/auth/login"
    return {
        "dependency_graph": [
            {"from": "frontend/auth", "to": "backend/auth", "type": "api", "via": [first_path]},
            {"from": "frontend/dashboard", "to": "backend/database", "type": "data", "via": "protected services"},
        ],
        "flow": "User authenticates, frontend stores the session token, protected API requests include auth, and the backend returns validated data.",
        "critical_paths": [
            "Login -> protected route -> dashboard",
            "Dashboard action -> API request -> database update -> UI refresh",
        ],
    }


def _fallback_safety() -> dict:
    return {
        "rules": [
            "All protected routes require authentication and role checks",
            "All user input must be validated on both frontend and backend",
            "API failures should return clear messages and user-friendly UI feedback",
        ],
        "completeness": False,
        "env_example": {
            "MONGO_URL": "mongodb://localhost:27017",
            "DATABASE_NAME": "app_db",
            "SECRET_KEY": "change-me",
        },
        "error_boundaries": [
            "Show loading, empty, and error states for data views",
            "Wrap async UI actions with toast or inline error handling",
        ],
        "test_stubs": [],
        "update_strategy": {
            "on_entity_add": "Add matching backend module, API route, frontend page, and state store",
        },
    }


async def run_planner_pipeline_core(
    user_input: str,
    event_sender: Callable[[dict], Awaitable[None]] | None = None,
    *,
    max_retries: int = 2,
    llm_options_overrides: dict | None = None,
) -> dict:
    """
    Core 5-stage planner pipeline, optionally streaming events via `event_sender`.
    Returns the complete plan dictionary.
    """
    outputs: dict[str, dict] = {
        "user_plan": {},
        "structure": {},
        "contracts": {},
        "connections": {},
        "safety": {},
    }

    async def send(event: dict):
        if event_sender:
            await event_sender(event)

    async def stage_start(stage: int, message: str):
        await send({"type": "stage_start", "stage": stage, "message": message})

    async def stage_complete(stage: int, output: dict):
        await send({"type": "stage_complete", "stage": stage, "output": output})

    async def stage_retry(stage: int, message: str):
        await send({"type": "stage_retry", "stage": stage, "message": message})

    async def stage_warning(stage: int, warnings: list[str]):
        await send({"type": "stage_warning", "stage": stage, "warnings": warnings})

    try:
        # ── STAGE 1 ────────────────────────────────────────────────────────────
        await stage_start(1, "Understanding your idea…")
        result_1 = None
        for attempt in range(1, max_retries + 1):
            result_1 = await run_stage_1(user_input, attempt, _api_key_getter, llm_options_overrides)
            if result_1["success"] and (result_1.get("output") or {}):
                outputs["user_plan"] = result_1.get("output") or {}
                await stage_complete(1, result_1["output"])
                break
            if attempt == max_retries:
                await stage_warning(1, list(result_1.get("errors") or ["Stage 1 fallback applied"]))
                outputs["user_plan"] = _fallback_user_plan(user_input)
                break
            await stage_retry(1, "Refining understanding…")

        # ── STAGE 2 ────────────────────────────────────────────────────────────
        await stage_start(2, "Designing structure…")
        result_2 = None
        for attempt in range(1, max_retries + 1):
            result_2 = await run_stage_2(outputs["user_plan"], attempt, _api_key_getter, llm_options_overrides)
            if result_2["success"] and (result_2.get("output") or {}):
                outputs["structure"] = result_2.get("output") or {}
                await stage_complete(2, result_2["output"])
                break
            if attempt == max_retries:
                await stage_warning(2, list(result_2.get("errors") or ["Stage 2 fallback applied"]))
                outputs["structure"] = _fallback_structure(outputs["user_plan"])
                break
            await stage_retry(2, "Refining structure…")

        # ── STAGE 3 ────────────────────────────────────────────────────────────
        await stage_start(3, "Defining contracts…")
        result_3 = None
        for attempt in range(1, max_retries + 1):
            result_3 = await run_stage_3(outputs["user_plan"], outputs["structure"], attempt, _api_key_getter, llm_options_overrides)
            if result_3["success"] and (result_3.get("output") or {}):
                outputs["contracts"] = result_3.get("output") or {}
                await stage_complete(3, result_3["output"])
                break
            if attempt == max_retries:
                await stage_warning(3, list(result_3.get("errors") or ["Stage 3 fallback applied"]))
                outputs["contracts"] = _fallback_contracts(outputs["user_plan"])
                break
            await stage_retry(3, "Fixing contracts…")

        # ── STAGE 4 ────────────────────────────────────────────────────────────
        await stage_start(4, "Connecting modules…")
        result_4 = None
        for attempt in range(1, max_retries + 1):
            result_4 = await run_stage_4(outputs["structure"], outputs["contracts"], attempt, _api_key_getter, llm_options_overrides)
            if result_4["success"] and (result_4.get("output") or {}):
                outputs["connections"] = result_4.get("output") or {}
                await stage_complete(4, result_4["output"])
                break
            if attempt == max_retries:
                await stage_warning(4, list(result_4.get("errors") or ["Stage 4 fallback applied"]))
                outputs["connections"] = _fallback_connections(outputs["structure"], outputs["contracts"])
                break
            await stage_retry(4, "Fixing dependencies…")

        # ── STAGE 5 ────────────────────────────────────────────────────────────
        await stage_start(5, "Finalizing project…")
        result_5 = None
        for attempt in range(1, max_retries + 1):
            result_5 = await run_stage_5(outputs, attempt, _api_key_getter, llm_options_overrides)
            if result_5["success"] and (result_5.get("output") or {}):
                outputs["safety"] = result_5.get("output") or {}
                await stage_complete(5, result_5["output"])
                break
            if attempt == max_retries:
                await stage_warning(5, list(result_5.get("errors") or ["Stage 5 fallback applied"]))
                outputs["safety"] = _fallback_safety()
                break
            await stage_retry(5, "Refining safety rules…")

        # Build final developer plan
        contracts_out = outputs.get("contracts") or {}
        connections_out = outputs.get("connections") or {}
        safety_out = outputs.get("safety") or {}
        structure_out = outputs.get("structure") or {}

        developer_plan = {
            **structure_out,
            "interfaces": contracts_out.get("interfaces", []),
            "api_contracts": contracts_out.get("api_contracts", []),
            "models": contracts_out.get("models", []),
            "dependency_graph": connections_out.get("dependency_graph", []),
            "flow": connections_out.get("flow", ""),
            "rules": safety_out.get("rules", []),
            "update_strategy": safety_out.get("update_strategy", {}),
            "completeness": safety_out.get("completeness", False),
            "env_example": safety_out.get("env_example", {}),
            "test_stubs": safety_out.get("test_stubs", []),
            "error_boundaries": safety_out.get("error_boundaries", []),
        }
        if not outputs.get("user_plan"):
            outputs["user_plan"] = _fallback_user_plan(user_input)
        if not outputs.get("structure"):
            outputs["structure"] = _fallback_structure(outputs["user_plan"])
            developer_plan = {
                **outputs["structure"],
                **developer_plan,
            }

        await send({"type": "pipeline_complete", "user_plan": outputs["user_plan"], "developer_plan": developer_plan})

        return {
            "user_plan": outputs["user_plan"],
            "developer_plan": developer_plan,
        }

    except Exception as e:
        import traceback
        print(f"[Planner] ❌ Pipeline unexpected failure: {e}")
        print(traceback.format_exc())
        await stage_warning(0, [f"Pipeline failure: {str(e)}"])
        user_plan = _fallback_user_plan(user_input)
        developer_plan = _fallback_structure(user_plan)
        await send({"type": "pipeline_complete", "user_plan": user_plan, "developer_plan": developer_plan})
        return {
            "user_plan": user_plan,
            "developer_plan": developer_plan,
        }


async def run_planner_pipeline(
    user_input: str,
    websocket: Any,
    *,
    max_retries: int = 2,
    llm_options_overrides: dict | None = None,
) -> dict:
    """
    WebSocket adapter: calls `run_planner_pipeline_core` and forwards events to `websocket`.
    """
    async def sender(event: dict):
        try:
            await websocket.send_json(event)
        except Exception as e:
            print(f"[Planner] ⚠️ WS send failed (event type={event.get('type')}): {e}")

    return await run_planner_pipeline_core(
        user_input,
        event_sender=sender,
        max_retries=max_retries,
        llm_options_overrides=llm_options_overrides,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatible PlannerAgent wrapper (5-stage pipeline)
# ─────────────────────────────────────────────────────────────────────────────

FALLBACK_PLAN = {
    "title": "Generic Software Project",
    "steps": [
        "Define project requirements",
        "Design system architecture",
        "Set up backend structure",
        "Implement core backend features",
        "Build frontend interface",
        "Connect frontend with backend",
        "Test and debug the application",
        "Prepare the project for deployment",
    ],
}


class PlannerAgent:
    """
    Maintains the original PlannerAgent interface while delegating to the
    new 5-stage pipeline.
    """

    def __init__(
        self,
        llm_client: Any = None,
        llm_options: Any = None,
        max_retries: int = 2,
        retry_delays: tuple[int, ...] = (2, 5, 10),
    ) -> None:
        # The new pipeline reads its own configuration from agents.config.json,
        # so we don't store the client/options. They are accepted only for
        # backward compatibility with factory injection.
        self.max_retries = max_retries
        self.retry_delays = retry_delays

    def plan(self, request: str) -> dict:
        """Synchronous planning. Returns {'title': str, 'steps': list[str], 'developer_plan': dict}."""
        try:
            import asyncio

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                return FALLBACK_PLAN.copy()

            result = asyncio.run(
                run_planner_pipeline_core(
                    request, max_retries=self.max_retries
                )
            )
            user_plan = result.get("user_plan", {})
            developer_plan = result.get("developer_plan", {})
            title = (
                (developer_plan.get("title") or "").strip()
                or self._derive_title(user_plan, request)
            )
            steps = developer_plan.get("steps") or user_plan.get("features", [])
            return {
                "title": title,
                "steps": steps,
                "developer_plan": developer_plan,
                "user_plan": user_plan,
            }
        except Exception:
            return FALLBACK_PLAN.copy()

    async def astream_plan_text(self, request: str):
        """
        Stream raw plan text. Since the new pipeline does not stream raw
        text, we emit the final JSON as a single chunk.
        """
        try:
            result = await run_planner_pipeline_core(
                request, max_retries=self.max_retries
            )
            user_plan = result.get("user_plan", {})
            developer_plan = result.get("developer_plan", {})
            title = (
                (developer_plan.get("title") or "").strip()
                or self._derive_title(user_plan, request)
            )
            steps = developer_plan.get("steps") or user_plan.get("features", [])
            yield json.dumps({"title": title, "steps": steps}, indent=2)
        except Exception:
            yield json.dumps(FALLBACK_PLAN, indent=2)

    def parse_plan_from_raw(self, raw_text: str) -> dict | None:
        """Parse raw text into a plan dict. Accepts JSON or falls back to extraction."""
        if not raw_text:
            return None
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict) and "steps" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
        title = self.extract_title(raw_text)
        steps = self._clean_steps(raw_text)
        if steps:
            return {"title": title, "steps": steps}
        return None

    def extract_title(self, raw_text: str) -> str:
        """Legacy title extraction from raw text."""
        if not raw_text:
            return "Untitled Project"
        patterns = [
            r"\*\*Project Title[:\- ]*(.*?)\*\*",
            r"Project Title[:\- ]*(.*)",
            r"Title[:\- ]*(.*)",
        ]
        for pattern in patterns:
            m = re.search(pattern, raw_text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        m = re.search(r"\*\*(.*?)\*\*", raw_text)
        if m:
            candidate = m.group(1).strip()
            if not re.match(r"^\d+[\.\)]", candidate):
                return candidate
        for line in raw_text.splitlines():
            if line.strip():
                return line.strip()
        return "Untitled Project"

    def _clean_steps(self, raw_text: str) -> list[str]:
        """Legacy step extraction from raw text."""
        if not raw_text:
            return []
        steps: list[str] = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            clean = re.sub(r"^(\d+[\.\)]|\-|\*|\•)\s*", "", line)
            clean = re.sub(r"[*_#>`~]", "", clean).strip()
            if clean:
                steps.append(clean)
        return steps

    def _derive_title(self, user_plan: dict, original_input: str) -> str:
        """Derive a concise title from the plan's app_name and description."""
        app_name = (user_plan.get("app_name") or "").strip()
        description = (user_plan.get("description") or "").strip()

        if app_name:
            if description:
                tagline = description.split(".")[0].strip()
                if len(tagline) > 45:
                    tagline = tagline[:42] + "..."
                return f"{app_name} - {tagline}"[:80]
            return app_name[:80]

        try:
            from core.factory.agent_factory import create_agent
            title_agent = create_agent("title")
            return title_agent.generate_title(original_input)
        except Exception:
            return "Project"
