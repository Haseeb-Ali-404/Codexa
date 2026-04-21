import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

from utils.database_models_util import save_message
from utils.file_utils import flatten_structure
from agents.developer_agent import DeveloperAgent
from agents.planner_agent import PlannerAgent
from agents.debugger_agent import DebuggerAgent
from agents.architecture_agent import ArchitectAgent
from core.validation.dependency_injector import fix_flat_files
from core.agents.integrator_agent import IntegratorAgent


def _apply_flat_to_structure(structure: list, flat_map: dict, base_path: str = "") -> None:
    """Write corrected file contents from flat_map back into the nested structure."""
    for node in structure:
        path = f"{base_path}/{node['name']}".lstrip("/")
        if node["type"] == "file" and path in flat_map:
            node["content"] = flat_map[path]
        elif node["type"] == "folder":
            _apply_flat_to_structure(node.get("children", []), flat_map, path)


class ProjectPipeline:
    def run(self, chat_id: str, user_message: str):
        """Synchronous full pipeline (HTTP /chat)."""
        planner = PlannerAgent()
        plan = planner.plan(user_message)

        if not plan or "steps" not in plan:
            raise RuntimeError("Planner failed")

        save_message(
            chat_id,
            role="assistant",
            content=json.dumps(plan, indent=2),
            agent="planner",
        )

        developer = DeveloperAgent()
        project_json = developer.generate_project(
            plan["title"],
            plan["steps"],
            user_message,
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
        )

        architect = ArchitectAgent()
        debugger = DebuggerAgent(verbose=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            arch_f = pool.submit(
                architect.generate_architecture, project_json, user_message
            )
            dbg_f = pool.submit(debugger.validate, project_json)
            architecture = arch_f.result()
            is_valid = dbg_f.result()

        save_message(
            chat_id,
            role="assistant",
            content=f"Debugger validation result: {is_valid}",
            agent="debugger",
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

        planner = PlannerAgent()
        plan_chunks: list[str] = []
        
        try:
            async for delta in planner.astream_plan_text(user_message):
                plan_chunks.append(delta)
                await websocket.send_json({"type": "planner_delta", "text": delta})
        except Exception as e:
            print(f"[Pipeline] Planner stream failed, using sync fallback: {e}")
        
        raw_plan = "".join(plan_chunks).strip()
        plan = planner.parse_plan_from_raw(raw_plan)
        if not plan:
            plan = planner.plan(user_message)

        if not plan or "steps" not in plan:
            await websocket.send_json({"type": "error", "message": "Planner failed"})
            return

        save_message(
            chat_id,
            role="assistant",
            content=json.dumps(plan, indent=2),
            agent="planner",
        )

        await websocket.send_json({"type": "planner_result", "data": plan})

        await websocket.send_json({"type": "developer_start"})

        developer = DeveloperAgent()
        dev_chunks: list[str] = []
        try:
            async for delta in developer.astream_developer_text(
                plan["title"],
                plan["steps"],
                user_message,
            ):
                dev_chunks.append(delta)
                await websocket.send_json({"type": "developer_delta", "text": delta})
        except Exception as e:
            print(f"[Pipeline] Developer stream failed, using sync fallback: {e}")

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
            )

        if not project_json or "structure" not in project_json:
            await websocket.send_json({"type": "error", "message": "Developer failed"})
            return

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

        save_message(
            chat_id,
            role="assistant",
            content="Generated multi-folder full-stack project  (JSON too large to display). View in Your Recent Projects.",
            agent="developer",
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
        
        await websocket.send_json({"type": "developer_result_done"})

        await websocket.send_json({"type": "debugger_start"})
        await websocket.send_json({"type": "architect_start"})

        architect = ArchitectAgent()
        debugger = DebuggerAgent(verbose=True)

        architecture, is_valid = await asyncio.gather(
            architect.agenerate_architecture(project_json, user_message),
            asyncio.to_thread(debugger.validate, project_json),
        )

        save_message(
            chat_id,
            role="assistant",
            content=f"Debugger validation result: {is_valid}",
            agent="debugger",
        )

        save_message(
            chat_id,
            role="assistant",
            content=json.dumps(architecture, indent=2),
            agent="architect",
        )

        await websocket.send_json({"type": "architect_result", "data": architecture})
        await websocket.send_json({"type": "debugger_result", "data": is_valid})

        return {
            "ok": is_valid,
            "type": "project",
            "chat_id": chat_id,
            "title": plan["title"],
            "plan": plan["steps"],
            "project": project_json,
            "architecture": architecture,
        }
