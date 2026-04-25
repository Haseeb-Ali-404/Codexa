from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from openai import OpenAI

from services.visual_service import (
    absolute_storage_path,
    build_project_context,
    fingerprint_project_context,
    project_storage_dir,
    relative_storage_path,
)
from utils.ai_client_util import get_gemini_client
from utils.database_models_util import list_project_assets, upsert_project_asset
from utils.json_parser import parse_json_block
from utils.plantuml import DEFAULT_PLANTUML_SERVER, ensure_wrapped_plantuml, render_plantuml_png_file


UML_DIAGRAM_TYPES = (
    "use_case",
    "class",
    "sequence",
    "component",
    "deployment",
    "activity"
)


def _complete_json(prompt: str) -> dict[str, Any] | None:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            client = get_gemini_client()
            model = os.getenv("CODEXA_DOC_MODEL", "gemini-2.5-flash")
            response = client.models.generate_content(model=model, contents=prompt)
            parsed = parse_json_block(getattr(response, "text", "") or "", default=None)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            print("UMLService Gemini fallback:", exc)

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            model = os.getenv("CODEXA_DOC_OPENAI_MODEL", "gpt-4.1-mini")
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "Return strict JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content or ""
            parsed = parse_json_block(text, default=None)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            print("UMLService OpenAI fallback:", exc)
    return None


