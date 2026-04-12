import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

from utils.database_models_util import save_message
from agents.developer_agent import DeveloperAgent
from agents.planner_agent import PlannerAgent
from agents.debugger_agent import DebuggerAgent
from agents.architecture_agent import ArchitectAgent


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
        async for delta in planner.astream_plan_text(user_message):
            plan_chunks.append(delta)
            await websocket.send_json({"type": "planner_delta", "text": delta})

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
        async for delta in developer.astream_developer_text(
            plan["title"],
            plan["steps"],
            user_message,
        ):
            dev_chunks.append(delta)
            await websocket.send_json({"type": "developer_delta", "text": delta})

        raw_dev = "".join(dev_chunks).strip()
        try:
            project_json = developer.parse_project_from_raw(raw_dev)
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

        save_message(
            chat_id,
            role="assistant",
            content="Generated multi-folder full-stack project  (JSON too large to display). View in Your Recent Projects.",
            agent="developer",
        )

        await websocket.send_json({"type": "developer_result", "data": project_json})

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
