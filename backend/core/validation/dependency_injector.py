import json
import re
from typing import List

from core.validation.import_extractor import scan_flat_files

# Known good versions. Add new packages here as they appear in generated projects.
_NPM_VERSIONS = {
    "react-hook-form":              "^7.51.0",
    "@hookform/resolvers":          "^3.3.4",
    "zod":                          "^3.22.4",
    "date-fns":                     "^3.3.1",
    "recharts":                     "^2.12.0",
    "lucide-react":                 "^0.344.0",
    "framer-motion":                "^11.0.5",
    "react-hot-toast":              "^2.4.1",
    "sonner":                       "^1.4.0",
    "react-toastify":               "^10.0.4",
    "react-icons":                  "^5.0.1",
    "react-select":                 "^5.8.0",
    "react-datepicker":             "^6.1.0",
    "react-modal":                  "^3.16.1",
    "clsx":                         "^2.1.0",
    "class-variance-authority":     "^0.7.0",
    "tailwind-merge":               "^2.2.1",
    "jwt-decode":                   "^4.0.0",
    "zustand":                      "^4.5.2",
    "jotai":                        "^2.7.0",
    "@tanstack/react-query":        "^5.28.0",
    "@tanstack/react-table":        "^8.13.2",
    "react-query":                  "^3.39.3",
    "@radix-ui/react-dialog":       "^1.0.5",
    "@radix-ui/react-dropdown-menu":"^2.0.6",
    "@radix-ui/react-toast":        "^1.1.5",
    "@radix-ui/react-label":        "^2.0.2",
    "@radix-ui/react-select":       "^2.0.0",
    "@radix-ui/react-checkbox":     "^1.0.4",
    "@radix-ui/react-switch":       "^1.0.3",
    "@radix-ui/react-tabs":         "^1.0.4",
    "@radix-ui/react-popover":      "^1.0.7",
    "@radix-ui/react-avatar":       "^1.0.4",
    "@radix-ui/react-slot":         "^1.0.2",
    "@radix-ui/react-accordion":    "^1.1.2",
    "@radix-ui/react-separator":    "^1.0.3",
    "@radix-ui/react-scroll-area":  "^1.0.5",
    "@radix-ui/react-progress":     "^1.0.3",
    "@radix-ui/react-alert-dialog": "^1.0.5",
    "@radix-ui/react-tooltip":      "^1.0.7",
    "@radix-ui/react-navigation-menu": "^1.1.4",
    "@radix-ui/react-context-menu": "^2.1.5",
    "@radix-ui/react-menubar":      "^1.0.4",
    "@radix-ui/react-collapsible":  "^1.0.3",
    "cmdk":                         "^0.2.1",
    "vaul":                         "^0.9.0",
    "embla-carousel-react":         "^8.0.0",
    "react-resizable-panels":       "^2.0.3",
    "input-otp":                    "^1.2.4",
    "react-day-picker":             "^8.10.0",
    "chart.js":                     "^4.4.2",
    "react-chartjs-2":              "^5.2.0",
    "d3":                           "^7.9.0",
    "leaflet":                      "^1.9.4",
    "react-leaflet":                "^4.2.1",
    "@types/leaflet":               "^1.9.8",
    "axios":                        "^1.6.7",
    "swr":                          "^2.2.5",
    "socket.io-client":             "^4.7.4",
    "react-dropzone":               "^14.2.3",
    "react-beautiful-dnd":          "^13.1.1",
    "@hello-pangea/dnd":            "^16.3.0",
    "react-virtualized":            "^9.22.5",
    "react-window":                 "^1.8.10",
    "react-infinite-scroll-component": "^6.1.0",
    "stripe":                       "^14.17.0",
    "@stripe/react-stripe-js":      "^2.5.0",
    "@stripe/stripe-js":            "^3.0.6",
    "marked":                       "^12.0.0",
    "react-markdown":               "^9.0.1",
    "highlight.js":                 "^11.9.0",
    "prismjs":                      "^1.29.0",
    "react-syntax-highlighter":     "^15.5.0",
    "monaco-editor":                "^0.47.0",
    "@monaco-editor/react":         "^4.6.0",
    "dompurify":                    "^3.0.9",
    "uuid":                         "^9.0.0",
    "nanoid":                       "^5.0.6",
    "lodash":                       "^4.17.21",
    "lodash-es":                    "^4.17.21",
    "dayjs":                        "^1.11.10",
    "moment":                       "^2.30.1",
    "numeral":                      "^2.0.6",
}

