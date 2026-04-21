import asyncio

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from models.schemas import ChatPayload, ChatRenamePayload
from agents.chat_agent import ChatAgent
from agents.classifier_agent import ClassifierAgent
from agents.edit_agent import EditAgent
from agents.project_pipeline_agent import ProjectPipeline
from utils.database_models_util import (
    create_chat,
    save_message,
    get_user_chats,
    get_chat_messages,
    save_project,
    update_chat_title,
    delete_chat_cascade,
    get_project_by_chat_id,
)
from utils.file_utils import save_files
from core.factory.agent_factory import create_agent
from core.memory.memory_store import get_trimmed_messages
from core.project.project_store import apply_change_record, list_files_for_project
from core.utils.diff_utils import enrich_change_with_diff
from core.utils.usage_logger import chat_id_var


router = APIRouter(prefix="/chat")

chat_agent = ChatAgent()
classifier = ClassifierAgent()
pipeline = ProjectPipeline()
edit_agent = EditAgent()


def _memory_hint_for_edit(chat_id: str) -> str:
    """Compressed conversation history for the EditAgent to resolve follow-ups."""
    turns = get_trimmed_messages(chat_id, max_messages=30)
    recent = turns[-20:]
    lines: list[str] = []
    for m in recent:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if len(content) > 900:
            content = content[:900] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _project_context_for_chat(existing_project: dict | None) -> str:
    """Compact project context string for the ChatAgent so it can answer grounded questions."""
    if not existing_project:
        return ""
    pid = existing_project.get("_id")
    title = (existing_project.get("title") or "Untitled").strip()
    description = (existing_project.get("description") or "").strip()
    try:
        files = list_files_for_project(str(pid))
    except Exception:
        files = []

    manifest_lines: list[str] = []
    for f in files[:80]:  # cap to keep prompt small
        path = (f.get("path") or "").strip()
        if path:
            manifest_lines.append(f"- {path}")
    more = max(0, len(files) - len(manifest_lines))

    parts = [f"Project title: {title}"]
    if description:
        parts.append(f"User's original request: {description[:400]}")
    if manifest_lines:
        manifest = "\n".join(manifest_lines)
        if more:
            manifest += f"\n(+{more} more files)"
        parts.append("File manifest:\n" + manifest)
    else:
        parts.append("File manifest: (empty)")
    return "\n\n".join(parts)


def run_code_edit(
    project_id: str,
    chat_id: str,
    user_message: str,
) -> dict:
    """
    LLM proposes file edits; apply to DB; return summary + enriched changes.
    """
    files = list_files_for_project(project_id)
    hint = _memory_hint_for_edit(chat_id)
    result = edit_agent.run(project_id, files, user_message, hint)
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error", "Edit failed"),
            "summary": "",
            "changes": [],
        }
    applied = []
    for ch in result.get("changes") or []:
        rec = apply_change_record(project_id, ch, chat_id=chat_id)
        if not rec.get("ok"):
            continue
        payload = {
            "file": rec.get("file"),
            "type": rec.get("type", "modify"),
            "before": rec.get("before", ""),
            "after": rec.get("after", ""),
        }
        applied.append(enrich_change_with_diff(payload))
    summary = (result.get("summary") or "").strip() or (
        f"Applied updates to {len(applied)} file(s)."
        if applied
        else "No file changes applied."
    )
    return {"ok": True, "summary": summary, "changes": applied}


def get_title_from_message(message: str) -> str:
    """Fast rule-based title generation - no LLM call needed."""
    # Remove extra whitespace and truncate to first 40 chars
    clean = message.strip().replace("\n", " ")
    if len(clean) <= 40:
        return clean
    return clean[:37] + "..."


@router.post("/")
def chat(payload: ChatPayload):

    user_message = payload.message.strip()
    user_id = payload.user_id
    chat_id = payload.chat_id
    # print("Received chat payload:", payload)
    # ---------- Create new project if none exists ----------
    if not chat_id:
        chat_id = create_chat(
            user_id=user_id,
            title=get_title_from_message(user_message),
            description=user_message
        )

    chat_id_var.set(chat_id)

    # ---------- Save User Message ----------
    save_message(chat_id, "user", user_message)

    existing_project = get_project_by_chat_id(chat_id)
    has_project = existing_project is not None

    # ---------- Classify Intent ----------
    intent = classifier.classify_for_project(
        user_message, chat_id, has_project=has_project
    )
    print("Classified Intent:", intent)
    # ---------- PROJECT PIPELINE ----------
    if intent["type"] == "project":
        
        pipeline_result = pipeline.run(chat_id, user_message)
        print("Pipeline Result:", pipeline_result)
        # Store final message returned to the frontend
        final_reply = "Project Creation completed successfully."

        save_message(
            chat_id,
            role="assistant",
            content=final_reply,
            agent="pipeline"
        )

        project_id = save_project(
            user_id=user_id,
            title=pipeline_result["title"],
            description=user_message,
            chat_id=chat_id,
            plan = pipeline_result["plan"],
        )
        update_chat_title(chat_id, user_id, pipeline_result["title"])

        project_json = pipeline_result["project"]
        save_files(
            project_id=project_id,
            structure=project_json["structure"]
        )

        return {
            "ok": True,
            "type": "project",
            "chat_id": chat_id,
            "project_id": project_id,
            "title": pipeline_result["title"],
            "reply": final_reply,
        }

    # ---------- CODE EDIT (existing project) ----------
    if intent.get("type") == "edit" and existing_project:
        pid = existing_project["_id"]
        edit_out = run_code_edit(pid, chat_id, user_message)
        if not edit_out["ok"]:
            save_message(chat_id, "assistant", edit_out.get("error", "Edit failed"), "edit")
            return {
                "ok": False,
                "type": "edit",
                "chat_id": chat_id,
                "project_id": pid,
                "reply": edit_out.get("error", "Edit failed"),
                "changes": [],
                "messages": get_chat_messages(chat_id),
            }
        save_message(chat_id, "assistant", edit_out["summary"], "edit")
        return {
            "ok": True,
            "type": "edit",
            "chat_id": chat_id,
            "project_id": pid,
            "reply": edit_out["summary"],
            "changes": edit_out["changes"],
            "messages": get_chat_messages(chat_id),
        }

    # ---------- CONVERSATIONAL MODE ----------
    project_context = _project_context_for_chat(existing_project)
    reply = chat_agent.respond(chat_id, user_message, project_context=project_context)

    return {
        "ok": True,
        "type": "conversation",
        "chat_id": chat_id,
        "reply": reply,
        "messages": get_chat_messages(chat_id)
    }



