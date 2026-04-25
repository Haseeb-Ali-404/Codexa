import asyncio
import json

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


def _small_project_message_content(payload: dict) -> str:
    files = payload.get("files") if isinstance(payload, dict) else None
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "").strip().lower()
            content = str(item.get("content") or "")
            if filename == "index.html" and content.strip():
                return content
        for item in files:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            if content.strip():
                return content
    return json.dumps(payload, ensure_ascii=False)


def _clip_message(text: str, limit: int = 90) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _chat_log(message: str) -> None:
    print(f"[Chat] {message}", flush=True)


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
    _chat_log(
        f"HTTP request chat_id={chat_id} has_project={has_project} msg='{_clip_message(user_message)}'"
    )

    # ---------- Classify Intent ----------
    intent = classifier.classify_for_project(
        user_message, chat_id, has_project=has_project
    )
    _chat_log(
        f"HTTP classified chat_id={chat_id} type={intent.get('type')} reason={intent.get('reason')}"
    )
    # ---------- PROJECT PIPELINE ----------
    if intent["type"] == "project":
        _chat_log(f"HTTP project pipeline started chat_id={chat_id}")
        pipeline_result = pipeline.run(chat_id, user_message)
        _chat_log(
            f"HTTP project pipeline finished chat_id={chat_id} title='{pipeline_result.get('title', '')}'"
        )
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
        _chat_log(f"HTTP project saved chat_id={chat_id} project_id={project_id}")

        return {
            "ok": True,
            "type": "project",
            "chat_id": chat_id,
            "project_id": project_id,
            "title": pipeline_result["title"],
            "reply": final_reply,
        }

    if intent["type"] == "small_project":
        _chat_log(f"HTTP small project generation started chat_id={chat_id}")
        small_project_result = pipeline.run_small_project(chat_id, user_message)
        project_id = save_project(
            user_id=user_id,
            title=small_project_result["title"],
            description=user_message,
            chat_id=chat_id,
            plan=None,
            project_type="small_project",
        )
        update_chat_title(chat_id, user_id, small_project_result["title"])
        save_files(
            project_id=project_id,
            structure=small_project_result["project"]["structure"]
        )
        save_message(
            chat_id,
            role="assistant",
            content=_small_project_message_content(small_project_result["payload"]),
            agent="chat",
            project_id=project_id,
        )
        _chat_log(
            f"HTTP small project saved chat_id={chat_id} project_id={project_id} title='{small_project_result.get('title', '')}'"
        )

        return {
            "ok": True,
            "type": "small_project",
            "chat_id": chat_id,
            "project_id": project_id,
            "title": small_project_result["title"],
            "reply": _small_project_message_content(small_project_result["payload"]),
            "messages": get_chat_messages(chat_id)
        }

    # ---------- CODE EDIT (existing project) ----------
    if intent.get("type") == "edit" and existing_project:
        pid = existing_project["_id"]
        _chat_log(f"HTTP edit started chat_id={chat_id} project_id={pid}")
        edit_out = run_code_edit(pid, chat_id, user_message)
        if not edit_out["ok"]:
            _chat_log(f"HTTP edit failed chat_id={chat_id} project_id={pid} err='{_clip_message(edit_out.get('error', 'Edit failed'))}'")
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
        _chat_log(
            f"HTTP edit completed chat_id={chat_id} project_id={pid} changes={len(edit_out.get('changes') or [])}"
        )
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
    _chat_log(f"HTTP conversation started chat_id={chat_id}")
    reply = chat_agent.respond(chat_id, user_message, project_context=project_context)
    _chat_log(f"HTTP conversation completed chat_id={chat_id}")

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
        _chat_log(
            f"WS request chat_id={chat_id} has_project={has_project} attachments={len(attachments)} msg='{_clip_message(message)}'"
        )
        intent = classifier.classify_for_project(
            message, chat_id, has_project=has_project
        )
        _chat_log(
            f"WS classified chat_id={chat_id} type={intent.get('type')} reason={intent.get('reason')}"
        )

        # PROJECT MODE
        if intent["type"] == "project":
            _chat_log(f"WS project pipeline started chat_id={chat_id}")
            pipeline_result = await ProjectPipeline().run_pipeline_ws(websocket, chat_id, message)

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
            _chat_log(f"WS project saved chat_id={chat_id} project_id={project_id}")

        elif intent["type"] == "small_project":
            _chat_log(f"WS small project generation started chat_id={chat_id}")
            await websocket.send_json(
                {
                    "type": "small_project_start",
                    "ok": True,
                    "chat_id": chat_id,
                }
            )
            small_project_result = await asyncio.to_thread(
                pipeline.run_small_project,
                chat_id,
                message,
            )

            project_id = save_project(
                user_id=user_id,
                title=small_project_result["title"],
                description=message,
                chat_id=chat_id,
                plan=None,
                project_type="small_project",
            )
            update_chat_title(chat_id, user_id, small_project_result["title"])
            save_files(
                project_id=project_id,
                structure=small_project_result["project"]["structure"],
            )
            save_message(
                chat_id,
                role="assistant",
                content=_small_project_message_content(small_project_result["payload"]),
                agent="chat",
                project_id=project_id,
            )
            await websocket.send_json(
                {
                    "type": "small_project_done",
                    "ok": True,
                    "chat_id": chat_id,
                    "new_project_id": project_id,
                    "chat_title": small_project_result["title"],
                    "payload": small_project_result["payload"],
                }
            )
            _chat_log(f"WS small project saved chat_id={chat_id} project_id={project_id}")

        # CODE EDIT — stream structured file updates
        elif intent.get("type") == "edit" and existing_project:
            pid = existing_project["_id"]
            _chat_log(f"WS edit started chat_id={chat_id} project_id={pid}")
            await websocket.send_json(
                {"type": "edit_start", "chat_id": chat_id, "project_id": pid}
            )
            edit_out = await asyncio.to_thread(run_code_edit, pid, chat_id, message)
            if not edit_out["ok"]:
                err = edit_out.get("error", "Edit failed")
                _chat_log(f"WS edit failed chat_id={chat_id} project_id={pid} err='{_clip_message(err)}'")
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
                _chat_log(
                    f"WS edit completed chat_id={chat_id} project_id={pid} changes={len(edit_out.get('changes') or [])}"
                )

        # CONVERSATIONAL MODE — stream tokens like Cursor / ChatGPT
        else:
            _chat_log(f"WS conversation started chat_id={chat_id}")
            await websocket.send_json(
                {
                    "type": "conversation_start",
                    "ok": True,
                    "chat_id": chat_id,
                }
            )
            try:
                project_context = _project_context_for_chat(existing_project)
                payload = await chat_agent.generate_structured_payload(
                    chat_id,
                    message,
                    project_context=project_context,
                )
                stream_text = chat_agent.payload_to_stream_text(payload)
                if stream_text:
                    await websocket.send_json(
                        {
                            "type": "conversation_delta",
                            "text": stream_text,
                        }
                    )
                await websocket.send_json(
                    {
                        "type": "conversation_structured",
                        "payload": payload,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "conversation_done",
                        "ok": True,
                        "chat_id": chat_id,
                    }
                )
                _chat_log(f"WS conversation completed chat_id={chat_id}")
            except Exception as stream_err:
                _chat_log(f"WS conversation failed chat_id={chat_id} err='{_clip_message(str(stream_err))}'")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": str(stream_err),
                    }
                )

        await websocket.close()
        
    except WebSocketDisconnect:
        _chat_log("WS client disconnected safely")
    except Exception as e:
        _chat_log(f"WS error err='{_clip_message(str(e))}'")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