_PIP_VERSIONS = {
    "python-multipart":  "python-multipart==0.0.9",
    "aiofiles":          "aiofiles==23.2.1",
    "httpx":             "httpx==0.26.0",
    "email-validator":   "email-validator==2.1.0",
    "requests":          "requests==2.31.0",
    "Pillow":            "Pillow==10.2.0",
    "PyYAML":            "PyYAML==6.0.1",
    "celery":            "celery==5.3.6",
    "redis":             "redis==5.0.1",
    "stripe":            "stripe==8.0.0",
    "sendgrid":          "sendgrid==6.11.0",
    "boto3":             "boto3==1.34.34",
    "cryptography":      "cryptography==42.0.4",
    "PyJWT":             "PyJWT==2.8.0",
    "Jinja2":            "Jinja2==3.1.3",
    "pydantic-settings": "pydantic-settings==2.2.1",
    "python-jose":       "python-jose[cryptography]==3.3.0",
    "bcrypt":            "bcrypt==4.1.2",
}


def inject_npm(package_json_content: str, missing: List[str]) -> tuple[str, List[str]]:
    """
    Add missing npm packages to package.json.
    Returns (updated_content, list_of_injected_packages).
    """
    if not missing:
        return package_json_content, []
    try:
        pkg = json.loads(package_json_content)
    except Exception:
        return package_json_content, []

    deps = pkg.setdefault("dependencies", {})
    injected = []
    for name in missing:
        if name not in deps:
            version = _NPM_VERSIONS.get(name, "latest")
            deps[name] = version
            injected.append(f"{name}@{version}")
            print(f"[DepInjector] +npm {name}@{version}")

    return json.dumps(pkg, indent=2), injected


def inject_pip(requirements_content: str, missing: List[str]) -> tuple[str, List[str]]:
    """
    Add missing pip packages to requirements.txt.
    Returns (updated_content, list_of_injected_packages).
    """
    if not missing:
        return requirements_content, []

    existing_lower = set()
    for line in requirements_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pkg = re.split(r"[>=<!~\[\s]", line)[0].strip().lower()
            existing_lower.add(pkg)

    lines = requirements_content.splitlines()
    injected = []
    for name in missing:
        if name.lower() not in existing_lower:
            pip_line = _PIP_VERSIONS.get(name, name)
            lines.append(pip_line)
            injected.append(pip_line)
            print(f"[DepInjector] +pip {pip_line}")

    return "\n".join(lines), injected


def fix_flat_files(flat_files: List[dict]) -> dict:
    """
    Scan flat_files for missing npm/pip dependencies and inject them in-place.

    Modifies the 'content' field of package.json and requirements.txt entries
    directly inside flat_files (mutates the list items).

    Returns a report:
    {
      "npm_missing_detected": [...],
      "pip_missing_detected": [...],
      "npm_injected":         [...],
      "pip_injected":         [...],
    }
    """
    scan = scan_flat_files(flat_files)

    npm_injected: List[str] = []
    pip_injected: List[str] = []

    for f in flat_files:
        path = f.get("path", "")

        if path == "frontend/package.json" and scan["npm_missing"]:
            new_content, added = inject_npm(f["content"], scan["npm_missing"])
            f["content"] = new_content
            npm_injected.extend(added)

        elif path == "backend/requirements.txt" and scan["pip_missing"]:
            new_content, added = inject_pip(f["content"], scan["pip_missing"])
            f["content"] = new_content
            pip_injected.extend(added)

    if npm_injected or pip_injected:
        print(f"[DepInjector] Injected {len(npm_injected)} npm, {len(pip_injected)} pip packages.")

    return {
        "npm_missing_detected": scan["npm_missing"],
        "pip_missing_detected": scan["pip_missing"],
        "npm_injected":         npm_injected,
        "pip_injected":         pip_injected,
    }
