import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor

from utils.database_models_util import save_message
from utils.file_utils import flatten_structure
from agents.developer_agent import DeveloperAgent
from agents.planner_agent import PlannerAgent
from agents.debugger_agent import DebuggerAgent
from agents.architecture_agent import ArchitectAgent
from core.agents.planner_agent import FALLBACK_PLAN, run_planner_pipeline_core
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


class ProjectPipeline:
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