@router.get("/{chat_id}")
def get_chat_history(chat_id: str):
    """
    Fetch all chat messages for a specific project.
    """
    messages = get_chat_messages(chat_id)

    if messages is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "ok": True,
        "chat_id": chat_id,
        "messages": messages
    }


@router.get("/get-chats/{user_id}")
def get_user_all_chats(user_id: str):
    """
    Fetch all chats for a specific user.
    """
    chats = get_user_chats(user_id)

    return {
        "ok": True,
        "user_id": user_id,
        "chats": chats
    }


@router.patch("/{chat_id}")
def rename_chat(chat_id: str, body: ChatRenamePayload):
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if not update_chat_title(chat_id, body.user_id, title):
        raise HTTPException(status_code=404, detail="Chat not found or access denied")
    return {"ok": True, "chat_id": chat_id, "title": title}


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, user_id: str = Query(..., description="Owner user id")):
    if not delete_chat_cascade(chat_id, user_id):
        raise HTTPException(status_code=404, detail="Chat not found or access denied")
    return {"ok": True, "chat_id": chat_id}


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()

    try:
        # ✅ receive ONLY ONCE
        data = await websocket.receive_json()

        chat_id = data.get("chat_id")
        user_id = data.get("user_id")
        raw_message = (data.get("message") or "").strip()
        attachments = data.get("attachments") or []
        if not isinstance(attachments, list):
            attachments = []

        names = []
        for a in attachments:
            if isinstance(a, dict):
                nm = (a.get("name") or "file").strip()
                if nm:
                    names.append(nm)

        if names:
            note = f"[Attached: {', '.join(names)}]"
            message = f"{raw_message}\n\n{note}" if raw_message else note
        else:
            message = raw_message

        if not message:
            message = "User sent a message."

        if not chat_id:
            chat_id = create_chat(
                user_id=user_id,
                title=get_title_from_message(message),
                description=message
            )

        chat_id_var.set(chat_id)

        save_message(chat_id, "user", message)
        existing_project = get_project_by_chat_id(chat_id)
        has_project = existing_project is not None
        intent = classifier.classify_for_project(
            message, chat_id, has_project=has_project
        )
        print("Classified Intent:", intent)

        # PROJECT MODE
        if intent["type"] == "project":
            pipeline = ProjectPipeline()
            pipeline_result = await pipeline.run_pipeline_ws(websocket, chat_id, message)

            final_reply = "Project Creation completed successfully."
            save_message(
                chat_id,
                role="assistant",
                content=final_reply,
                agent="pipeline",
            )

            project_id = save_project(
                user_id=user_id,
                title=pipeline_result["title"],
                description=message,
                chat_id=chat_id,
                plan=pipeline_result["plan"],
            )

            update_chat_title(chat_id, user_id, pipeline_result["title"])

            project_json = pipeline_result["project"]
            save_files(
                project_id=project_id,
                structure=project_json["structure"],
            )
            await websocket.send_json({
                "type": "done",
                "new_project_id": project_id,
                "chat_title": pipeline_result["title"],
            })
            print(f"New Project ID: {project_id}")

        # CODE EDIT — stream structured file updates
        elif intent.get("type") == "edit" and existing_project:
            pid = existing_project["_id"]
            await websocket.send_json(
                {"type": "edit_start", "chat_id": chat_id, "project_id": pid}
            )
            edit_out = await asyncio.to_thread(run_code_edit, pid, chat_id, message)
            if not edit_out["ok"]:
                err = edit_out.get("error", "Edit failed")
                save_message(chat_id, "assistant", err, "edit")
                await websocket.send_json({"type": "error", "message": err})
            else:
                for ch in edit_out.get("changes") or []:
                    await websocket.send_json({"type": "edit_file", "change": ch})
                save_message(chat_id, "assistant", edit_out["summary"], "edit")
                await websocket.send_json(
                    {
                        "type": "edit_done",
                        "ok": True,
                        "chat_id": chat_id,
                        "project_id": pid,
                        "summary": edit_out["summary"],
                        "changes": edit_out["changes"],
                    }
                )

        # CONVERSATIONAL MODE — stream tokens like Cursor / ChatGPT
        else:
            await websocket.send_json(
                {
                    "type": "conversation_start",
                    "ok": True,
                    "chat_id": chat_id,
                }
            )
            try:
                project_context = _project_context_for_chat(existing_project)
                async for piece in chat_agent.stream_respond(
                    chat_id, message, project_context=project_context
                ):
                    if piece:
                        await websocket.send_json(
                            {
                                "type": "conversation_delta",
                                "text": piece,
                            }
                        )
                await websocket.send_json(
                    {
                        "type": "conversation_done",
                        "ok": True,
                        "chat_id": chat_id,
                    }
                )
            except Exception as stream_err:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": str(stream_err),
                    }
                )

        await websocket.close()
        
    except WebSocketDisconnect:
        print("❌ Client disconnected safely")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })