"""
LLM-powered auto-fixer: takes FileError list, fixes broken files using an LLM.
Targeted single-file calls — fast and cheap.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from core.validation.code_validator import FileError

_MAX_CONTEXT_CHARS = 8000


def fix_errors(
    errors: list[FileError],
    base_path: Path,
    llm_call: Callable[[str], str],
    max_rounds: int = 3,
) -> dict[str, int]:
    """Fix files with errors using LLM. Returns {path: rounds_taken}."""
    fixed: dict[str, int] = {}

    by_file: dict[str, list[FileError]] = {}
    for e in errors:
        by_file.setdefault(e.path, []).append(e)

    for rel_path, file_errors in by_file.items():
        file_path = base_path / rel_path.replace("/", "\\")
        if not file_path.exists() or file_path.is_dir():
            print(f"[AutoFixer] Skipping (not a file): {rel_path}")
            continue

        for attempt in range(1, max_rounds + 1):
            current_content = file_path.read_text(encoding="utf-8", errors="replace")
            context = _build_context(rel_path, current_content, base_path)
            error_summary = _format_errors(file_errors)

            prompt = _build_prompt(rel_path, current_content, error_summary, context)
            try:
                response = llm_call(prompt)
                fixed_content = _extract_fixed_content(response, rel_path, current_content)
                if fixed_content and fixed_content != current_content:
                    file_path.write_text(fixed_content, encoding="utf-8")
                    print(f"[AutoFixer] Fixed {rel_path} (attempt {attempt})")
                    fixed[rel_path] = attempt
                    break
                else:
                    print(f"[AutoFixer] No change for {rel_path} on attempt {attempt}")
            except Exception as e:
                print(f"[AutoFixer] LLM call failed for {rel_path}: {e}")
                break

    return fixed


def _format_errors(errors: list[FileError]) -> str:
    lines = []
    for e in errors:
        loc = f"line {e.line}" if e.line else "unknown line"
        lines.append(f"- [{e.error_type}] {loc}: {e.message}")
    return "\n".join(lines)


def _build_context(rel_path: str, file_content: str, base_path: Path) -> str:
    """
    Dynamically build context from files that the broken file actually imports.
    Much more accurate than a static map.
    """
    parts: list[str] = []
    total = 0
    seen: set[str] = {rel_path}

    # Extract imported module names from the file content
    is_python = rel_path.endswith(".py")
    if is_python:
        # Match: from app.X import Y  /  import app.X
        imports = re.findall(r'(?:from|import)\s+(app\.[a-zA-Z0-9_.]+)', file_content)
        for imp in imports:
            # Convert dotted path to file path: app.utils.security -> app/utils/security.py
            candidate = imp.replace(".", "/") + ".py"
            p = base_path / candidate
            if not p.exists():
                # Try as package __init__.py
                p = base_path / imp.replace(".", "/") / "__init__.py"
            if p.exists():
                try:
                    rel = str(p.relative_to(base_path)).replace("\\", "/")
                    if rel not in seen:
                        seen.add(rel)
                        content = p.read_text(encoding="utf-8", errors="replace")
                        snippet = content[:3000]
                        parts.append(f"=== {rel} ===\n{snippet}")
                        total += len(snippet)
                        if total >= _MAX_CONTEXT_CHARS:
                            break
                except Exception:
                    pass
    else:
        # TypeScript: match from '@/X' or './X' or '../X'
        imports = re.findall(r'from\s+[\'"](@/[^\'"]+|\.\.?/[^\'"]+)[\'"]', file_content)
        for imp in imports:
            # Resolve @/ alias to src/
            candidate = imp.replace("@/", "src/")
            for ext in [".ts", ".tsx", "/index.ts", "/index.tsx"]:
                p = base_path / (candidate + ext)
                if p.exists():
                    try:
                        rel = str(p.relative_to(base_path)).replace("\\", "/")
                        if rel not in seen:
                            seen.add(rel)
                            content = p.read_text(encoding="utf-8", errors="replace")
                            snippet = content[:2000]
                            parts.append(f"=== {rel} ===\n{snippet}")
                            total += len(snippet)
                            if total >= _MAX_CONTEXT_CHARS:
                                break
                    except Exception:
                        pass
            if total >= _MAX_CONTEXT_CHARS:
                break

    # Always include key anchor files if we haven't hit the limit
    anchors = ["app/schemas.py", "app/models.py", "src/types/index.ts"] if is_python else ["src/types/index.ts", "src/services/api.ts"]
    for anchor in anchors:
        if total >= _MAX_CONTEXT_CHARS:
            break
        p = base_path / anchor.replace("/", "\\")
        if p.exists():
            rel = anchor
            if rel not in seen:
                seen.add(rel)
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    snippet = content[:1500]
                    parts.append(f"=== {anchor} ===\n{snippet}")
                    total += len(snippet)
                except Exception:
                    pass

    return "\n\n".join(parts)


def _build_prompt(rel_path: str, content: str, errors: str, context: str) -> str:
    ctx_section = f"\n\nRelated files for context:\n{context}" if context else ""
    lang = "Python" if rel_path.endswith(".py") else "TypeScript"
    return f"""Fix ONLY the errors listed below in this {lang} file. Do not rewrite working code.

File: {rel_path}

Errors:
{errors}

Current content:
{content}
{ctx_section}

Rules:
- Fix ALL listed errors completely
- Do NOT change code that is not related to the errors
- Do NOT add markdown fences, comments about changes, or any explanation
- Return ONLY the raw fixed file content — first character must be the first line of code"""


def _extract_fixed_content(response: str, rel_path: str, original: str) -> str:
    if not response or not response.strip():
        return original

    # Strip markdown fences if present
    text = response.strip()

    # Remove ```python ... ``` or ```typescript ... ``` fences
    fence_match = re.match(r'^```(?:python|typescript|ts|js|tsx|jsx)?\s*\n(.*?)```\s*$', text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).rstrip()

    # Remove single opening fence
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines)
        if lines[-1].strip() == "```":
            end -= 1
        return "\n".join(lines[1:end])

    return text
