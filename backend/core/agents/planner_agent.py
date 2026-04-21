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

    async def stage_error(stage: int, errors: list[str]):
        await send({"type": "stage_error", "stage": stage, "errors": errors})

    try:
        # ── STAGE 1 ────────────────────────────────────────────────────────────
        await stage_start(1, "Understanding your idea…")
        result_1 = None
        for attempt in range(1, max_retries + 1):
            result_1 = await run_stage_1(user_input, attempt, _api_key_getter, llm_options_overrides)
            if result_1["success"]:
                outputs["user_plan"] = result_1.get("output") or {}
                if not outputs["user_plan"]:
                    raise ValueError("Stage 1 returned empty user_plan")
                await stage_complete(1, result_1["output"])
                break
            if attempt == max_retries:
                await stage_error(1, result_1["errors"])
                raise PlannerStageError(stage=1, errors=result_1["errors"])
            await stage_retry(1, "Refining understanding…")

        # ── STAGE 2 ────────────────────────────────────────────────────────────
        await stage_start(2, "Designing structure…")
        result_2 = None
        for attempt in range(1, max_retries + 1):
            result_2 = await run_stage_2(outputs["user_plan"], attempt, _api_key_getter, llm_options_overrides)
            if result_2["success"]:
                outputs["structure"] = result_2.get("output") or {}
                if not outputs["structure"]:
                    raise ValueError("Stage 2 returned empty structure")
                await stage_complete(2, result_2["output"])
                break
            if attempt == max_retries:
                await stage_error(2, result_2["errors"])
                raise PlannerStageError(stage=2, errors=result_2["errors"])
            await stage_retry(2, "Refining structure…")

        # ── STAGE 3 ────────────────────────────────────────────────────────────
        await stage_start(3, "Defining contracts…")
        result_3 = None
        for attempt in range(1, max_retries + 1):
            result_3 = await run_stage_3(outputs["user_plan"], outputs["structure"], attempt, _api_key_getter, llm_options_overrides)
            if result_3["success"]:
                outputs["contracts"] = result_3.get("output") or {}
                if not outputs["contracts"]:
                    raise ValueError("Stage 3 returned empty contracts")
                await stage_complete(3, result_3["output"])
                break
            if attempt == max_retries:
                await stage_error(3, result_3["errors"])
                raise PlannerStageError(stage=3, errors=result_3["errors"])
            await stage_retry(3, "Fixing contracts…")

        # ── STAGE 4 ────────────────────────────────────────────────────────────
        await stage_start(4, "Connecting modules…")
        result_4 = None
        for attempt in range(1, max_retries + 1):
            result_4 = await run_stage_4(outputs["structure"], outputs["contracts"], attempt, _api_key_getter, llm_options_overrides)
            if result_4["success"]:
                outputs["connections"] = result_4.get("output") or {}
                if not outputs["connections"]:
                    raise ValueError("Stage 4 returned empty connections")
                await stage_complete(4, result_4["output"])
                break
            if attempt == max_retries:
                await stage_error(4, result_4["errors"])
                raise PlannerStageError(stage=4, errors=result_4["errors"])
            await stage_retry(4, "Fixing dependencies…")

        # ── STAGE 5 ────────────────────────────────────────────────────────────
        await stage_start(5, "Finalizing project…")
        result_5 = None
        for attempt in range(1, max_retries + 1):
            result_5 = await run_stage_5(outputs, attempt, _api_key_getter, llm_options_overrides)
            if result_5["success"]:
                outputs["safety"] = result_5.get("output") or {}
                if not outputs["safety"]:
                    raise ValueError("Stage 5 returned empty safety output")
                await stage_complete(5, result_5["output"])
                break
            if attempt == max_retries:
                await stage_error(5, result_5["errors"])
                raise PlannerStageError(stage=5, errors=result_5["errors"])
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
            raise ValueError("user_plan missing")
        if not outputs.get("structure"):
            raise ValueError("structure missing")

        await send({"type": "pipeline_complete", "user_plan": outputs["user_plan"], "developer_plan": developer_plan})

        return {
            "user_plan": outputs["user_plan"],
            "developer_plan": developer_plan,
        }

    except PlannerStageError:
        raise
    except Exception as e:
        import traceback
        print(f"[Planner] ❌ Pipeline unexpected failure: {e}")
        print(traceback.format_exc())
        await stage_error(0, [f"Pipeline failure: {str(e)}"])
        raise


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

            result = asyncio.run(
                run_planner_pipeline_core(
                    request, max_retries=self.max_retries
                )
            )
            user_plan = result.get("user_plan", {})
            developer_plan = result.get("developer_plan", {})
            title = self._derive_title(user_plan, request)
            steps = user_plan.get("features", [])
            return {"title": title, "steps": steps, "developer_plan": developer_plan}
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
            title = self._derive_title(user_plan, request)
            steps = user_plan.get("features", [])
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