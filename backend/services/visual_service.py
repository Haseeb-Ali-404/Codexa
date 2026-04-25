from __future__ import annotations

import hashlib
import json
import os
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from core.project.project_store import list_files_for_project
from utils.database_models_util import get_project_by_id, list_project_assets


BG = (8, 11, 20)
BG_ELEVATED = (15, 23, 42)
INK = (241, 245, 249)
MUTED = (148, 163, 184)
ACCENT = (96, 165, 250)
ACCENT_SOFT = (56, 189, 248)


def storage_root() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    root = Path(os.getenv("CODEXA_STORAGE_ROOT", repo_root / "storage"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_storage_dir(project_id: str, bucket: str) -> Path:
    target = storage_root() / "projects" / project_id / bucket
    target.mkdir(parents=True, exist_ok=True)
    return target


def relative_storage_path(path: str | Path) -> str:
    return Path(path).resolve().relative_to(storage_root().resolve()).as_posix()


def absolute_storage_path(relative_path: str) -> Path:
    return storage_root() / relative_path


def _truncate(text: str, limit: int = 220) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _parse_package_json_deps(files: list[dict[str, Any]]) -> set[str]:
    deps: set[str] = set()
    for file in files:
        path = (file.get("path") or "").lower()
        if not path.endswith("package.json"):
            continue
        try:
            payload = json.loads(file.get("content") or "{}")
        except Exception:
            continue
        for group in ("dependencies", "devDependencies"):
            deps.update((payload.get(group) or {}).keys())
    return deps


def _parse_requirements(files: list[dict[str, Any]]) -> set[str]:
    packages: set[str] = set()
    for file in files:
        path = (file.get("path") or "").lower()
        if not path.endswith("requirements.txt"):
            continue
        for raw_line in (file.get("content") or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split("==")[0].split(">=")[0].split("<=")[0].strip()
            if name:
                packages.add(name.lower())
    return packages


def _detect_tech_stack(files: list[dict[str, Any]]) -> list[str]:
    manifest = [(file.get("path") or "").lower() for file in files]
    package_deps = _parse_package_json_deps(files)
    python_deps = _parse_requirements(files)
    tech: list[str] = []

    def add(label: str):
        if label not in tech:
            tech.append(label)

    if any(path.startswith("frontend/") for path in manifest):
        add("Frontend UI")
    if any(path.startswith("backend/") for path in manifest) or any(path.endswith(".py") for path in manifest):
        add("Python Backend")
    if "react" in package_deps:
        add("React")
    if "vite" in package_deps:
        add("Vite")
    if "typescript" in package_deps or any(path.endswith(".ts") or path.endswith(".tsx") for path in manifest):
        add("TypeScript")
    if "tailwindcss" in package_deps:
        add("Tailwind CSS")
    if "fastapi" in python_deps or any("fastapi" in (file.get("content") or "").lower() for file in files):
        add("FastAPI")
    if any("mongodb" in (file.get("content") or "").lower() for file in files):
        add("MongoDB")
    if any("websocket" in (file.get("content") or "").lower() for file in files):
        add("WebSockets")
    if any("dockerfile" in path for path in manifest):
        add("Docker")
    if any(term in (file.get("content") or "").lower() for file in files for term in ("openai", "gemini", "anthropic")):
        add("LLM Integration")

    return tech[:10]


def _extract_plan_steps(plan: Any) -> list[str]:
    if isinstance(plan, list):
        return [str(item).strip() for item in plan if str(item).strip()]
    if isinstance(plan, dict):
        steps = plan.get("steps") or plan.get("plan") or plan.get("tasks")
        if isinstance(steps, list):
            return [str(item).strip() for item in steps if str(item).strip()]
    return []


def _derive_features(project: dict[str, Any], files: list[dict[str, Any]], tech_stack: list[str]) -> list[str]:
    manifest = " ".join((file.get("path") or "").lower() for file in files)
    features: list[str] = []

    def add(feature: str):
        if feature not in features:
            features.append(feature)

    description = (project.get("description") or "").lower()
    for candidate in _extract_plan_steps(project.get("plan"))[:4]:
        add(candidate)

    if "auth" in manifest or "login" in description:
        add("Authentication and secure user access")
    if "chat" in manifest or "conversation" in description:
        add("Conversational AI workflows")
    if "preview" in manifest:
        add("Live preview and execution checks")
    if "dashboard" in manifest:
        add("Interactive dashboard views")
    if "upload" in manifest or "file" in manifest:
        add("Project file management")
    if "docker" in manifest:
        add("Container-ready deployment path")
    if "WebSockets" in tech_stack:
        add("Real-time streaming updates")
    if "LLM Integration" in tech_stack:
        add("AI-assisted reasoning and generation")

    if not features:
        add("End-to-end workflow automation")
        add("Structured frontend and backend coordination")
        add("Scalable project delivery pipeline")

    return features[:6]


def _derive_architecture_components(files: list[dict[str, Any]], tech_stack: list[str]) -> list[str]:
    components: list[str] = ["Client Interface", "Application API"]

    def add(component: str):
        if component not in components:
            components.append(component)

    if "FastAPI" in tech_stack:
        add("FastAPI Service")
    if "MongoDB" in tech_stack:
        add("MongoDB Storage")
    if "LLM Integration" in tech_stack:
        add("LLM Provider")
    if "WebSockets" in tech_stack:
        add("Realtime Channel")
    if any("auth" in (file.get("path") or "").lower() for file in files):
        add("Auth Module")
    if any("preview" in (file.get("path") or "").lower() for file in files):
        add("Preview Runner")
    if any("docker" in (file.get("path") or "").lower() for file in files):
        add("Container Runtime")

    return components[:7]


def _derive_workflow_steps(project: dict[str, Any], features: list[str]) -> list[str]:
    steps = _extract_plan_steps(project.get("plan"))
    if steps:
        return steps[:5]

    fallback = [
        "User submits the initial project request",
        "Platform interprets intent and assembles the execution plan",
        "Generation services create code, files, and derived assets",
        "Validation and preview flows check the result",
        "User iterates on the generated output",
    ]
    return [step for step in (features[:2] + fallback) if step][:5]


def _pick_key_files(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    preferred = (
        "readme",
        "package.json",
        "requirements.txt",
        "main.py",
        "app.py",
        "app.tsx",
        "index.tsx",
        "router",
    )
    selected: list[dict[str, str]] = []
    for file in files:
        path = (file.get("path") or "").strip()
        if not path:
            continue
        lower = path.lower()
        if not any(token in lower for token in preferred):
            continue
        selected.append(
            {
                "path": path,
                "excerpt": _truncate(file.get("content") or "", limit=500),
            }
        )
        if len(selected) >= 8:
            break
    return selected


def build_project_context(project_id: str, override_description: str | None = None) -> dict[str, Any]:
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError("Project not found")

    files = list_files_for_project(project_id)
    tech_stack = _detect_tech_stack(files)
    features = _derive_features(project, files, tech_stack)
    architecture_components = _derive_architecture_components(files, tech_stack)
    workflow_steps = _derive_workflow_steps(project, features)

    file_hashes = [
        {
            "path": file.get("path") or "",
            "sha256": hashlib.sha256((file.get("content") or "").encode("utf-8")).hexdigest(),
        }
        for file in files
    ]

    context = {
        "project_id": project_id,
        "title": (project.get("title") or "Untitled Project").strip(),
        "description": (override_description or project.get("description") or "").strip(),
        "plan": project.get("plan"),
        "updated_at": project.get("updated_at"),
        "file_manifest": [file.get("path") or "" for file in files if file.get("path")],
        "file_hashes": sorted(file_hashes, key=lambda item: item["path"]),
        "tech_stack": tech_stack,
        "features": features,
        "architecture_components": architecture_components,
        "workflow_steps": workflow_steps,
        "key_files": _pick_key_files(files),
    }
    return context


def fingerprint_project_context(context: dict[str, Any], *, extra: dict[str, Any] | None = None) -> str:
    payload = {
        "title": context.get("title"),
        "description": context.get("description"),
        "plan": context.get("plan"),
        "file_hashes": context.get("file_hashes"),
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _vertical_gradient(image: Image.Image, start: tuple[int, int, int], end: tuple[int, int, int]) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(
            int(start[channel] + (end[channel] - start[channel]) * ratio)
            for channel in range(3)
        )
        draw.line((0, y, width, y), fill=color)


def _draw_chip(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], text: str) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=20, fill=(20, 28, 45), outline=(45, 55, 72))
    draw.text((x1 + 18, y1 + 10), text, fill=INK, font=_load_font(22, bold=True))


class VisualService:
    def ensure_visuals(
        self,
        context: dict[str, Any],
        *,
        source_hash: str,
        force: bool = False,
    ) -> dict[str, str]:
        project_id = str(context["project_id"])
        visuals_dir = project_storage_dir(project_id, "visuals")
        suffix = source_hash[:10]
        targets = {
            "hero": visuals_dir / f"hero-{suffix}.png",
            "architecture": visuals_dir / f"architecture-{suffix}.png",
            "workflow": visuals_dir / f"workflow-{suffix}.png",
        }

        tasks = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            for key, path in targets.items():
                if force or not path.exists():
                    tasks.append(
                        executor.submit(self._render_visual, key, path, context)
                    )
            for task in tasks:
                try:
                    task.result()
                except Exception as e:
                    print(f"VisualService: Error rendering visual: {e}")

        return {key: relative_storage_path(path) for key, path in targets.items() if path.exists()}

    def _render_visual(self, key: str, path: Path, context: dict[str, Any]) -> None:
        try:
            if key == "hero":
                self._render_hero(path, context)
                return
            if key == "architecture":
                self._render_architecture(path, context)
                return
            self._render_workflow(path, context)
        except Exception as e:
            print(f"VisualService: Error rendering {key} visual: {e}")

    def _render_hero(self, path: Path, context: dict[str, Any]) -> None:
        image = Image.new("RGB", (1600, 900), BG)
        _vertical_gradient(image, BG, (13, 18, 32))
        draw = ImageDraw.Draw(image)

        for index in range(6):
            offset = index * 220
            draw.ellipse(
                (980 + offset // 3, -60 + offset // 8, 1520 + offset // 3, 480 + offset // 8),
                outline=(ACCENT[0], ACCENT[1], ACCENT[2]),
                width=2,
            )

        draw.text((90, 92), "CODEXA PRESENTATION", fill=ACCENT_SOFT, font=_load_font(24, bold=True))
        draw.text((90, 170), context["title"], fill=INK, font=_load_font(62, bold=True))
        draw.multiline_text(
            (90, 288),
            textwrap.fill(
                context.get("description") or "A structured overview of the generated solution, architecture, and roadmap.",
                width=42,
            ),
            fill=MUTED,
            font=_load_font(26),
            spacing=10,
        )

        tech_items = context.get("tech_stack") or ["AI Workflow", "Automation", "Delivery"]
        for index, tech in enumerate(tech_items[:4]):
            x = 90 + (index % 2) * 250
            y = 520 + (index // 2) * 74
            _draw_chip(draw, (x, y, x + 220, y + 52), tech)

        draw.rounded_rectangle((1040, 560, 1490, 760), radius=32, fill=(15, 23, 42), outline=(56, 189, 248), width=3)
        draw.text((1080, 600), "Presentation Focus", fill=ACCENT_SOFT, font=_load_font(24, bold=True))
        focus_lines = "\n".join(f"• {item}" for item in (context.get("features") or [])[:3])
        draw.multiline_text((1080, 650), focus_lines, fill=INK, font=_load_font(24), spacing=12)
        image.save(path, format="PNG")

    def _render_architecture(self, path: Path, context: dict[str, Any]) -> None:
        image = Image.new("RGB", (1600, 900), BG)
        _vertical_gradient(image, BG, (10, 17, 30))
        draw = ImageDraw.Draw(image)
        draw.text((90, 72), "Architecture View", fill=INK, font=_load_font(42, bold=True))
        draw.text((90, 126), "Core modules and service boundaries", fill=MUTED, font=_load_font(24))

        columns = [
            ("Experience Layer", (100, 220, 470, 740), ["User Session", "UI Screens", "Client Actions"]),
            ("Application Layer", (615, 180, 985, 780), context.get("architecture_components", [])[:4]),
            ("Data + Integration", (1130, 220, 1500, 740), (context.get("tech_stack") or ["APIs", "Storage", "Automation"])[:4]),
        ]
        for title, bounds, items in columns:
            draw.rounded_rectangle(bounds, radius=36, fill=BG_ELEVATED, outline=(56, 189, 248), width=3)
            x1, y1, x2, _ = bounds
            draw.text((x1 + 30, y1 + 26), title, fill=INK, font=_load_font(30, bold=True))
            current_y = y1 + 110
            for item in items[:4]:
                item_box = (x1 + 26, current_y, x2 - 26, current_y + 78)
                draw.rounded_rectangle(item_box, radius=24, fill=(22, 33, 55), outline=(45, 55, 72))
                draw.text((item_box[0] + 20, item_box[1] + 22), item, fill=INK, font=_load_font(24, bold=True))
                current_y += 98

        draw.line((470, 480, 615, 480), fill=ACCENT_SOFT, width=6)
        draw.line((985, 480, 1130, 480), fill=ACCENT_SOFT, width=6)
        draw.ellipse((602, 466, 628, 492), fill=ACCENT_SOFT)
        draw.ellipse((1117, 466, 1143, 492), fill=ACCENT_SOFT)
        image.save(path, format="PNG")

    def _render_workflow(self, path: Path, context: dict[str, Any]) -> None:
        image = Image.new("RGB", (1600, 900), BG)
        _vertical_gradient(image, BG, (12, 20, 38))
        draw = ImageDraw.Draw(image)
        draw.text((90, 72), "Execution Workflow", fill=INK, font=_load_font(42, bold=True))
        draw.text((90, 126), "How requests move through the platform", fill=MUTED, font=_load_font(24))

        steps = context.get("workflow_steps") or [
            "Request captured",
            "Plan assembled",
            "Assets generated",
            "Result delivered",
        ]
        x_positions = [170, 520, 870, 1220]
        for index, x in enumerate(x_positions):
            y = 430
            draw.ellipse((x, y, x + 170, y + 170), fill=BG_ELEVATED, outline=(56, 189, 248), width=4)
            draw.text((x + 60, y + 52), str(index + 1), fill=ACCENT_SOFT, font=_load_font(38, bold=True))
            label = textwrap.fill(steps[index] if index < len(steps) else "Process", width=18)
            draw.multiline_text((x - 10, y + 210), label, fill=INK, font=_load_font(24, bold=True), spacing=8, align="center")
            if index < len(x_positions) - 1:
                draw.line((x + 170, y + 85, x_positions[index + 1], y + 85), fill=ACCENT_SOFT, width=6)
                draw.ellipse((x_positions[index + 1] - 12, y + 73, x_positions[index + 1] + 12, y + 97), fill=ACCENT_SOFT)
        image.save(path, format="PNG")


def get_cached_uml_assets(project_id: str) -> dict[str, str]:
    assets = list_project_assets(project_id, asset_type="uml")
    mapping: dict[str, str] = {}
    for asset in assets:
        diagram_type = (asset.get("diagram_type") or "").strip()
        file_path = (asset.get("file_path") or "").strip()
        if not diagram_type or not file_path:
            continue
        if absolute_storage_path(file_path).exists():
            mapping[diagram_type] = file_path
    return mapping
