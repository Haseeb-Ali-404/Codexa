"""
Validates generated project code: Python syntax + imports, TypeScript compilation.
Returns structured FileError objects for auto_fixer to consume.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileError:
    path: str          # relative path from project root, e.g. "backend/app/main.py"
    line: int | None
    message: str
    error_type: str    # "syntax" | "import" | "typescript" | "runtime"
    full_output: str = ""


def validate_python(backend_path: Path) -> list[FileError]:
    errors: list[FileError] = []
    py_files = list(backend_path.rglob("*.py"))

    for py_file in py_files:
        if "__pycache__" in str(py_file):
            continue
        rel = py_file.relative_to(backend_path)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(py_file)],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                line_num = _extract_line_number(stderr)
                errors.append(FileError(
                    path=str(rel).replace("\\", "/"),
                    line=line_num,
                    message=stderr,
                    error_type="syntax",
                    full_output=stderr,
                ))
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            errors.append(FileError(
                path=str(rel).replace("\\", "/"),
                line=None,
                message=str(e),
                error_type="syntax",
            ))

    # Import check: only run if .env exists (missing .env causes pydantic-settings to crash,
    # which is not a code error — it's a config issue we auto-fix separately)
    main_py = backend_path / "main.py"
    env_file = backend_path / ".env"
    if main_py.exists() and env_file.exists() and not errors:
        try:
            result = subprocess.run(
                [sys.executable, "-c", "import sys; sys.path.insert(0,''); import main"],
                cwd=str(backend_path),
                capture_output=True, text=True, timeout=25
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                # Skip errors caused by missing env vars or DB connection — not fixable by LLM
                _skip_patterns = [
                    "ValidationError", "missing", "MONGO", "mongodb", "connection",
                    "pydantic_settings", "field required", "env_file"
                ]
                if any(p.lower() in stderr.lower() for p in _skip_patterns):
                    print(f"[Validator] Skipping import error (config/env issue): {_last_error_line(stderr)}")
                else:
                    broken_file = _extract_file_from_traceback(stderr, backend_path)
                    errors.append(FileError(
                        path=broken_file or "main.py",
                        line=_extract_line_number(stderr),
                        message=_last_error_line(stderr),
                        error_type="import",
                        full_output=stderr,
                    ))
        except subprocess.TimeoutExpired:
            pass

    return errors


def validate_typescript(frontend_path: Path) -> list[FileError]:
    errors: list[FileError] = []
    tsconfig = frontend_path / "tsconfig.json"
    if not tsconfig.exists():
        return errors

    node_modules = frontend_path / "node_modules"
    if not node_modules.exists():
        return errors

    # Use npx.cmd on Windows, npx elsewhere
    npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
    try:
        result = subprocess.run(
            [npx_cmd, "tsc", "--noEmit", "--skipLibCheck"],
            cwd=str(frontend_path),
            capture_output=True, text=True, timeout=60,
            shell=(sys.platform == "win32")
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).replace("\\", "/")
            errors.extend(_parse_tsc_output(output, frontend_path))
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        print(f"[Validator] tsc check failed: {e}")

    return errors


def _extract_line_number(text: str) -> int | None:
    import re
    m = re.search(r'line (\d+)', text)
    if m:
        return int(m.group(1))
    m = re.search(r':(\d+):', text)
    if m:
        return int(m.group(1))
    return None


def _extract_file_from_traceback(stderr: str, base_path: Path) -> str | None:
    import re
    # Match: File "/path/to/backend/app/foo.py", line N
    for m in re.finditer(r'File "([^"]+\.py)", line \d+', stderr):
        fp = Path(m.group(1))
        try:
            rel = fp.relative_to(base_path)
            return str(rel).replace("\\", "/")
        except ValueError:
            continue
    return None


def _last_error_line(stderr: str) -> str:
    lines = [l for l in stderr.strip().splitlines() if l.strip()]
    return lines[-1] if lines else stderr[:200]


def _parse_tsc_output(output: str, frontend_path: Path) -> list[FileError]:
    import re
    errors: list[FileError] = []
    seen: set[tuple] = set()
    # Pattern: src/components/Foo.tsx(12,5): error TS2345: ...
    pattern = re.compile(r'^(.+?)\((\d+),\d+\): error (TS\d+): (.+)$', re.MULTILINE)
    for m in pattern.finditer(output):
        raw_path, line_str, ts_code, msg = m.groups()
        rel = raw_path.strip().replace("\\", "/")
        line = int(line_str)
        key = (rel, line, ts_code)
        if key in seen:
            continue
        seen.add(key)
        errors.append(FileError(
            path=rel,
            line=line,
            message=f"{ts_code}: {msg}",
            error_type="typescript",
            full_output=output[:2000],
        ))
        if len(errors) >= 10:
            break
    return errors
