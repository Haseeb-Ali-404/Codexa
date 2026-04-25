import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from utils.database_models_util import save_message
from utils.file_utils import flatten_structure
from utils.json_parser import parse_json_block
from agents.developer_agent import DeveloperAgent
from agents.planner_agent import PlannerAgent
from agents.debugger_agent import DebuggerAgent
from agents.architecture_agent import ArchitectAgent
from core.agents.planner_agent import FALLBACK_PLAN, run_planner_pipeline_core
from core.factory.agent_factory import build_llm_client_for_agent
from core.providers.base import ChatMessage as LLMChatMessage
from core.validation.dependency_injector import fix_flat_files
from core.agents.integrator_agent import IntegratorAgent


_DEVELOPER_TOTALS_RE = re.compile(
    r"^(?P<tiers>\d+)\s+tiers,\s+(?P<files>\d+)\s+files to generate$"
)
_DEVELOPER_TIER_RE = re.compile(
    r"^Tier\s+(?P<tier>\d+)(?:\s+(?P<parallel>PARALLEL))?:\s*(?P<label>.+)$"
)
_DEVELOPER_ASSEMBLING_RE = re.compile(r"^Assembling\s+(?P<count>\d+)\s+files\.\.\.$")
_DEVELOPER_PROGRESS_RE = re.compile(
    r"^\u2713(?:\s+[^\u2013\u2014-]+)?\s*[\u2013\u2014-]\s*(?P<done>\d+)/(?P<total>\d+)\s+total$"
)
_HTML_DOCUMENT_RE = re.compile(r"<!doctype html>.*?</html>", re.IGNORECASE | re.DOTALL)
_HTML_CODE_FENCE_RE = re.compile(r"```(?:html)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

_SMALL_PROJECT_PROMPT = """
You generate complete small web apps for CODEXA.

Return STRICT JSON only in this format:
{
  "type": "small_project",
  "files": [
    {
      "filename": "index.html",
      "content": "FULL HTML CODE"
    }
  ]
}

Hard requirements:
- Single HTML file only.
- The HTML must include inline <style> and inline <script>.
- No external dependencies, CDN links, imports, or asset URLs.
- Fully working logic. No placeholders. No TODOs.
- The file content must be raw HTML text, never a nested JSON string.
- Responsive premium glassmorphism design with gradients, blur, soft shadows, rounded corners, smooth transitions, and clean typography.
- Make the design feel polished and intentional, not generic: use a strong visual hierarchy, expressive spacing, tasteful motion, hover/focus states, and a cohesive color system.
- Build complete interactions for the requested app, including empty states, keyboard-safe controls where relevant, and realistic UX details that make the app feel demo-ready.
- Prefer visually rich layouts, clear headings, and refined micro-interactions over bare utility output.
- If the user also asks for explanation, ignore the explanation request and generate only the app.
- Output must be production-ready and directly runnable in a browser.
"""


def _apply_flat_to_structure(structure: list, flat_map: dict, base_path: str = "") -> None:
    """Write corrected file contents from flat_map back into the nested structure."""
    for node in structure:
        path = f"{base_path}/{node['name']}".lstrip("/")
        if node["type"] == "file" and path in flat_map:
            node["content"] = flat_map[path]
        elif node["type"] == "folder":
            _apply_flat_to_structure(node.get("children", []), flat_map, path)


def _clean_developer_marker(raw_line: str) -> str:
    text = (raw_line or "").strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    return text


def _initial_planner_pipeline_state() -> dict:
    return {
        "stages": [
            {"stage": n, "status": "idle"}
            for n in (1, 2, 3, 4, 5)
        ],
        "currentStage": 0,
        "isComplete": False,
    }


def _initial_developer_pipeline_state() -> dict:
    return {
        "stages": [
            {"stage": n, "status": "idle"}
            for n in (1, 2, 3, 4, 5)
        ],
        "currentStage": 0,
        "isComplete": False,
        "recentUpdates": [],
    }


def _initial_debugger_pipeline_state() -> dict:
    return {
        "status": "running",
        "currentStep": "Preparing validation",
        "recentUpdates": [],
        "filesProcessed": 0,
        "filesFixed": 0,
        "issuesFound": 0,
        "isComplete": False,
    }


def _append_recent_update(state: dict, message: str | None) -> None:
    text = (message or "").strip()
    if not text:
        return
    updates = list(state.get("recentUpdates") or [])
    updates = [item for item in updates if item != text]
    updates.append(text)
    state["recentUpdates"] = updates[-6:]


def _completed_debugger_pipeline_state(summary: dict, *, files_fixed: int = 0) -> dict:
    state = _initial_debugger_pipeline_state()
    state["status"] = "complete" if summary.get("ok", True) else "warning"
    state["currentStep"] = "Validation complete"
    state["recentUpdates"] = list(summary.get("recent_updates") or [])[-6:]
    state["filesProcessed"] = int(summary.get("files_processed", 0) or 0)
    state["filesFixed"] = int(files_fixed or 0)
    state["issuesFound"] = int(summary.get("issues_found", 0) or 0)
    state["isComplete"] = True
    return state


def _derive_plan_from_outputs(user_message: str, user_plan: dict, developer_plan: dict) -> dict:
    title = (
        (developer_plan.get("title") or "").strip()
        or (user_plan.get("app_name") or "").strip()
        or "Project"
    )
    steps = developer_plan.get("steps") or user_plan.get("features") or []
    return {
        "title": title,
        "steps": steps,
        "developer_plan": developer_plan,
        "user_plan": user_plan,
    }


def _planner_stage_output(pipeline_state: dict, stage_num: int) -> dict:
    for stage in pipeline_state.get("stages") or []:
        if int(stage.get("stage", 0) or 0) == stage_num:
            return dict(stage.get("output") or {})
    return {}


def _planner_fallback_plan_from_tracker(user_message: str, tracker: "_PlannerProgressTracker") -> dict:
    user_plan = _planner_stage_output(tracker.state, 1)
    developer_plan = _planner_stage_output(tracker.state, 2)
    if user_plan or developer_plan:
        return _derive_plan_from_outputs(user_message, user_plan, developer_plan)
    return {
        "title": FALLBACK_PLAN["title"],
        "steps": list(FALLBACK_PLAN["steps"]),
        "developer_plan": {},
        "user_plan": {},
    }


def _completed_developer_pipeline_state(total_files: int) -> dict:
    state = _initial_developer_pipeline_state()
    stage_messages = {
        1: "Planning project structure...",
        2: "Execution plan ready",
        3: f"Generated {total_files} files",
        4: "Workspace assembled and polished",
        5: "Developer output ready",
    }
    state["isComplete"] = True
    state["currentStage"] = 5
    state["totalFiles"] = total_files
    state["completedFiles"] = total_files
    state["recentUpdates"] = ["Developer output delivered successfully"]
    for stage in state["stages"]:
        stage["status"] = "complete"
        stage["message"] = stage_messages.get(stage["stage"])
    return state


class _PlannerProgressTracker:
    def __init__(self) -> None:
        self.state = _initial_planner_pipeline_state()

    def ingest_event(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "stage_start":
            stage_num = int(event.get("stage", 0) or 0)
            message = (event.get("message") or "").strip()
            self.state["currentStage"] = stage_num
            self._set_stage(
                stage_num,
                status="running",
                message=message or None,
            )
            return

        if event_type == "stage_complete":
            stage_num = int(event.get("stage", 0) or 0)
            output = event.get("output") or {}
            self._set_stage(stage_num, status="complete", output=output)
            return

        if event_type == "stage_retry":
            stage_num = int(event.get("stage", 0) or 0)
            message = (event.get("message") or "").strip()
            self._set_stage(
                stage_num,
                status="retrying",
                message=message or None,
            )
            return

        if event_type in ("stage_warning", "stage_error"):
            stage_num = int(event.get("stage", 0) or 0)
            self._set_stage(
                stage_num,
                status="warning",
                warnings=list(event.get("warnings") or event.get("errors") or []),
                errors=list(event.get("warnings") or event.get("errors") or []),
            )
            return

        if event_type == "pipeline_complete":
            self.state["isComplete"] = True
            self.state["userPlan"] = event.get("user_plan") or {}
            self.state["developerPlan"] = event.get("developer_plan") or {}

    def finalize(self, plan_result: dict, user_plan: dict, developer_plan: dict) -> dict:
        self.state["isComplete"] = True
        self.state["userPlan"] = user_plan or {}
        self.state["developerPlan"] = developer_plan or {}
        self.state["planResult"] = {
            "title": plan_result.get("title") or "",
            "steps": list(plan_result.get("steps") or []),
        }
        for stage in self.state["stages"]:
            if stage.get("status") == "idle":
                stage["status"] = "complete"
        if not self.state.get("currentStage"):
            self.state["currentStage"] = 5
        return self.state

    def _set_stage(self, stage_num: int, **updates) -> None:
        for stage in self.state["stages"]:
            if stage["stage"] == stage_num:
                stage.update({k: v for k, v in updates.items() if v is not None})
                break


class _DeveloperProgressTracker:
    """Translate orchestrator progress markers into structured WebSocket events."""

    def __init__(self, websocket) -> None:
        self.websocket = websocket
        self.buffer = ""
        self.started_stages: set[int] = set()
        self.completed_stages: set[int] = set()
        self.total_tiers = 0
        self.total_files = 0
        self.state = _initial_developer_pipeline_state()

    async def stage_start(self, stage: int, message: str, **extra) -> None:
        self.started_stages.add(stage)
        self.state["currentStage"] = stage
        self._set_stage(stage, status="running", message=message)
        self._apply_extra_fields(extra)
        _append_recent_update(self.state, message)
        payload = {"type": "developer_stage_start", "stage": stage, "message": message}
        payload.update({k: v for k, v in extra.items() if v is not None})
        await self.websocket.send_json(payload)

    async def stage_complete(self, stage: int, message: str | None = None, **extra) -> None:
        self.started_stages.add(stage)
        self.completed_stages.add(stage)
        self._set_stage(stage, status="complete", message=message)
        self._apply_extra_fields(extra)
        _append_recent_update(self.state, message)
        payload = {"type": "developer_stage_complete", "stage": stage}
        if message:
            payload["message"] = message
        payload.update({k: v for k, v in extra.items() if v is not None})
        await self.websocket.send_json(payload)

    async def progress(self, message: str | None = None, **extra) -> None:
        self._apply_extra_fields(extra)
        _append_recent_update(self.state, message)
        payload = {"type": "developer_progress"}
        if message:
            payload["message"] = message
        payload.update({k: v for k, v in extra.items() if v is not None})
        await self.websocket.send_json(payload)

    async def ingest(self, chunk: str) -> None:
        if not chunk:
            return
        self.buffer += chunk
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            await self._handle_line(line)

    async def flush(self) -> None:
        if self.buffer.strip():
            await self._handle_line(self.buffer)
        self.buffer = ""

    async def _handle_line(self, raw_line: str) -> None:
        line = _clean_developer_marker(raw_line)
        if not line:
            return

        if line.startswith("Planning structure for:"):
            await self.stage_start(1, "Planning project structure...")
            return

        totals_match = _DEVELOPER_TOTALS_RE.match(line)
        if totals_match:
            self.total_tiers = int(totals_match.group("tiers"))
            self.total_files = int(totals_match.group("files"))
            if 1 not in self.completed_stages:
                await self.stage_complete(1, "Project blueprint ready")
            await self.stage_start(
                2,
                f"Prepared {self.total_tiers} generation tiers",
                total_tiers=self.total_tiers,
                total_files=self.total_files,
            )
            await self.progress(
                message=f"{self.total_files} files queued for generation",
                total_tiers=self.total_tiers,
                total_files=self.total_files,
            )
            return

        tier_match = _DEVELOPER_TIER_RE.match(line)
        if tier_match:
            current_tier = int(tier_match.group("tier"))
            current_batch_label = tier_match.group("label").strip()
            if 2 not in self.completed_stages:
                await self.stage_complete(
                    2,
                    "Execution plan ready",
                    total_tiers=self.total_tiers or None,
                    total_files=self.total_files or None,
                )
            await self.stage_start(
                3,
                f"Generating tier {current_tier} of {self.total_tiers or '?'}",
                current_tier=current_tier,
                total_tiers=self.total_tiers or None,
                total_files=self.total_files or None,
                current_batch_label=current_batch_label,
                is_parallel=bool(tier_match.group("parallel")),
            )
            await self.progress(
                message=current_batch_label,
                current_tier=current_tier,
                total_tiers=self.total_tiers or None,
                total_files=self.total_files or None,
                current_batch_label=current_batch_label,
                is_parallel=bool(tier_match.group("parallel")),
            )
            return

        progress_match = _DEVELOPER_PROGRESS_RE.match(line)
        if progress_match:
            completed_files = int(progress_match.group("done"))
            total_files = int(progress_match.group("total"))
            self.total_files = max(self.total_files, total_files)
            if 3 not in self.started_stages:
                await self.stage_start(
                    3,
                    "Generating project files...",
                    total_files=self.total_files,
                    total_tiers=self.total_tiers or None,
                )
            await self.progress(
                message=line,
                completed_files=completed_files,
                total_files=self.total_files,
                total_tiers=self.total_tiers or None,
            )
            return

        assembling_match = _DEVELOPER_ASSEMBLING_RE.match(line)
        if assembling_match:
            assembled_files = int(assembling_match.group("count"))
            if 3 not in self.completed_stages:
                await self.stage_complete(
                    3,
                    f"Generated {self.total_files or assembled_files} files",
                    completed_files=self.total_files or assembled_files,
                    total_files=self.total_files or assembled_files,
                )
            await self.stage_start(
                4,
                "Assembling final workspace...",
                assembled_files=assembled_files,
                total_files=self.total_files or assembled_files,
            )
            await self.progress(
                message=f"Assembling {assembled_files} files",
                assembled_files=assembled_files,
                total_files=self.total_files or assembled_files,
            )

    def finalize(self, *, delivery_chunks_total: int = 0) -> dict:
        self.state["isComplete"] = True
        if delivery_chunks_total:
            self.state["deliveryChunksTotal"] = delivery_chunks_total
            self.state["deliveryChunksReceived"] = delivery_chunks_total
        if self.total_files:
            self.state["totalFiles"] = self.total_files
            self.state["completedFiles"] = self.total_files
        self.state["currentStage"] = 5
        for stage in self.state["stages"]:
            if stage.get("status") == "idle":
                stage["status"] = "complete"
            if stage["stage"] == 5:
                stage["status"] = "complete"
                stage["message"] = stage.get("message") or "Developer output ready"
        return self.state

    def _set_stage(self, stage_num: int, **updates) -> None:
        for stage in self.state["stages"]:
            if stage["stage"] == stage_num:
                stage.update({k: v for k, v in updates.items() if v is not None})
                break

    def _apply_extra_fields(self, extra: dict) -> None:
        if extra.get("total_tiers") is not None:
            self.state["totalTiers"] = extra["total_tiers"]
        if extra.get("current_tier") is not None:
            self.state["currentTier"] = extra["current_tier"]
        if extra.get("total_files") is not None:
            self.state["totalFiles"] = extra["total_files"]
        if extra.get("completed_files") is not None:
            self.state["completedFiles"] = extra["completed_files"]
        if extra.get("current_batch_label") is not None:
            self.state["currentBatchLabel"] = extra["current_batch_label"]
        if extra.get("assembled_files") is not None:
            self.state["assembledFiles"] = extra["assembled_files"]
        if extra.get("is_parallel") is not None:
            self.state["isParallel"] = extra["is_parallel"]


def _derive_small_project_title(user_message: str) -> str:
    cleaned = " ".join((user_message or "").strip().split())
    if not cleaned:
        return "Small Project"

    trimmed = re.sub(
        r"^(please\s+)?(build|create|make|generate|design|develop|code|recreate|rebuild|regenerate|remake|redo)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    trimmed = re.sub(r"\b(please|again)\b", "", trimmed, flags=re.IGNORECASE)
    trimmed = " ".join(trimmed.split())
    trimmed = trimmed[:60].strip(" .:-")
    if not trimmed:
        trimmed = cleaned[:60].strip(" .:-")

    words = [part for part in re.split(r"\s+", trimmed) if part]
    titled = " ".join(word.capitalize() for word in words[:6])
    return titled or "Small Project"


def _extract_html_document(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    match = _HTML_DOCUMENT_RE.search(text)
    if match:
        return match.group(0).strip()

    for fence in _HTML_CODE_FENCE_RE.finditer(text):
        content = (fence.group(1) or "").strip()
        if "<html" in content.lower() or "<body" in content.lower():
            return content

    if "<html" in text.lower() or "<body" in text.lower():
        return text

    return None


def _ensure_inline_small_project_html(html: str, title: str) -> str:
    content = (html or "").strip()
    if not content:
        content = (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "  <head>\n"
            "    <meta charset=\"UTF-8\" />\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
            f"    <title>{title}</title>\n"
            "    <style>\n"
            "      body { margin: 0; font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; }\n"
            "    </style>\n"
            "  </head>\n"
            "  <body>\n"
            "    <main>Small project</main>\n"
            "    <script>\n"
            "      console.log('Small project ready');\n"
            "    </script>\n"
            "  </body>\n"
            "</html>"
        )

    lowered = content.lower()
    if "<!doctype" not in lowered:
        content = "<!doctype html>\n" + content
        lowered = content.lower()
    if "<html" not in lowered:
        content = (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "  <head>\n"
            "    <meta charset=\"UTF-8\" />\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
            f"    <title>{title}</title>\n"
            "  </head>\n"
            f"  <body>\n{content}\n  </body>\n"
            "</html>"
        )
        lowered = content.lower()
    if "<title>" not in lowered:
        content = content.replace(
            "<head>",
            f"<head>\n    <title>{title}</title>",
            1,
        )
        lowered = content.lower()
    if "<style" not in lowered:
        content = content.replace(
            "</head>",
            "  <style>\n"
            "    :root { color-scheme: dark; }\n"
            "    body { margin: 0; min-height: 100vh; background: linear-gradient(135deg, #0f172a, #111827 45%, #1e293b); }\n"
            "  </style>\n"
            "</head>",
            1,
        )
        lowered = content.lower()
    if "<script" not in lowered:
        content = content.replace(
            "</body>",
            "  <script>\n"
            "    console.log('Small project ready');\n"
            "  </script>\n"
            "</body>",
            1,
        )
    return content.strip()


def _extract_nested_small_project_html(value: Any) -> str | None:
    current: Any = value
    for _ in range(5):
        if isinstance(current, str):
            text = current.strip()
            if not text:
                return None
            html = _extract_html_document(text)
            if html:
                return html
            parsed = parse_json_block(text, default=None)
            if parsed is None:
                try:
                    parsed = json.loads(text)
                except Exception:
                    return None
            current = parsed
            continue

        if isinstance(current, dict):
            current_type = str(current.get("type") or "").strip().lower()
            if current_type == "small_project":
                files = current.get("files")
                if isinstance(files, list):
                    for item in files:
                        if isinstance(item, dict) and str(item.get("content") or "").strip():
                            current = item.get("content")
                            break
                    else:
                        return None
                    continue

            if current_type == "conversation":
                content_blocks = current.get("content")
                if isinstance(content_blocks, list):
                    for block in content_blocks:
                        if not isinstance(block, dict):
                            continue
                        nested_html = _extract_nested_small_project_html(
                            block.get("content")
                        ) or _extract_nested_small_project_html(block.get("value"))
                        if nested_html:
                            return nested_html
                return None

            if str(current.get("content") or "").strip():
                current = current.get("content")
                continue

        return None

    return None


def _coerce_small_project_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value or "")


class _SmallProjectGenerator:
    def __init__(self) -> None:
        self._llm, self._opts = build_llm_client_for_agent("developer")

    def _normalize_payload(self, raw: str, *, title: str) -> dict[str, Any]:
        parsed = parse_json_block(raw, default=None)
        if isinstance(parsed, dict) and str(parsed.get("type") or "").strip().lower() == "small_project":
            files = parsed.get("files")
            if isinstance(files, list):
                normalized_files: list[dict[str, str]] = []
                for item in files:
                    if not isinstance(item, dict):
                        continue
                    filename = str(item.get("filename") or "").strip() or "index.html"
                    raw_content = _coerce_small_project_content(item.get("content"))
                    content = _extract_nested_small_project_html(raw_content) or raw_content
                    if content.strip():
                        normalized_files.append(
                            {
                                "filename": "index.html" if filename.lower().endswith(".html") else "index.html",
                                "content": _ensure_inline_small_project_html(content, title),
                            }
                        )
                if normalized_files:
                    return {"type": "small_project", "files": normalized_files[:1]}

        recovered_html = _extract_nested_small_project_html(parsed if parsed is not None else raw)
        if recovered_html:
            return {
                "type": "small_project",
                "files": [
                    {
                        "filename": "index.html",
                        "content": _ensure_inline_small_project_html(recovered_html, title),
                    }
                ],
            }

        html = _extract_html_document(raw)
        if html:
            return {
                "type": "small_project",
                "files": [
                    {
                        "filename": "index.html",
                        "content": _ensure_inline_small_project_html(html, title),
                    }
                ],
            }

        raise RuntimeError("Small project generator did not return a valid HTML app.")

    def generate(self, user_message: str) -> dict[str, Any]:
        title = _derive_small_project_title(user_message)
        messages = [
            LLMChatMessage(role="system", content=_SMALL_PROJECT_PROMPT),
            LLMChatMessage(
                role="user",
                content=f"User request:\n{user_message}\n\nGenerate the app now.",
            ),
        ]
        result = self._llm.complete(messages, self._opts)
        payload = self._normalize_payload((result.text or "").strip(), title=title)
        html = payload["files"][0]["content"]
        return {
            "type": "small_project",
            "title": title,
            "payload": payload,
            "project": {
                "structure": [
                    {
                        "type": "folder",
                        "name": "frontend",
                        "children": [
                            {
                                "type": "file",
                                "name": "index.html",
                                "content": html,
                            }
                        ],
                    }
                ]
            },
        }


class ProjectPipeline:
    def run_small_project(self, chat_id: str, user_message: str) -> dict[str, Any]:
        generator = _SmallProjectGenerator()
        return generator.generate(user_message)

    def run(self, chat_id: str, user_message: str):
        """Synchronous full pipeline (HTTP /chat)."""
        planner = PlannerAgent()
        plan = planner.plan(user_message)

        if not plan or "steps" not in plan:
            raise RuntimeError("Planner failed")

        planner_pipeline_state = _PlannerProgressTracker().finalize(
            plan,
            plan.get("user_plan") or {},
            plan.get("developer_plan") or {},
        )

        save_message(
            chat_id,
            role="assistant",
            content=json.dumps(plan, indent=2),
            agent="planner",
            pipeline=planner_pipeline_state,
        )

        developer = DeveloperAgent()
        project_json = developer.generate_project(
            plan["title"],
            plan["steps"],
            user_message,
            developer_plan=plan.get("developer_plan"),
        )

        if not project_json or "structure" not in project_json:
            raise RuntimeError("Developer failed")

        # 1. Dep-injector: inject missing npm/pip packages
        _flat = flatten_structure(project_json["structure"])
        _dep_report = fix_flat_files(_flat)
        if _dep_report["npm_injected"] or _dep_report["pip_injected"]:
            print(f"[Pipeline] Dep-injector: npm={_dep_report['npm_injected']} pip={_dep_report['pip_injected']}")
            _flat_map = {f["path"]: f["content"] for f in _flat}
            _apply_flat_to_structure(project_json["structure"], _flat_map)

        # 2. Integrator: fix CORS, auth interceptor, API endpoint mismatches
        try:
            _integrator = IntegratorAgent(verbose=True)
            _int_result = _integrator.fix_project(project_json)
            if _int_result["fixes_applied"]:
                print(f"[Pipeline] Integrator fixes: {_int_result['fixes_applied']}")
        except Exception as _e:
            print(f"[Pipeline] Integrator error (non-fatal): {_e}")

        save_message(
            chat_id,
            role="assistant",
            content="Generated multi-folder full-stack project (JSON too large to display). View in Your Recent Projects.",
            agent="developer",
            developer_pipeline=_completed_developer_pipeline_state(len(_flat)),
        )

        architect = ArchitectAgent()
        debugger = DebuggerAgent(verbose=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            arch_f = pool.submit(
                architect.generate_architecture, project_json, user_message
            )
            dbg_f = pool.submit(debugger.validate_project_json_with_summary, project_json)
            architecture = arch_f.result()
            debugger_summary = dbg_f.result()
            is_valid = bool(debugger_summary.get("ok"))

        save_message(
            chat_id,
            role="assistant",
            content=f"Debugger validation result: {is_valid}",
            agent="validator",
            validation_passed=is_valid,
            debugger_pipeline=_completed_debugger_pipeline_state(debugger_summary),
        )

        save_message(
            chat_id,
            role="assistant",
            content=json.dumps(architecture, indent=2),
            agent="architect",
        )

        return {
            "ok": is_valid,
            "type": "project",
            "chat_id": chat_id,
            "title": plan["title"],
            "plan": plan["steps"],
            "project": project_json,
            "architecture": architecture,
        }

    async def run_pipeline_ws(self, websocket, chat_id: str, user_message: str):
        await websocket.send_json({"type": "planner_start"})

        planner_tracker = _PlannerProgressTracker()

        async def planner_sender(event: dict) -> None:
            planner_tracker.ingest_event(event)
            await websocket.send_json(event)

        try:
            planner_result = await run_planner_pipeline_core(
                user_message,
                event_sender=planner_sender,
            )
            plan = _derive_plan_from_outputs(
                user_message,
                planner_result.get("user_plan") or {},
                planner_result.get("developer_plan") or {},
            )
        except Exception as e:
            print(f"[Pipeline] Planner staged pipeline failed, using fast fallback: {e}")
            plan = _planner_fallback_plan_from_tracker(user_message, planner_tracker)
            planner_tracker.finalize(
                plan,
                plan.get("user_plan") or {},
                plan.get("developer_plan") or {},
            )

        if not plan or "steps" not in plan:
            await websocket.send_json({"type": "error", "message": "Planner failed"})
            return

        planner_pipeline_state = planner_tracker.finalize(
            plan,
            plan.get("user_plan") or {},
            plan.get("developer_plan") or {},
        )

        save_message(
            chat_id,
            role="assistant",
            content=json.dumps(plan, indent=2),
            agent="planner",
            pipeline=planner_pipeline_state,
        )

        await websocket.send_json({"type": "planner_result", "data": plan})

        await websocket.send_json({"type": "developer_start"})
        progress_tracker = _DeveloperProgressTracker(websocket)
        await progress_tracker.stage_start(1, "Planning project structure...")

        developer = DeveloperAgent()
        dev_chunks: list[str] = []
        try:
            async for delta in developer.astream_developer_text(
                plan["title"],
                plan["steps"],
                user_message,
                developer_plan=plan.get("developer_plan"),
            ):
                dev_chunks.append(delta)
                await progress_tracker.ingest(delta)
                await websocket.send_json({"type": "developer_delta", "text": delta})
        except Exception as e:
            print(f"[Pipeline] Developer stream failed, using sync fallback: {e}")
        finally:
            await progress_tracker.flush()

        raw_dev = "".join(dev_chunks).strip()
        try:
            project_json = developer.parse_project_from_raw(raw_dev)
            if not project_json or "structure" not in project_json or not project_json["structure"]:
                raise ValueError("Empty structure from stream parse")
        except Exception as exc:
            print("Developer stream parse failed, non-streaming fallback:", exc)
            project_json = developer.generate_project(
                plan["title"],
                plan["steps"],
                user_message,
                developer_plan=plan.get("developer_plan"),
            )

        if not project_json or "structure" not in project_json:
            await websocket.send_json({"type": "error", "message": "Developer failed"})
            return

        if 3 not in progress_tracker.completed_stages:
            generated_files = progress_tracker.total_files or len(
                flatten_structure(project_json["structure"])
            )
            await progress_tracker.stage_complete(
                3,
                f"Generated {generated_files} files",
                completed_files=generated_files,
                total_files=generated_files,
            )

        if 4 not in progress_tracker.started_stages:
            await progress_tracker.stage_start(
                4,
                "Assembling final workspace...",
                total_files=progress_tracker.total_files or None,
            )

        # 1. Dep-injector
        _flat = flatten_structure(project_json["structure"])
        _dep_report = fix_flat_files(_flat)
        if _dep_report["npm_injected"] or _dep_report["pip_injected"]:
            print(f"[Pipeline-WS] Dep-injector: npm={_dep_report['npm_injected']} pip={_dep_report['pip_injected']}")
            _flat_map = {f["path"]: f["content"] for f in _flat}
            _apply_flat_to_structure(project_json["structure"], _flat_map)

        # 2. Integrator: fix CORS, auth interceptor, API mismatches
        try:
            _integrator = IntegratorAgent(verbose=True)
            _int_result = _integrator.fix_project(project_json)
            if _int_result["fixes_applied"]:
                print(f"[Pipeline-WS] Integrator fixes: {_int_result['fixes_applied']}")
        except Exception as _e:
            print(f"[Pipeline-WS] Integrator error (non-fatal): {_e}")

        await progress_tracker.stage_complete(
            4,
            "Workspace assembled and polished",
            total_files=progress_tracker.total_files or len(_flat),
        )
        await progress_tracker.stage_start(
            5,
            "Packaging project for delivery...",
            total_files=progress_tracker.total_files or len(_flat),
        )

        # Stream project_json in chunks to avoid WebSocket message size limits
        project_str = json.dumps(project_json)
        chunk_size = 50000  # 50KB chunks
        total_chunks = (len(project_str) + chunk_size - 1) // chunk_size
        
        for i in range(0, len(project_str), chunk_size):
            chunk = project_str[i:i + chunk_size]
            await websocket.send_json({
                "type": "developer_result_chunk",
                "chunk_index": i // chunk_size,
                "total_chunks": total_chunks,
                "data": chunk
            })

        await progress_tracker.stage_complete(
            5,
            "Developer output ready",
            total_files=progress_tracker.total_files or len(_flat),
        )
        save_message(
            chat_id,
            role="assistant",
            content="Generated multi-folder full-stack project  (JSON too large to display). View in Your Recent Projects.",
            agent="developer",
            developer_pipeline=progress_tracker.finalize(
                delivery_chunks_total=total_chunks
            ),
        )
        await websocket.send_json({"type": "developer_result_done"})

        await websocket.send_json({"type": "debugger_start"})
        await websocket.send_json({"type": "architect_start"})

        architect = ArchitectAgent()
        debugger = DebuggerAgent(verbose=True)

        await websocket.send_json({
            "type": "debugger_progress",
            "message": "Scanning generated project structure",
        })

        async def run_debugger_summary() -> dict:
            summary = await asyncio.to_thread(
                debugger.validate_project_json_with_summary,
                project_json,
            )
            for update in summary.get("recent_updates") or []:
                await websocket.send_json({
                    "type": "debugger_progress",
                    "message": update,
                    "files_processed": summary.get("files_processed", 0),
                    "issues_found": summary.get("issues_found", 0),
                })
            return summary

        architecture, debugger_summary = await asyncio.gather(
            architect.agenerate_architecture(project_json, user_message),
            run_debugger_summary(),
        )
        is_valid = bool(debugger_summary.get("ok"))

        save_message(
            chat_id,
            role="assistant",
            content=f"Debugger validation result: {is_valid}",
            agent="validator",
            validation_passed=is_valid,
            debugger_pipeline=_completed_debugger_pipeline_state(debugger_summary),
        )

        save_message(
            chat_id,
            role="assistant",
            content=json.dumps(architecture, indent=2),
            agent="architect",
        )

        await websocket.send_json({"type": "architect_result", "data": architecture})
        await websocket.send_json({
            "type": "debugger_result",
            "data": is_valid,
            "summary": debugger_summary,
        })

        return {
            "ok": is_valid,
            "type": "project",
            "chat_id": chat_id,
            "title": plan["title"],
            "plan": plan["steps"],
            "project": project_json,
            "architecture": architecture,
        }