class UMLService:
    def __init__(self, server_url: str | None = None) -> None:
        self.server_url = server_url or os.getenv("PLANTUML_SERVER_URL", DEFAULT_PLANTUML_SERVER)

    def generate_uml(
        self,
        project_id: str,
        *,
        project_description: str | None = None,
        diagram_types: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        requested = self._normalize_types(diagram_types)
        context = build_project_context(project_id, override_description=project_description)
        source_hash = fingerprint_project_context(context, extra={"diagram_types": requested})

        cached = self._get_cached_assets(project_id, requested, source_hash)
        if cached and not force:
            return {"cached": True, "source_hash": source_hash, "diagrams": cached, "context": context}

        diagram_sources = self._build_diagram_sources(context, requested)
        rendered = self.render_uml_images(project_id, diagram_sources, source_hash=source_hash)
        return {"cached": False, "source_hash": source_hash, "diagrams": rendered, "context": context}

    def render_uml_images(
        self,
        project_id: str,
        diagrams: dict[str, str],
        *,
        source_hash: str,
    ) -> list[dict[str, str]]:
        uml_dir = project_storage_dir(project_id, "uml")

        def render_one(item: tuple[str, str]) -> dict[str, str] | None:
            try:
                diagram_type, code = item
                output_path = uml_dir / f"{diagram_type}.png"
                render_plantuml_png_file(
                    code,
                    output_path,
                    server_url=self.server_url,
                    title=diagram_type.replace("_", " ").title(),
                )
                relative_path = relative_storage_path(output_path)
                upsert_project_asset(
                    project_id,
                    "uml",
                    relative_path,
                    diagram_type=diagram_type,
                    source_hash=source_hash,
                    meta={
                        "line_count": len(code.splitlines()),
                        "rendered_with": "plantuml",
                    },
                )
                return {"diagram_type": diagram_type, "file_path": relative_path}
            except Exception as e:
                print(f"UMLService: Error rendering {item[0]} diagram: {e}")
                return None

        with ThreadPoolExecutor(max_workers=max(1, min(len(diagrams), 4))) as executor:
            results = [r for r in executor.map(render_one, diagrams.items()) if r is not None]

        order = {name: index for index, name in enumerate(UML_DIAGRAM_TYPES)}
        return sorted(results, key=lambda item: order.get(item["diagram_type"], 999))

    def _get_cached_assets(
        self,
        project_id: str,
        diagram_types: list[str],
        source_hash: str,
    ) -> list[dict[str, str]]:
        docs = list_project_assets(project_id, asset_type="uml")
        by_type: dict[str, dict[str, str]] = {}
        for doc in docs:
            if doc.get("source_hash") != source_hash:
                continue
            file_path = (doc.get("file_path") or "").strip()
            diagram_type = (doc.get("diagram_type") or "").strip()
            if not file_path or not diagram_type:
                continue
            if absolute_storage_path(file_path).exists():
                by_type[diagram_type] = {"diagram_type": diagram_type, "file_path": file_path}

        if any(diagram_type not in by_type for diagram_type in diagram_types):
            return []

        order = {name: index for index, name in enumerate(UML_DIAGRAM_TYPES)}
        return sorted((by_type[name] for name in diagram_types), key=lambda item: order.get(item["diagram_type"], 999))

    def _normalize_types(self, diagram_types: list[str] | None) -> list[str]:
        if not diagram_types:
            return list(UML_DIAGRAM_TYPES)
        normalized: list[str] = []
        for item in diagram_types:
            value = (item or "").strip().lower().replace("-", "_")
            if value in UML_DIAGRAM_TYPES and value not in normalized:
                normalized.append(value)
        return normalized or list(UML_DIAGRAM_TYPES)

    def _build_diagram_sources(
        self,
        context: dict[str, Any],
        requested: list[str],
    ) -> dict[str, str]:
        fallback = self._fallback_diagrams(context)
        prompt = self._uml_prompt(context, requested)
        ai_payload = _complete_json(prompt) or {}

        diagrams: dict[str, str] = {}
        for diagram_type in requested:
            raw_value = ai_payload.get(diagram_type)
            if isinstance(raw_value, dict):
                raw_value = raw_value.get("code") or raw_value.get("plantuml")
            source = raw_value if isinstance(raw_value, str) and raw_value.strip() else fallback[diagram_type]
            diagrams[diagram_type] = ensure_wrapped_plantuml(source, diagram_type)
        return diagrams

    def _uml_prompt(self, context: dict[str, Any], requested: list[str]) -> str:
        summary = {
            "title": context.get("title"),
            "description": context.get("description"),
            "tech_stack": context.get("tech_stack"),
            "features": context.get("features"),
            "architecture_components": context.get("architecture_components"),
            "workflow_steps": context.get("workflow_steps"),
            "key_files": context.get("key_files"),
        }
        return (
            "You are generating PlantUML diagrams for a software project.\n"
            "Return strict JSON where each key is one requested diagram type and each value is valid complete PlantUML code.\n"
            "Use concise but realistic software architecture naming.\n"
            "Keep diagrams monochrome-friendly and structurally correct.\n"
            f"Requested diagram types: {requested}\n"
            f"Project context: {summary}\n"
        )

    def _fallback_diagrams(self, context: dict[str, Any]) -> dict[str, str]:
        title = context.get("title") or "Project"
        components = context.get("architecture_components") or ["Client Interface", "Application API", "Data Store"]
        features = context.get("features") or ["Project request handling", "Asset generation", "Preview delivery"]
        workflow = context.get("workflow_steps") or [
            "User submits request",
            "System plans the work",
            "Services generate the output",
            "Result is reviewed and delivered",
        ]
        tech = context.get("tech_stack") or ["Frontend UI", "Python Backend", "Storage"]

        use_case_body = "\n".join(f'  usecase "{feature}" as UC{index + 1}' for index, feature in enumerate(features[:4]))
        use_case_links = "\n".join(f"  User --> UC{index + 1}" for index, _ in enumerate(features[:4]))

        class_members = "\n".join(
            f"class {component.replace(' ', '')} {{\n  +status\n  +execute()\n}}\n"
            for component in components[:4]
        )
        class_links = "\n".join(
            f"{components[index].replace(' ', '')} --> {components[index + 1].replace(' ', '')}"
            for index in range(max(0, min(len(components), 4) - 1))
        )

        sequence_steps = []
        actors = ["User", "Client", "API", "Services", "Storage"]
        for index, step in enumerate(workflow[:4]):
            source = actors[index]
            target = actors[min(index + 1, len(actors) - 1)]
            sequence_steps.append(f"{source} -> {target}: {step}")
            sequence_steps.append(f"{target} --> {source}: acknowledgement")

        component_boxes = "\n".join(f'[{component}]' for component in components[:5])
        component_links = "\n".join(
            f'[{components[index]}] --> [{components[index + 1]}]'
            for index in range(max(0, min(len(components), 5) - 1))
        )

        deployment_nodes = "\n".join(
            [
                'node "Client Browser" as browser { [Frontend App] }',
                'node "Application Host" as host { [API Service] [Worker Services] }',
                'database "Project Storage" as db',
                'cloud "LLM Provider" as llm',
                "browser --> host",
                "host --> db",
                "host --> llm",
            ]
        )

        return {
            "use_case": "\n".join(
                [
                    "@startuml",
                    f'title {title} Use Cases',
                    "left to right direction",
                    "actor User",
                    use_case_body,
                    use_case_links,
                    "@enduml",
                ]
            ),
            "class": "\n".join(
                [
                    "@startuml",
                    f"title {title} Class View",
                    class_members,
                    class_links,
                    "@enduml",
                ]
            ),
            "sequence": "\n".join(
                [
                    "@startuml",
                    f"title {title} Workflow Sequence",
                    "actor User",
                    "participant Client",
                    "participant API",
                    "participant Services",
                    "database Storage",
                    *sequence_steps,
                    "@enduml",
                ]
            ),
            "component": "\n".join(
                [
                    "@startuml",
                    f"title {title} Components",
                    component_boxes,
                    component_links,
                    "\n".join(f'[{item}] --> [Project Platform]' for item in tech[:2]),
                    "@enduml",
                ]
            ),
            "deployment": "\n".join(
                [
                    "@startuml",
                    f"title {title} Deployment",
                    deployment_nodes,
                    "@enduml",
                ]
            ),
        }


default_uml_service = UMLService()
