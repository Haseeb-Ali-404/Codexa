"""
Multi-call project generator (Lovable-style architecture).

Each file group gets its own dedicated LLM call with the FULL token budget.
Files are generated in dependency order — later calls see all prior outputs.
Context accumulates across groups so every file is consistent with the rest.
"""
from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import AsyncIterator

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


MAX_FILES_PER_GROUP = 7   # Hard cap: Gemini returns nothing for huge prompts

# ---------------------------------------------------------------------------
# Prompt sanity check — catches unescaped { } in format templates at import time
# ---------------------------------------------------------------------------
def _validate_prompts() -> None:
    _dummy = {"project_spec": "", "context": "", "n_files": 0, "files_to_generate": "", "specific_instructions": ""}
    try:
        _STRUCTURE_PLAN_PROMPT.format(user_message="", plan_steps="")
    except KeyError as e:
        raise RuntimeError(f"_STRUCTURE_PLAN_PROMPT has unescaped format key: {e}") from e
    try:
        _FILE_GEN_PROMPT.format(**_dummy)
    except KeyError as e:
        raise RuntimeError(f"_FILE_GEN_PROMPT has unescaped format key: {e}") from e

# Groups that can run in parallel (they don't depend on each other's output)
# Group numbers match _group_of() return values
_PARALLEL_SETS: list[frozenset[int]] = [
    frozenset({3, 4}),   # backend services + backend routes
    frozenset({7, 8}),   # frontend stores + frontend components
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(content: str) -> str:
    """Strip markdown code fences (```lang\\n...```) that LLMs sometimes wrap output in."""
    s = content.strip()
    if not s.startswith("```"):
        return content
    lines = s.splitlines()
    # Find closing fence
    end = len(lines)
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip() == "```":
            end = i
            break
    # Strip opening fence line
    return "\n".join(lines[1:end])


def _extract_files(raw: str) -> dict[str, str]:
    """Parse <file path="...">...</file> blocks from LLM output."""
    files: dict[str, str] = {}
    for m in re.finditer(
        r'<file\s+path=["\']([^"\']+)["\']>([\s\S]*?)</file>',
        raw,
        re.MULTILINE,
    ):
        path, content = m.group(1).strip(), m.group(2)
        if content.startswith("\n"):
            content = content[1:]
        if content.endswith("\n"):
            content = content[:-1]
        files[path] = _strip_fences(content)
    return files


def _context_block(generated: dict[str, str], max_chars: int = 120_000) -> str:
    """Build a compact context block from already-generated files (newest-first, size-capped)."""
    lines: list[str] = []
    used = 0
    for path, content in reversed(list(generated.items())):
        snippet = f'\n<file path="{path}">\n{content}\n</file>\n'
        if used + len(snippet) > max_chars:
            lines.append(f'\n<!-- {path} omitted for brevity -->\n')
            continue
        lines.append(snippet)
        used += len(snippet)
    return "".join(reversed(lines))


def _flat_to_nested(flat: dict[str, str]) -> list:
    """Convert {path: content} dict into the nested structure format."""
    root: dict = {}

    # Build nested dict, guarding against path collisions (file vs folder same name)
    for path, content in flat.items():
        parts = path.replace("\\", "/").split("/")
        node = root
        for part in parts[:-1]:
            existing = node.get(part)
            if not isinstance(existing, dict):
                # Overwrite if previously set as a file — folder wins
                node[part] = {}
            node = node[part]
        node[parts[-1]] = content

    def _build(d, name: str = ""):
        # Guard: leaf value passed as folder (path collision)
        if isinstance(d, str):
            return {"type": "file", "name": name, "content": d}
        children = []
        for k, v in d.items():
            children.append(_build(v, k))
        if name:
            return {"type": "folder", "name": name, "children": children}
        return children  # top-level call returns list

    structure = []
    for top_name, subtree in root.items():
        built = _build(subtree, top_name)
        structure.append(built)
    return structure


# ---------------------------------------------------------------------------
# Group assignment — stack-agnostic, handles FastAPI/React, Next.js, Express
# ---------------------------------------------------------------------------

def _group_of(path: str) -> int:
    p = path.lower().replace("\\", "/")
    fname = p.split("/")[-1]

    # Group 0: Pure config / metadata / static files
    _CONFIG_FILES = {
        "requirements.txt", "package.json", "package-lock.json",
        "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json", "tsconfig.build.json", "tsconfig.base.json",
        ".env.example", ".env.local.example", "vite.config.ts", "vite.config.js",
        "next.config.mjs", "next.config.js", "next.config.ts",
        "tailwind.config.ts", "tailwind.config.js", "postcss.config.js",
        "postcss.config.cjs", "docker-compose.yml", "docker-compose.yaml",
        "dockerfile", ".dockerignore", ".gitignore", "readme.md",
        "eslint.config.js", ".eslintrc.js", ".eslintrc.cjs", "prettier.config.js",
        "index.html", "__init__.py", "schema.prisma", "jest.config.ts",
        "jest.config.js", "vitest.config.ts",
    }
    if fname in _CONFIG_FILES or fname.endswith(".example") or fname.endswith(".env.example"):
        return 0
    if "prisma/schema" in p or "prisma/migrations" in p:
        return 0

    # Group 1: Types / schemas / models / interfaces
    if any(x in p for x in [
        "types/index.ts", "types/index.js", "/types.ts", "src/types/",
        "schemas.py", "models.py", "/interfaces/", "/dtos/", "/entities/",
    ]):
        return 1
    if fname in {"types.ts", "schemas.ts", "models.py", "schemas.py", "entities.ts", "dtos.ts"}:
        return 1

    # Group 2: Infrastructure — db, config, security, middleware, auth helpers
    _INFRA_FILES = {
        "config.py", "database.py", "security.py", "db.ts", "db.js",
        "prisma.ts", "prisma.js", "connection.ts", "connection.py",
        "config.ts", "env.ts", "settings.py",
    }
    if fname in _INFRA_FILES:
        return 2
    if any(x in p for x in [
        "/lib/db", "/lib/prisma", "/lib/auth.ts", "/lib/config",
        "middleware/auth", "middleware/error", "utils/security",
    ]):
        return 2
    if "middleware" in p and not any(x in p for x in ["pages/", "src/app/", "(public)", "(auth)", "(admin)"]):
        return 2

    # Group 3: Services / repositories / business logic
    if any(x in p for x in ["services/", "repositories/", "usecases/", "use-cases/"]):
        return 3
    if fname.endswith(".service.ts") or fname.endswith(".service.js") or fname.endswith("_service.py"):
        return 3
    if "service" in fname and (fname.endswith(".ts") or fname.endswith(".py")):
        return 3

    # Group 4: Controllers / routes / handlers / validations
    if any(x in p for x in ["routes/", "routers/", "controllers/", "handlers/", "resolvers/"]):
        return 4
    if any(fname.endswith(x) for x in [
        ".routes.ts", ".router.ts", ".controller.ts", ".handler.ts",
        ".validation.ts", ".validator.ts", "_routes.py", "_router.py",
    ]):
        return 4
    if "modules/" in p and any(x in fname for x in ["route", "controller", "handler", "validation", "guard"]):
        return 4

    # Group 5: App entry points
    if fname in {"main.py", "app.py", "wsgi.py", "asgi.py"} and "backend" in p:
        return 5
    if fname in {"index.ts", "index.js", "server.ts", "server.js", "app.ts", "app.js"} and (
        "backend/src" in p or p.count("/") <= 2
    ):
        return 5

    # Group 6: Frontend API layer + auth store (most critical for working auth)
    if any(x in p for x in [
        "services/api.ts", "services/api.js", "lib/api.ts", "utils/api.ts",
        "src/api.ts", "api/client.ts", "api/index.ts",
    ]):
        return 6
    if fname in {"api.ts", "api.js"} and "frontend" in p:
        return 6
    if any(x in p for x in [
        "stores/auth", "store/auth", "hooks/useauth", "hooks/use-auth",
        "context/auth", "lib/auth.ts", "src/auth.ts",
    ]):
        return 6
    if fname in {"providers.tsx", "providers.jsx"} and "frontend" in p:
        return 6

    # Group 7: Other state management — stores, hooks, contexts
    if any(x in p for x in ["stores/", "store/", "hooks/", "context/", "contexts/"]):
        return 7
    if any(fname.endswith(x) for x in ["store.ts", "Store.ts", "store.tsx", ".store.ts", ".hook.ts"]):
        return 7

    # Group 8: Shared UI components
    if any(x in p for x in [
        "/components/ui/", "/components/common/", "/components/layout/",
        "/components/shared/", "/ui/", "/design-system/",
    ]):
        return 8
    if "components/" in p and not any(x in p for x in [
        "pages/", "/app/(", "/page.tsx", "/page.jsx", "/page.ts",
    ]):
        return 8

    # Group 9: Pages / views / Next.js app router
    if any(x in p for x in [
        "pages/", "/page.tsx", "/page.jsx", "/page.ts",
        "views/", "screens/", "app/(public)/", "app/(auth)/",
        "app/(admin)/", "app/(dashboard)/", "app/(protected)/",
    ]):
        return 9
    if "/layout.tsx" in p and "src/app/" in p and "/src/app/layout.tsx" not in p:
        return 9

    # Group 1.5 (use 1): Global CSS — generated early so ALL components see class names in context
    if fname in {"globals.css", "global.css", "index.css", "app.css", "main.css"}:
        return 1

    # Group 10: Root app entry + Next.js root layout + middleware
    if fname in {"app.tsx", "app.jsx", "main.tsx", "main.jsx"} and "frontend/src" in p:
        return 10
    if "/src/app/layout.tsx" in p or p.endswith("src/app/layout.tsx"):
        return 10
    if fname == "middleware.ts" and "src/" in p and "frontend" in p:
        return 10

    return 8  # Default: treat as component


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_STRUCTURE_PLAN_PROMPT = """You are a senior software architect. Analyze the user request and produce a complete file manifest.

USER REQUEST:
{user_message}

IMPLEMENTATION PLAN:
{plan_steps}

═══ AUTH DETECTION (read carefully) ═══
Set "auth": true ONLY if the user explicitly mentions: login, signup, register, authentication, user accounts, dashboard, protected pages, JWT, or "users".
If NOT mentioned → set "auth": false. Do NOT add login/register pages just to fill space.
When auth=false, spend ALL that token budget on making the main website pages richer and more beautiful.

═══ STACK DETECTION ═══
- "next.js" / "nextjs" → Next.js 14 + App Router
- "express" / "node.js" → Express.js + TypeScript
- "prisma" → Prisma ORM; "postgres" → PostgreSQL; "mongodb" → MongoDB
- Default: FastAPI (Python) + React/Vite (TypeScript) + MongoDB

Output ONLY valid JSON. Write SPECIFIC implementation hints in every "description" field — the generator reads these directly when writing code.
{{
  "project_name": "...",
  "description": "...",
  "stack": {{"frontend": "react-vite|nextjs", "backend": "fastapi|express", "database": "mongodb|postgresql|sqlite"}},
  "auth": true,
  "entities": [{{"name": "EntityName", "fields": {{"field": "type"}}}}],
  "api_routes": {{
    "public": ["GET /api/items", "POST /api/contact"],
    "auth": ["POST /api/auth/register", "POST /api/auth/login"]
  }},
  "backend_files": [
    {{"path": "backend/main.py", "description": "FastAPI app, CORSMiddleware with origins [5959,5173,3000], lifespan startup/shutdown for DB, include_router for auth + every entity router with /api/PREFIX"}},
    {{"path": "backend/app/config.py", "description": "pydantic-settings BaseSettings: MONGO_URL, DATABASE_NAME, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES"}},
    {{"path": "backend/app/database.py", "description": "motor AsyncIOMotorClient, connect_db/disconnect_db, get_database() FastAPI Depends"}},
    {{"path": "backend/app/models.py", "description": "Pydantic v2 *InDB models — plain str for id, no PyObjectId, no bson imports, datetime fields with default_factory=datetime.utcnow"}},
    {{"path": "backend/app/schemas.py", "description": "Request/Response Pydantic schemas: LoginRequest, RegisterRequest, AuthResponse, UserResponse, Create/Update/Response for each entity — never include password in responses"}},
    {{"path": "backend/app/utils/security.py", "description": "bcrypt direct (import bcrypt as _bcrypt_lib), JWT create/verify, OAuth2PasswordBearer, get_current_user Depends with lazy user_service import"}},
    {{"path": "backend/app/routes/ENTITY.py", "description": "FastAPI APIRouter CRUD: GET / list (filter by user_id), POST / create (201), PUT /{{id}} update (find_one_and_update), DELETE /{{id}} (204) — all async, all Depends(get_current_user)"}}
  ],
  "frontend_files": [
    {{"path": "frontend/package.json", "description": "react@^18.3.1 react-dom react-router-dom@^6.26.0 axios zustand lucide-react framer-motion; devDeps: typescript vite @vitejs/plugin-react @types/react @types/node; type:module"}},
    {{"path": "frontend/src/types/index.ts", "description": "Export all TypeScript interfaces: User, AuthResponse, Entity (id:string not _id), CreateEntityRequest, UpdateEntityRequest — single source of truth"}},
    {{"path": "frontend/src/services/api.ts", "description": "axios.create baseURL=/api timeout=15000, request interceptor reads JWT from localStorage auth-storage-v2 state.token, 401 response interceptor redirects to /login"}},
    {{"path": "frontend/src/stores/ENTITYStore.ts", "description": "Zustand store: items:Entity[], isLoading, error, fetchAll (GET /entities), create (POST, prepend), update (PUT /id, map-replace), remove (DELETE /id, filter) — full try/catch/finally"}},
    {{"path": "frontend/src/pages/ENTITYPage.tsx", "description": "CRUD page: useEffect fetchAll, loading/error/empty/data states, card grid, modal for create/edit, delete with window.confirm, page-header with New button"}}
  ]
}}

═══ REQUIRED FILES — auth=false (website-first) ═══

FastAPI backend (minimal, no auth):
  backend/requirements.txt  backend/.env.example  backend/main.py
  backend/app/__init__.py  backend/app/config.py  backend/app/database.py
  backend/app/models.py  backend/app/schemas.py
  backend/app/routes/__init__.py
  + per entity: backend/app/routes/ENTITY.py  backend/app/services/ENTITY_service.py

React/Vite frontend (auth=false — invest ALL tokens here):
  frontend/package.json  frontend/vite.config.ts  frontend/tsconfig.json  frontend/tsconfig.app.json  frontend/tsconfig.node.json  frontend/index.html
  frontend/src/main.tsx  frontend/src/App.tsx  frontend/src/index.css
  frontend/src/types/index.ts  frontend/src/services/api.ts
  frontend/src/components/layout/Navbar.tsx
  frontend/src/components/layout/Footer.tsx
  frontend/src/components/sections/HeroSection.tsx
  frontend/src/components/sections/FeaturesSection.tsx
  frontend/src/components/sections/HowItWorksSection.tsx
  frontend/src/components/sections/TestimonialsSection.tsx
  frontend/src/components/sections/CTASection.tsx
  frontend/src/components/common/Button.tsx
  frontend/src/components/common/Card.tsx
  frontend/src/pages/HomePage.tsx
  + per entity: frontend/src/pages/ENTITYPage.tsx  frontend/src/components/ENTITY/ENTITYCard.tsx

═══ REQUIRED FILES — auth=true (full app) ═══

FastAPI backend MUST include ALL of:
  backend/requirements.txt  backend/.env.example  backend/main.py
  backend/app/__init__.py  backend/app/config.py  backend/app/database.py
  backend/app/models.py  backend/app/schemas.py
  backend/app/utils/__init__.py  backend/app/utils/security.py
  backend/app/services/__init__.py  backend/app/services/user_service.py
  backend/app/routes/__init__.py  backend/app/routes/auth.py
  + per entity: backend/app/services/ENTITY_service.py  backend/app/routes/ENTITY.py

React/Vite frontend (auth=true):
  frontend/package.json  frontend/vite.config.ts  frontend/tsconfig.json  frontend/tsconfig.app.json  frontend/tsconfig.node.json  frontend/index.html
  frontend/src/main.tsx  frontend/src/App.tsx  frontend/src/index.css
  frontend/src/types/index.ts  frontend/src/services/api.ts
  frontend/src/stores/authStore.ts
  frontend/src/components/layout/Header.tsx  frontend/src/components/layout/Sidebar.tsx
  frontend/src/components/common/Button.tsx  frontend/src/components/common/Input.tsx
  frontend/src/components/common/Modal.tsx  frontend/src/components/common/LoadingSpinner.tsx
  frontend/src/components/common/EmptyState.tsx  frontend/src/components/common/ErrorMessage.tsx
  frontend/src/pages/LoginPage.tsx  frontend/src/pages/RegisterPage.tsx
  frontend/src/pages/DashboardPage.tsx
  + per entity: frontend/src/stores/ENTITYStore.ts  frontend/src/pages/ENTITYPage.tsx

═══ CRITICAL RULES ═══
- FastAPI entry MUST be "backend/main.py" — NEVER "backend/app/main.py"
- React/Vite MUST include "frontend/tsconfig.node.json"
- NEVER use Chakra UI, MUI, Ant Design, Bootstrap — plain CSS + lucide-react only
- NEVER add Redis/Celery/Websockets unless requested
- requirements.txt MUST include: fastapi uvicorn[standard] motor pymongo pydantic-settings python-dotenv
- If auth=true also add: python-jose[cryptography] bcrypt python-multipart
- package.json MUST include: zustand axios lucide-react react-router-dom framer-motion
- If auth=true also add: react-hook-form zod @hookform/resolvers

Output ONLY the JSON manifest."""


_FILE_GEN_PROMPT = """You are an elite full-stack engineer and UI designer. Generate PRODUCTION-READY, COMPLETE code at the quality level of Lovable.dev, v0.dev, and Linear.app — stunning, real-world websites users love at first glance.

═══ PROJECT SPEC ═══
{project_spec}

═══ ALREADY GENERATED FILES (match exactly — same imports, types, naming) ═══
{context}

═══ YOUR TASK: Generate {n_files} file(s) ═══
{files_to_generate}

═══ HARD CONSTRAINTS ═══
• NEVER import: @chakra-ui @mui antd bootstrap @mantine @nextui-org — plain CSS + lucide-react + framer-motion
• NEVER import SVG files as React components — NO `import X from '*.svg?react'`, NO `import X from '*.svg'` used as JSX — use lucide-react icons or CSS/text logos instead
• NEVER reference files in src/assets/ unless you also generate that file — use inline SVG JSX or lucide-react icons
• FastAPI entry is ALWAYS backend/main.py — never backend/app/main.py
• FastAPI CORS allow_origins MUST include "http://localhost:5959"
• Vite port = 5959, proxy /api → http://localhost:7979
• backend: use bcrypt directly (import bcrypt as _bcrypt_lib) — NEVER passlib
• api.ts: axios interceptor reads JWT from localStorage key 'auth-storage-v2'
• authStore.ts: persist name='auth-storage-v2', partialize excludes isLoading/error
• package.json MUST have: zustand axios lucide-react react-router-dom framer-motion
• If auth project: also add react-hook-form zod @hookform/resolvers

═══ CSS CLASS CONTRACT (most common source of broken UI — read carefully) ═══
The index.css file is generated FIRST and its class names are the contract. Every component MUST use ONLY those exact class names.
AUTH-APP projects — required classes already in index.css — use exactly these names:
  Layout: .app-layout .sidebar .sidebar-brand .sidebar-nav .sidebar-link .sidebar-link.active .main-content .header .user-menu .user-avatar
  Auth: .auth-page .auth-card .auth-title .auth-subtitle .auth-switch .error-message
  Forms: .form-group .form-label .form-input .form-error .form-hint
  Buttons: .btn .btn-primary .btn-secondary .btn-ghost .btn-danger .btn-full .btn-sm .btn-lg .btn-loading
  Data: .page-header .data-grid .card .card-header .card-actions .badge .badge-success .badge-warning .badge-danger .badge-info
  Dashboard: .dashboard-grid .stat-card .stat-icon .stat-value .stat-label
  Modal: .modal-overlay .modal .modal-header .modal-footer
  Utility: .loading-state .error-state .empty-state .spinner .spinner-sm .skeleton
WEBSITE-FIRST projects — required classes:
  .navbar .navbar.scrolled .hamburger .mobile-menu .hero .hero-blob .hero-content .hero-visual .hero-stats .stat-item
  .section .section-title .section-subtitle .container .features-grid .feature-card .icon-box
  .steps-grid .step .testimonials-grid .testimonial-card .cta-section .footer .footer-grid .footer-bottom
  .btn .btn-primary .btn-secondary .glass .gradient-text .animate-fade-in-up .delay-100→.delay-600
NEVER invent a className not in this list — it will have no CSS rule and render as unstyled text.

═══ NAMING & CONSISTENCY (identical across every file — no drift) ═══
• Entity naming: singular PascalCase TS interface (Task) | plural snake_case MongoDB collection (tasks) | plural kebab route prefix (/api/tasks) | camelCase+Store Zustand (useTaskStore) | plural PascalCase page (TasksPage.tsx)
• _id → id mapping: every backend response must transform _id: return {{"id": str(d["_id"]), **{{k:v for k,v in d.items() if k!="_id"}}}}
• Frontend never uses _id — all interfaces in types/index.ts use id: string
• API path alignment: if include_router(tasks.router, prefix="/api/tasks") → frontend calls api.get('/tasks') (axios baseURL='/api')
• lucide-react: ALWAYS named imports — import {{ Zap, Shield, BarChart2 }} from 'lucide-react'
• TS types: import from '@/types' or '../types/index' — NEVER redefine an interface that already exists in types/index.ts
• Every JSX component tag must have a matching import at the top of that file — scan your own output before finalizing
• CSS class names: ONLY use classes defined in index.css — never invent a className that has no CSS rule in the stylesheet

═══ CODE COMPLETENESS (zero shortcuts) ═══
• Every function FULLY implemented — zero "pass", "TODO", "raise NotImplementedError", "// implement"
• All imports at the top — no missing imports anywhere
• All types fully defined — NO `any` types in TypeScript
• All referenced functions/components MUST be defined or imported from context files

═══ WORKING BUTTONS & INTERACTIVITY (mandatory — zero dead UI) ═══
• EVERY <button> and <Button> MUST have a real onClick that does something — never onClick={{() => {{}}}}
• Navigation buttons → const navigate = useNavigate(); onClick={{() => navigate('/path')}}
• Scroll-to-section buttons → onClick={{() => document.getElementById('section-id')?.scrollIntoView({{behavior:'smooth'}})}}
• "Get Started" / "Try Now" / "Sign Up" CTAs → navigate to next section or /signup
• Modal open buttons → const [isOpen, setIsOpen] = useState(false); onClick={{() => setIsOpen(true)}}; modal uses onClose={{() => setIsOpen(false)}}
• Form submit → onSubmit on the <form> tag using handleSubmit(onSubmit) — NOT onClick on button
• Delete buttons → confirm first (window.confirm OR a modal), then call store action
• Hamburger menu → toggles a boolean state; menu slides in/out with CSS transition
• ALL <a href="#"> MUST be replaced with <button onClick={{...}}> or <Link to="...">
• Nav links that scroll → always implement the scrollIntoView logic, never leave as dead anchors
• Dropdown/accordion toggles → useState boolean, chevron rotates with CSS transform

═══ ZERO RUNTIME ERRORS (the golden rule) ═══
• Optional chaining everywhere: user?.name, items?.length, data?.results ?? []
• Guard ALL .map()/.filter() calls: ensure the array exists first — (items ?? []).map(...)
• ALL useEffect with async: wrap in inner async fn, cleanup with AbortController or isMounted ref
• Every async store action: try {{ set({{isLoading:true}}); ... }} catch(e) {{ set({{error: e.message}}) }} finally {{ set({{isLoading:false}}) }}
• Event handler types explicit: (e: React.MouseEvent<HTMLButtonElement>) => void
• className not class, htmlFor not for, defaultValue not value for uncontrolled inputs
• Images: always include alt="" attribute
• Keys in lists: always unique stable key (item.id or item._id), NEVER array index for dynamic lists
• No circular imports: stores import from api.ts, pages import from stores — never the reverse
• TypeScript: prefer interface over type for object shapes; export all interfaces from types/index.ts

═══ EXACT CRUD PATTERNS (copy these exactly — substitute entity name only) ═══
FastAPI route (Motor async — replace "foo"/"Foo"/"foos" with real entity):
  from bson import ObjectId; from datetime import datetime; from typing import List
  from fastapi import APIRouter, Depends, HTTPException
  from app.database import get_database; from app.utils.security import get_current_user
  from app.schemas import FooResponse, CreateFooRequest, UpdateFooRequest
  router = APIRouter()

  @router.get("/", response_model=List[FooResponse])
  async def list_foos(db=Depends(get_database), user=Depends(get_current_user)):
      docs = await db.foos.find({{"user_id": str(user["_id"])}}).to_list(length=200)
      return [{{"id": str(d["_id"]), **{{k:v for k,v in d.items() if k!="_id"}}}} for d in docs]

  @router.post("/", response_model=FooResponse, status_code=201)
  async def create_foo(body: CreateFooRequest, db=Depends(get_database), user=Depends(get_current_user)):
      doc = {{**body.model_dump(), "user_id": str(user["_id"]), "created_at": datetime.utcnow()}}
      result = await db.foos.insert_one(doc); created = await db.foos.find_one({{"_id": result.inserted_id}})
      return {{"id": str(created["_id"]), **{{k:v for k,v in created.items() if k!="_id"}}}}

  @router.put("/{{foo_id}}", response_model=FooResponse)
  async def update_foo(foo_id: str, body: UpdateFooRequest, db=Depends(get_database), user=Depends(get_current_user)):
      updated = await db.foos.find_one_and_update({{"_id": ObjectId(foo_id), "user_id": str(user["_id"])}}, {{"$set": body.model_dump(exclude_unset=True)}}, return_document=True)
      if not updated: raise HTTPException(404, "Not found")
      return {{"id": str(updated["_id"]), **{{k:v for k,v in updated.items() if k!="_id"}}}}

  @router.delete("/{{foo_id}}", status_code=204)
  async def delete_foo(foo_id: str, db=Depends(get_database), user=Depends(get_current_user)):
      r = await db.foos.delete_one({{"_id": ObjectId(foo_id), "user_id": str(user["_id"])}})
      if r.deleted_count == 0: raise HTTPException(404, "Not found")

Zustand store (replace Foo/foo — all CRUD actions, no missing methods):
  import {{ create }} from 'zustand'; import api from '@/services/api'; import type {{ Foo, CreateFooRequest }} from '@/types'
  interface FooState {{ items: Foo[]; isLoading: boolean; error: string | null
    fetchAll: () => Promise<void>; create: (d: CreateFooRequest) => Promise<Foo>
    update: (id: string, d: Partial<Foo>) => Promise<void>; remove: (id: string) => Promise<void> }}
  export const useFooStore = create<FooState>()((set) => ({{
    items: [], isLoading: false, error: null,
    fetchAll: async () => {{ set({{isLoading:true,error:null}})
      try {{ const {{data}} = await api.get<Foo[]>('/foos'); set({{items:data}}) }}
      catch(e:any) {{ set({{error:e.response?.data?.detail??'Failed'}}) }} finally {{ set({{isLoading:false}}) }} }},
    create: async (payload) => {{ const {{data}} = await api.post<Foo>('/foos', payload)
      set((s) => ({{items:[data,...s.items]}})); return data }},
    update: async (id,payload) => {{ const {{data}} = await api.put<Foo>(`/foos/${{id}}`, payload)
      set((s) => ({{items:s.items.map(i=>i.id===id?data:i)}})) }},
    remove: async (id) => {{ await api.delete(`/foos/${{id}}`)
      set((s) => ({{items:s.items.filter(i=>i.id!==id)}})) }},
  }}))

Entity Page pattern (replace Foo — loading/error/empty/data states required):
  const {{ items, isLoading, error, fetchAll, remove }} = useFooStore()
  const [showModal, setShowModal] = useState(false)
  useEffect(() => {{ fetchAll() }}, [])
  if (isLoading) return <LoadingSpinner />
  if (error) return <div className="error-state">{{error}}</div>
  return (<div>
    <div className="page-header"><h1>Foos</h1><Button onClick={{()=>setShowModal(true)}}>+ New Foo</Button></div>
    {{items.length===0 ? <EmptyState title="No foos yet" action={{<Button onClick={{()=>setShowModal(true)}}>Create your first foo</Button>}} />
      : <div className="grid">{{items.map(item=><FooCard key={{item.id}} item={{item}} onDelete={{()=>{{if(window.confirm('Delete?'))remove(item.id)}}}} />)}}</div>}}
  </div>)

═══ WEBSITE-FIRST DESIGN (when auth=false — ALL energy goes here) ═══
When the project has no login/auth, the entire codebase budget goes to making the website breathtaking:
• Hero section: full-viewport, stunning gradient background (mesh gradient or multi-stop), large bold headline, animated subtitle, clear CTA button with glow effect
• Smooth scroll navigation: sticky glassmorphism navbar (backdrop-filter: blur), active-link highlighting
• Sections animate in on scroll: use Intersection Observer or framer-motion for fade-up/slide-in
• Feature cards: glass morphism style, icon + title + description, hover lifts card with colored glow shadow
• Interactive elements: hover states on ALL clickable things, smooth color transitions (transition: all 0.3s ease)
• Gradient text: use background-clip: text for headings in brand colors
• Floating/parallax elements: subtle background shapes that move on scroll or have float animation
• Section spacing: generous padding (100px+ sections), clear visual hierarchy
• Dark theme: deep dark background (#0a0a0f or similar) with vibrant accent colors
• Animated counter numbers, typewriter effects, or particle backgrounds when appropriate
• Mobile hamburger menu with smooth slide-in animation

═══ ANIMATIONS & TRANSITIONS (mandatory — not optional) ═══
• @keyframes: fadeInUp, fadeInLeft, slideDown, float, pulse, shimmer, gradientShift — define ALL of them
• .animate-fade-in-up: opacity 0→1 + translateY(30px→0), 0.6s ease, staggered delays for children
• .animate-float: infinite up-down float (translateY -10px to 10px, 3s ease-in-out infinite)
• .animate-gradient: background-position shift for animated gradient backgrounds
• CSS scroll-driven animations: @keyframes + animation-timeline: scroll() for parallax
• Hover transitions: cards (translateY -8px + shadow boost), buttons (scale 1.05 + glow), nav links (color + underline slide)
• Page load: hero content fades in with stagger — headline first (0s), subtitle (0.2s), CTA (0.4s), image/visual (0.6s)
• Smooth scroll: html {{ scroll-behavior: smooth }} + section padding-top for fixed navbar offset

═══ FRONTEND QUALITY (Lovable-level UI) ═══
• Every list/data page: loading skeleton → error state → empty state (icon+CTA) → cards/table
• Responsive: mobile-first, hamburger menu, works at 320px and 1440px
• Professional typography: Inter or Geist font via @import, proper h1→h6 scale
• Color palette: intentional, 2-3 accent colors max, consistent throughout
• Every button has: hover state, active scale(0.97), focus ring, disabled state
• Toast/notification for all user feedback

═══ CSS QUALITY (400+ lines for website-first projects) ═══
• @import Google Fonts (Inter, Poppins, or Geist)
• :root with full design token set (20+ CSS variables: colors, gradients, spacing, radius, shadow, transition)
• Animated gradient background: @keyframes gradientShift + background-size: 400%
• All @keyframes animations defined at top of file
• Glass morphism utility: .glass {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); }}
• Gradient text utility: .gradient-text {{ background: linear-gradient(...); -webkit-background-clip: text; color: transparent; }}
• Hero: .hero with full viewport height, centered content, layered background
• Navbar: .navbar with position: sticky, backdrop-filter, transition on scroll class
• Section: generous padding, .section-title with gradient underline
• Feature cards: .feature-card with hover lift + glow shadow
• All button states: .btn with gradient, :hover (scale+brightness), :active (scale 0.97), :focus-visible (ring)
• Responsive: @media (max-width: 768px) and (max-width: 480px) for ALL components

═══ FORMS (auth projects only — react-hook-form + zod) ═══
• ALL forms use react-hook-form with zodResolver
• Zod validates every field with clear error messages
• Submit button: disabled + spinner while isSubmitting
• On success: clear form + toast + navigate; on error: show server message

═══ STATE MANAGEMENT (Zustand) ═══
• All shared state in Zustand stores — zero prop drilling
• Follow EXACT CRUD PATTERNS above — every store has: items[], isLoading, error, fetchAll, create, update, remove
• Pages: call store.fetchAll() in useEffect(()=>{{ fetchAll() }}, [fetchAll])
• Forms: call store.create(data) or store.update(id,data) in react-hook-form onSubmit handler
• Optimistic updates: update local state immediately after successful API call (already shown in pattern above)

═══ BACKEND QUALITY ═══
• Correct HTTP codes: 200, 201, 204, 400, 401, 404, 422
• JWT auth via Depends(get_current_user) on every protected endpoint (auth projects)
• Public endpoints (no auth) for website-first projects
• ALL route functions are async def — no sync def in FastAPI routes
• All MongoDB operations use motor (async): await collection.find_one(), await collection.insert_one()
• Return Pydantic models (response_model=), never raw dicts from routes
• Error handling: try/except around DB calls, raise HTTPException with clear detail string
• Never return passwords or hashed_password in any response schema
• models.py: use Optional[str] = None for nullable fields, datetime = Field(default_factory=datetime.utcnow)
• config.py: use pydantic-settings BaseSettings, read from .env file
• database.py: motor AsyncIOMotorClient, async connect_db() / disconnect_db() for lifespan events

{specific_instructions}

═══ SELF-VERIFICATION (run through before writing any <file> tag) ═══
Mentally scan every file you are about to generate and fix these before outputting:
□ Frontend JSX: every <ComponentName /> — imported at the top of that file?
□ Frontend CSS: every className="..." — is it in the CSS CLASS CONTRACT list? No invented class names.
□ Frontend: every <button> — has a real onClick body? Not onClick={{() => {{}}}}?
□ Frontend: every .map() — has key={{item.id ?? item._id}}?
□ Frontend: useNavigate, Link, NavLink — imported from 'react-router-dom'?
□ Frontend: useState, useEffect, useCallback, useRef — imported from 'react'?
□ Frontend: every store hook — imported from correct relative path (../stores/X or ../../stores/X)?
□ Frontend: main.tsx — has `import './index.css'` (mandatory)?
□ Frontend: class= → className=, for= → htmlFor= (JSX attribute names)?
□ Backend: every route function — `async def`, not `def`?
□ Backend: every db.collection operation — has `await`?
□ Backend: every response — maps _id → id (no raw MongoDB _id exposed)?
□ Backend: login failure → 401, duplicate email → 409, not found → 404?
□ Backend: main.py — every entity router registered with app.include_router()?
□ Both: zero `pass`, `TODO`, `# implement`, empty function bodies?
Fix every failure before writing the output.

═══ OUTPUT FORMAT (strict) ═══
Return EACH file in XML tags — no markdown fences, no explanation:
<file path="exact/path/here">
complete file content here
</file>

Generate all {n_files} file(s) now:"""


_SPECIFIC_INSTRUCTIONS = {
    "security.py": """\
SECURITY.PY — exact pattern required (no passlib, bcrypt directly, lazy circular import):
  import bcrypt as _bcrypt_lib
  from jose import JWTError, jwt
  from fastapi import Depends, HTTPException
  from fastapi.security import OAuth2PasswordBearer
  from datetime import datetime, timedelta
  from app.config import settings
  from app.database import get_database

  oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

  def verify_password(plain: str, hashed: str) -> bool:
      return _bcrypt_lib.checkpw(plain.encode()[:72], hashed.encode())

  def get_password_hash(password: str) -> str:
      return _bcrypt_lib.hashpw(password.encode()[:72], _bcrypt_lib.gensalt()).decode()

  def create_access_token(data: dict, expires_delta=None):
      to_encode = data.copy()
      expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
      to_encode["exp"] = expire
      return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

  async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_database)):
      exc = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
      try:
          payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
          user_id = payload.get("sub")
          if not user_id: raise exc
      except JWTError:
          raise exc
      from app.services.user_service import get_user_by_id  # lazy import — prevents circular
      user = await get_user_by_id(db, user_id)
      if not user: raise exc
      return user""",

    "api.ts": """\
API.TS — exact interceptor pattern (reads from 'auth-storage-v2'):
  import axios from 'axios';
  const api = axios.create({ baseURL: '/api', timeout: 15000 });
  const STORAGE_KEY = 'auth-storage-v2';
  api.interceptors.request.use((config) => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) { const token = JSON.parse(raw)?.state?.token; if (token) config.headers.Authorization = `Bearer ${token}`; }
    } catch {}
    return config;
  });
  api.interceptors.response.use((r) => r, (err) => {
    if (err.response?.status === 401) { localStorage.removeItem(STORAGE_KEY); window.location.href = '/login'; }
    return Promise.reject(err);
  });
  export default api;""",

    "authStore.ts": """\
AUTH STORE — persist name='auth-storage-v2', partialize MUST exclude isLoading/error.
Full interface required:
  interface AuthState {
    user: User | null; token: string | null; isAuthenticated: boolean;
    isLoading: boolean; error: string | null;
    login: (email: string, password: string) => Promise<void>;
    register: (data: RegisterData) => Promise<void>;
    logout: () => void; fetchMe: () => Promise<void>;
  }
  persist(..., { name: 'auth-storage-v2', partialize: (s) => ({ token: s.token, user: s.user, isAuthenticated: s.isAuthenticated }) })""",

    "main.py": """\
MAIN.PY — file is at backend/main.py (NOT inside app/). CORS includes 5959. Register ALL entity routers.
  from fastapi import FastAPI
  from fastapi.middleware.cors import CORSMiddleware
  from app.database import connect_db, disconnect_db
  from app.routes import auth  # import every route module

  app = FastAPI(title="...", version="1.0.0")
  app.add_middleware(CORSMiddleware,
      allow_origins=["http://localhost:5959","http://localhost:5173","http://localhost:3000"],
      allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

  @app.on_event("startup")
  async def startup(): await connect_db()
  @app.on_event("shutdown")
  async def shutdown(): await disconnect_db()

  app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
  # include ALL entity routers here

  @app.get("/health")
  async def health(): return {"status": "ok"}""",

    "vite.config.ts": """\
VITE CONFIG — port 5959, proxy /api → 7979, @/ path alias:
  import { defineConfig } from 'vite'
  import react from '@vitejs/plugin-react'
  import path from 'path'
  export default defineConfig({
    plugins: [react()],
    resolve: { alias: { '@': path.resolve(__dirname, './src') } },
    server: { port: 5959, proxy: { '/api': { target: 'http://localhost:7979', changeOrigin: true } } },
  })""",

    "HomePage.tsx": """\
HOMEPAGE.TSX — stunning landing page, every button and interaction fully working:
  Import Navbar, Footer, and all section components. Wrap in <div> with Navbar at top, <main>, Footer at bottom.
  Section IDs: id="hero" id="features" id="how-it-works" id="testimonials" id="cta" — Navbar scrollTo uses these.
  CTA buttons in HeroSection: primary → scrolls to #features or #cta, secondary → scrolls to #how-it-works.
  "Get Started" / "Try Free" / "Learn More" buttons MUST all call scrollIntoView or navigate — never dead.
  HeroSection: full-viewport, two CTA buttons with real onClick, floating blobs, stats row with real numbers.
  FeaturesSection: 6 cards, each icon from lucide-react is a REAL import (Zap, Shield, BarChart, etc.).
  HowItWorksSection: 3 numbered steps, each step has a title and 2-3 sentences of real content.
  TestimonialsSection: 3 real testimonials with name, role, company, 1-2 sentence quote.
  CTASection: big CTA with onClick that scrolls to #hero or navigates — never a no-op.
  ALL sections: use Intersection Observer or framer-motion for scroll-triggered fade-in animation.
  Section components accept NO required props — all content is self-contained.""",

    "HeroSection.tsx": """\
HEROSECTION.TSX — the most important component, must be breathtaking:
  Full viewport height (min-height: 100vh), centered flex layout.
  Background: layered mesh gradient using multiple radial-gradient() + animated gradient shift.
  Layout: two-column on desktop (text left, visual right), single column centered on mobile.
  Headline: large (font-size: clamp(2.5rem, 6vw, 5rem)), bold, gradient-text class.
  Animated subtitle: typewriter or fade-in, muted color, 1.5rem.
  CTA buttons: primary (gradient background, box-shadow glow on hover), secondary (glass border).
  Hero visual: stylized product mockup, dashboard screenshot, or abstract 3D-ish CSS art — NOT a placeholder image.
  Floating blobs: 3 absolutely positioned divs with border-radius: 50%, blur(80px), float animation, opacity 0.3.
  Stats row below: 3 numbers (e.g. "10K+ Users", "99.9% Uptime", "50+ Features") with animated count-up feel.
  Fully responsive: on mobile, visual stacks below text, font sizes scale down.""",

    "FeaturesSection.tsx": """\
FEATURESSECTION.TSX — polished feature showcase:
  Section title with gradient underline, centered subtitle.
  6 feature cards in a 3-column grid (2 on tablet, 1 on mobile).
  Each card: glass morphism (.glass class), icon container with gradient background, icon from lucide-react,
    bold title, 2-sentence description.
  On hover: translateY(-8px), box-shadow with colored glow matching icon color.
  Scroll animation: cards fade-in-up with 0.1s stagger delay per card (nth-child delays).
  Colors: each card's icon container has a different gradient (purple, blue, green, orange, pink, teal).""",

    "Navbar.tsx": """\
NAVBAR.TSX — sticky glassmorphism navigation, ALL interactions implemented:
  const [isScrolled, setIsScrolled] = useState(false)
  const [isMobileOpen, setIsMobileOpen] = useState(false)
  useEffect(() => {
    const handler = () => setIsScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }, [])
  const scrollTo = (id: string) => { document.getElementById(id)?.scrollIntoView({{behavior:'smooth'}}); setIsMobileOpen(false) }
  Nav links MUST use onClick={{() => scrollTo('section-id')}} — NEVER <a href="#section"> dead anchors.
  CTA button: onClick={{() => scrollTo('cta')}} or onClick={{() => navigate('/signup')}} — fully working.
  Hamburger: onClick={{() => setIsMobileOpen(prev => !prev)}}, icon switches between Menu and X (lucide-react).
  Mobile menu: className={{`mobile-menu ${{isMobileOpen ? 'open' : ''}}`}}, each link calls scrollTo and closes menu.
  position: sticky top-0, z-index: 100, backdrop-filter: blur(20px).
  className={{`navbar ${{isScrolled ? 'scrolled' : ''}}`}} — .scrolled adds more background opacity.""",

    "index.css": """\
INDEX.CSS [MODE:WEBSITE-FIRST] — pure landing page CSS, 500+ lines. Include ALL:
  @import Google Fonts Inter or Poppins (300 400 500 600 700 900)
  :root — 30+ variables: --color-primary #6366f1, --color-secondary, --color-accent, --color-bg #0a0a0f,
    --color-surface #111118, --color-text #f8fafc, --color-muted #94a3b8, --color-border rgba(255,255,255,0.1),
    --gradient-primary, --gradient-hero, --gradient-card,
    --radius-sm/md/lg/xl/full, --shadow-sm/md/lg/glow, --transition-fast 0.15s/--transition-base 0.3s/--transition-slow 0.6s
  @keyframes: fadeInUp fadeInLeft fadeInRight slideDown float gradientShift shimmer scaleIn pulse glow spin
  Utility: .animate-fade-in-up .delay-100→.delay-600 .animate-float .animate-scale-in .gradient-text .glass .container
  .navbar: sticky top-0 backdrop-filter blur(20px) z-index:100; .navbar.scrolled increases bg opacity
  .hamburger: 3-bar → X animation; .mobile-menu .mobile-menu.open: slide-down transition
  .hero: min-height:100vh flex center relative overflow:hidden; .hero-content .hero-visual .hero-stats
  .hero-blob: position:absolute border-radius:50% filter:blur(80px) opacity:0.3 animate-float
  .stat-item: large gradient number, label below
  .section: padding:100px 0; .section-title gradient underline; .section-subtitle muted
  .features-grid: CSS grid 3-col→2→1; .feature-card glass hover(translateY -8px + glow); .icon-box gradient bg
  .steps-grid: numbered steps with connecting line; .step-number large gradient circle
  .testimonials-grid: 3-col→1; .testimonial-card glass; .testimonial-avatar gradient circle initials
  .cta-section: full-width alt gradient bg; .cta-content centered
  .footer .footer-grid .footer-col .footer-brand .footer-links .footer-bottom border-top
  .btn: gradient bg + glow shadow :hover(scale 1.05 brightness 1.1) :active(scale 0.97) :focus-visible(ring) :disabled(opacity 0.5)
  .btn-primary .btn-secondary(glass border) .btn-ghost .btn-sm .btn-lg
  Forms: .form-group .form-label .form-input(:focus ring) .form-error .form-hint
  .card .badge .modal-overlay .modal(scaleIn) .spinner(spin) .skeleton(shimmer)
  @media (max-width:1024px) (max-width:768px) (max-width:480px) — all sections responsive""",

    "index.css_auth": """\
INDEX.CSS [MODE:AUTH-APP] — full app UI CSS, 500+ lines. Every class listed MUST be defined.
  @import Google Fonts Inter (300 400 500 600 700)
  :root — 25+ variables: --color-primary #6366f1, --color-bg #0f0f17, --color-surface #1a1a2e,
    --color-surface-2 #16213e, --color-text #f1f5f9, --color-muted #64748b, --color-border #2d2d44,
    --color-error #ef4444, --color-success #22c55e, --color-warning #f59e0b,
    --gradient-primary linear-gradient(135deg,#6366f1,#8b5cf6),
    --radius-sm 4px --radius-md 8px --radius-lg 12px --radius-xl 16px --radius-full 9999px,
    --shadow-sm --shadow-md --shadow-lg --transition-base 0.2s ease --transition-fast 0.15s ease
  @keyframes: fadeInUp(translateY 20px→0 opacity 0→1) scaleIn(scale 0.95→1) shimmer spin slideDown pulse
  * box-sizing:border-box margin:0 padding:0
  body: font-family Inter bg:var(--color-bg) color:var(--color-text) min-height:100vh
  scrollbar: width:6px track:var(--color-surface) thumb:var(--color-border)

  AUTH PAGES (must work with LoginPage.tsx + RegisterPage.tsx):
    .auth-page: min-height:100vh display:flex align-items:center justify-content:center bg:var(--color-bg) padding:1rem
    .auth-card: background:var(--color-surface) border:1px solid var(--color-border) border-radius:var(--radius-xl)
      padding:2.5rem width:100% max-width:420px box-shadow:var(--shadow-lg)
    .auth-title: font-size:1.75rem font-weight:700 margin-bottom:0.5rem
    .auth-subtitle: color:var(--color-muted) font-size:0.95rem margin-bottom:2rem
    .auth-switch: text-align:center margin-top:1.5rem color:var(--color-muted) font-size:0.9rem
    .auth-switch a: color:var(--color-primary) text-decoration:none font-weight:500 :hover underline
    .error-message: background:rgba(239,68,68,0.1) border:1px solid rgba(239,68,68,0.3)
      color:#fca5a5 border-radius:var(--radius-md) padding:0.75rem 1rem font-size:0.875rem margin-bottom:1rem

  FORMS (.form-* classes used by LoginPage RegisterPage and all entity forms):
    .form-group: margin-bottom:1.25rem
    .form-label: display:block font-size:0.875rem font-weight:500 margin-bottom:0.4rem color:var(--color-text)
    .form-input: width:100% padding:0.65rem 0.9rem background:var(--color-surface-2) border:1px solid var(--color-border)
      border-radius:var(--radius-md) color:var(--color-text) font-size:0.95rem outline:none transition:border-color 0.2s
      :focus border-color:var(--color-primary) box-shadow:0 0 0 3px rgba(99,102,241,0.15)
      ::placeholder color:var(--color-muted)
      .form-input.error: border-color:var(--color-error)
    .form-error: color:var(--color-error) font-size:0.8rem margin-top:0.3rem display:block
    .form-hint: color:var(--color-muted) font-size:0.8rem margin-top:0.3rem

  BUTTONS (.btn must work for ALL components — auth forms, CRUD pages, modals):
    .btn: display:inline-flex align-items:center gap:0.4rem padding:0.6rem 1.2rem border-radius:var(--radius-md)
      font-size:0.9rem font-weight:500 border:none cursor:pointer transition:all var(--transition-base)
      :hover scale(1.02) :active scale(0.98) :focus-visible outline:2px solid var(--color-primary) outline-offset:2px
      :disabled opacity:0.5 cursor:not-allowed pointer-events:none
    .btn-primary: background:var(--gradient-primary) color:white :hover brightness(1.1) box-shadow:0 0 20px rgba(99,102,241,0.4)
    .btn-secondary: background:transparent border:1px solid var(--color-border) color:var(--color-text) :hover border-color:var(--color-primary)
    .btn-ghost: background:transparent color:var(--color-muted) :hover color:var(--color-text) background:var(--color-surface)
    .btn-danger: background:rgba(239,68,68,0.15) color:#fca5a5 border:1px solid rgba(239,68,68,0.3) :hover background:rgba(239,68,68,0.25)
    .btn-full: width:100% justify-content:center
    .btn-sm: padding:0.4rem 0.8rem font-size:0.8rem
    .btn-lg: padding:0.75rem 1.5rem font-size:1rem
    .btn-loading: opacity:0.7 cursor:wait

  APP LAYOUT (sidebar + main used by all authenticated pages):
    .app-layout: display:flex min-height:100vh
    .sidebar: width:260px background:var(--color-surface) border-right:1px solid var(--color-border)
      display:flex flex-direction:column flex-shrink:0 position:fixed height:100vh overflow-y:auto z-index:50
    .sidebar-brand: padding:1.5rem 1rem display:flex align-items:center gap:0.75rem border-bottom:1px solid var(--color-border)
    .sidebar-brand h1: font-size:1.25rem font-weight:700 background:var(--gradient-primary) -webkit-background-clip:text color:transparent
    .sidebar-nav: padding:1rem 0 flex:1
    .sidebar-link: display:flex align-items:center gap:0.75rem padding:0.65rem 1rem margin:0.1rem 0.5rem
      border-radius:var(--radius-md) color:var(--color-muted) text-decoration:none font-size:0.9rem
      transition:all var(--transition-fast) cursor:pointer border:none background:transparent width:calc(100% - 1rem)
      :hover background:var(--color-surface-2) color:var(--color-text)
    .sidebar-link.active: background:rgba(99,102,241,0.15) color:var(--color-primary) font-weight:500
    .main-content: margin-left:260px flex:1 padding:2rem min-height:100vh

  HEADER:
    .header: display:flex align-items:center justify-content:space-between padding:1rem 2rem
      background:var(--color-surface) border-bottom:1px solid var(--color-border) sticky top-0 z-index:40
    .header-title: font-size:1.1rem font-weight:600
    .user-menu: display:flex align-items:center gap:0.75rem
    .user-avatar: width:36px height:36px border-radius:50% background:var(--gradient-primary)
      display:flex align-items:center justify-content:center font-weight:600 font-size:0.85rem

  DASHBOARD:
    .dashboard-grid: display:grid grid-template-columns:repeat(auto-fit,minmax(220px,1fr)) gap:1rem margin-bottom:2rem
    .stat-card: background:var(--color-surface) border:1px solid var(--color-border) border-radius:var(--radius-lg)
      padding:1.5rem display:flex align-items:center gap:1rem
    .stat-icon: width:48px height:48px border-radius:var(--radius-md) display:flex align-items:center justify-content:center
    .stat-value: font-size:1.75rem font-weight:700
    .stat-label: font-size:0.85rem color:var(--color-muted) margin-top:0.25rem

  DATA PAGES:
    .page-header: display:flex align-items:center justify-content:space-between margin-bottom:1.5rem
    .page-header h1: font-size:1.5rem font-weight:700
    .data-grid: display:grid grid-template-columns:repeat(auto-fill,minmax(300px,1fr)) gap:1rem
    .card: background:var(--color-surface) border:1px solid var(--color-border) border-radius:var(--radius-lg)
      padding:1.25rem transition:all var(--transition-base)
      :hover border-color:var(--color-primary) transform:translateY(-2px) box-shadow:var(--shadow-md)
    .card-header: display:flex justify-content:space-between align-items:flex-start margin-bottom:0.75rem
    .card-actions: display:flex gap:0.5rem
    .badge: padding:0.25rem 0.6rem border-radius:var(--radius-full) font-size:0.75rem font-weight:500
    .badge-success: background:rgba(34,197,94,0.15) color:#4ade80
    .badge-warning: background:rgba(245,158,11,0.15) color:#fbbf24
    .badge-danger: background:rgba(239,68,68,0.15) color:#f87171
    .badge-info: background:rgba(99,102,241,0.15) color:#818cf8

  MODAL:
    .modal-overlay: position:fixed inset:0 background:rgba(0,0,0,0.7) display:flex align-items:center justify-content:center
      z-index:1000 backdrop-filter:blur(4px) animation:fadeInUp 0.2s ease
    .modal: background:var(--color-surface) border:1px solid var(--color-border) border-radius:var(--radius-xl)
      padding:2rem width:90% max-width:520px animation:scaleIn 0.2s ease
    .modal-header: display:flex justify-content:space-between align-items:center margin-bottom:1.5rem
    .modal-footer: display:flex gap:0.75rem justify-content:flex-end margin-top:1.5rem

  UTILITY:
    .loading-state: display:flex align-items:center justify-content:center padding:4rem
    .error-state: background:rgba(239,68,68,0.1) border:1px solid rgba(239,68,68,0.2) border-radius:var(--radius-md)
      padding:1rem color:#fca5a5 margin-bottom:1rem
    .empty-state: text-align:center padding:4rem 2rem color:var(--color-muted)
    .spinner: width:36px height:36px border:3px solid var(--color-border) border-top-color:var(--color-primary)
      border-radius:50% animation:spin 0.8s linear infinite
    .spinner-sm: width:16px height:16px border-width:2px
    .skeleton: background:linear-gradient(90deg,var(--color-surface) 25%,var(--color-surface-2) 50%,var(--color-surface) 75%)
      background-size:200% height:1em border-radius:var(--radius-sm) animation:shimmer 1.5s infinite

  @media (max-width:768px): .sidebar width:100% position:relative height:auto; .main-content margin-left:0;
    .dashboard-grid grid-template-columns:1fr 1fr; .data-grid grid-template-columns:1fr; .modal max-width:95%""",

    "main.tsx": """\
MAIN.TSX — entry point, must import CSS and wrap correctly:
  import React from 'react'
  import ReactDOM from 'react-dom/client'
  import { BrowserRouter } from 'react-router-dom'
  import App from './App'
  import './index.css'   ← THIS LINE IS MANDATORY — without it NO CSS loads

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>
  )

  NEVER put BrowserRouter in App.tsx — it belongs here in main.tsx only.""",

    "auth.py": """\
AUTH.PY — FastAPI auth routes, exact error codes (no 404 for auth failures):
  from fastapi import APIRouter, Depends, HTTPException, status
  from app.database import get_database; from app.schemas import LoginRequest, RegisterRequest, AuthResponse, UserResponse
  from app.utils.security import verify_password, get_password_hash, create_access_token

  router = APIRouter()

  @router.post("/register", response_model=AuthResponse, status_code=201)
  async def register(body: RegisterRequest, db=Depends(get_database)):
      existing = await db.users.find_one({"email": body.email})
      if existing: raise HTTPException(status_code=409, detail="Email already registered")
      hashed = get_password_hash(body.password)
      doc = {"email": body.email, "name": body.name, "hashed_password": hashed, "is_active": True, "created_at": datetime.utcnow()}
      result = await db.users.insert_one(doc)
      user = await db.users.find_one({"_id": result.inserted_id})
      token = create_access_token({"sub": str(user["_id"])})
      return {"access_token": token, "token_type": "bearer", "user": {"id": str(user["_id"]), "email": user["email"], "name": user["name"], "created_at": user["created_at"]}}

  @router.post("/login", response_model=AuthResponse)
  async def login(body: LoginRequest, db=Depends(get_database)):
      user = await db.users.find_one({"email": body.email})
      if not user or not verify_password(body.password, user["hashed_password"]):
          raise HTTPException(status_code=401, detail="Invalid email or password")  ← MUST be 401 not 404
      token = create_access_token({"sub": str(user["_id"])})
      return {"access_token": token, "token_type": "bearer", "user": {"id": str(user["_id"]), "email": user["email"], "name": user["name"], "created_at": user["created_at"]}}

  @router.get("/me", response_model=UserResponse)
  async def get_me(current_user=Depends(get_current_user)):
      return {"id": str(current_user["_id"]), "email": current_user["email"], "name": current_user["name"], "created_at": current_user["created_at"]}

  CRITICAL: login returns 401 for wrong credentials — NEVER 404. register returns 409 for duplicate email.""",

    "globals.css": """\
GLOBALS.CSS for Next.js — Tailwind + complete CSS variables + custom components:
  @tailwind base; @tailwind components; @tailwind utilities;
  @layer base { :root { --color-primary: ...; all CSS variables } }
  @layer components { .btn { @apply ... }, .card { @apply ... }, .input { @apply ... } }
  Also: smooth scrolling, ::selection color, scrollbar styling.""",

    "App.tsx": """\
APP.TSX — decide based on auth flag in PROJECT SPEC:

IF auth=true: full protected routing:
  import {{ Routes, Route, Navigate }} from 'react-router-dom'
  import {{ useAuthStore }} from './stores/authStore'
  // ProtectedRoute wrapper:
  const ProtectedRoute = ({{ children }}: {{ children: React.ReactNode }}) => {{
    const isAuthenticated = useAuthStore(s => s.isAuthenticated)
    return isAuthenticated ? <>{{children}}</> : <Navigate to="/login" replace />
  }}
  // Layout wrapper for authenticated pages (Header + Sidebar + <Outlet>)
  // Routes: / → <Navigate to="/dashboard">, /login, /register, /dashboard (protected), /ENTITY (protected)
  // EVERY entity page listed in project spec MUST have a Route here

IF auth=false: website routing only (NO login/register routes):
  import {{ Routes, Route }} from 'react-router-dom'
  // Routes: / → HomePage, /ENTITY → ENTITYPage (if entity pages exist)
  // NO ProtectedRoute, NO authStore import, NO /login or /register routes
  // Wrap in a single layout div — Navbar at top imported directly in App.tsx (NOT per-page)""",

    "Button.tsx": """\
BUTTON.TSX — reusable button, all variants fully styled and working:
  interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
    size?: 'sm' | 'md' | 'lg'
    isLoading?: boolean
    leftIcon?: React.ReactNode
    rightIcon?: React.ReactNode
  }
  export default function Button({ variant='primary', size='md', isLoading=false, leftIcon, rightIcon, children, disabled, className, ...props }: ButtonProps) {
    return (
      <button
        className={`btn btn-${variant} btn-${size} ${isLoading ? 'btn-loading' : ''} ${className ?? ''}`}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading ? <span className="spinner-sm" /> : leftIcon}
        {children}
        {!isLoading && rightIcon}
      </button>
    )
  }
  CSS classes .btn .btn-primary .btn-secondary .btn-ghost .btn-danger .btn-sm .btn-lg .btn-loading must be in index.css.""",

    "Header.tsx": """\
HEADER.TSX — top bar for authenticated app layout:
  import { useAuthStore } from '../../stores/authStore'
  import { useNavigate } from 'react-router-dom'
  import { LogOut, Bell, User } from 'lucide-react'
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const handleLogout = () => { logout(); navigate('/login') }
  Render:
    <header className="header">
      <div className="header-title">{{pageTitle from props or from location}}</div>
      <div className="user-menu">
        <div className="user-avatar">{{user?.name?.[0]?.toUpperCase()}}</div>
        <span className="user-name">{{user?.name}}</span>
        <button className="btn btn-ghost btn-sm" onClick={{handleLogout}}><LogOut size={{16}} /> Logout</button>
      </div>
    </header>
  Props: interface HeaderProps {{ title?: string }}
  All CSS classes (.header .user-menu .user-avatar) are defined in index.css.""",

    "Sidebar.tsx": """\
SIDEBAR.TSX — navigation sidebar for authenticated app layout:
  import { NavLink, useNavigate } from 'react-router-dom'
  import { useAuthStore } from '../../stores/authStore'
  import {{ LayoutDashboard, LogOut, [entity icons] }} from 'lucide-react'
  const {{ logout }} = useAuthStore()
  NavLink usage (gives .active class automatically):
    <NavLink to="/dashboard" className={{({{ isActive }}) => `sidebar-link ${{isActive ? 'active' : ''}}`}}>
      <LayoutDashboard size={{18}} /> Dashboard
    </NavLink>
  One NavLink per entity page. Logout button at bottom calls logout() then navigate('/login').
  Brand name at top in .sidebar-brand with gradient text.
  All CSS classes (.sidebar .sidebar-brand .sidebar-nav .sidebar-link .sidebar-link.active) defined in index.css.""",

    "user_service.py": """\
USER_SERVICE.PY — user CRUD used by auth routes and get_current_user:
  from bson import ObjectId
  from motor.motor_asyncio import AsyncIOMotorDatabase

  async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> dict | None:
      return await db.users.find_one({"email": email})

  async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: str) -> dict | None:
      try:
          return await db.users.find_one({"_id": ObjectId(user_id)})
      except Exception:
          return None

  async def create_user(db: AsyncIOMotorDatabase, email: str, name: str, hashed_password: str) -> dict:
      doc = {"email": email, "name": name, "hashed_password": hashed_password,
             "is_active": True, "created_at": datetime.utcnow()}
      result = await db.users.insert_one(doc)
      return await db.users.find_one({"_id": result.inserted_id})

  CRITICAL: get_user_by_id is called by security.py get_current_user — it MUST exist and return None (not raise) when user not found.""",

    "requirements.txt": """\
REQUIREMENTS.TXT — exact packages, no version conflicts:
  fastapi>=0.111.0
  uvicorn[standard]>=0.29.0
  motor>=3.4.0
  pymongo>=4.7.0
  pydantic>=2.7.0
  pydantic-settings>=2.3.0
  python-dotenv>=1.0.0
  python-multipart>=0.0.9
  If auth=true also add:
    python-jose[cryptography]>=3.3.0
    bcrypt>=4.1.0
  NEVER add passlib. NEVER add SQLAlchemy. NEVER pin to exact versions with == (use >=).""",

    "index.html": """\
INDEX.HTML — minimal Vite entry, id="root" required:
  <!DOCTYPE html>
  <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>{{Project Name}}</title>
    </head>
    <body>
      <div id="root"></div>
      <script type="module" src="/src/main.tsx"></script>
    </body>
  </html>
  NEVER add <link rel="stylesheet"> here — CSS is imported in main.tsx via `import './index.css'`.""",

    "DashboardPage.tsx": """\
DASHBOARDPAGE.TSX — real working dashboard, not a placeholder:
  Shows stats cards (total items, recent activity, key metrics) from real store data.
  Fetch data in useEffect: store.fetchAll() on mount.
  Stats cards: 4 cards with icon (lucide-react), label, value from actual data.
  Recent items table/list: last 5 items from store, with View/Edit buttons that navigate.
  Quick action buttons: "Create New" → navigate to create page or opens modal.
  All numbers from store.items.length, real calculations — no hardcoded "1,234".
  Loading skeleton while isLoading, error message if error, empty state with CTA if no data.""",

    "package.json": """\
PACKAGE.JSON — exact versions, all required deps present:
  dependencies MUST include: react@^18.3.1 react-dom@^18.3.1 react-router-dom@^6.26.0
    axios@^1.7.0 zustand@^4.5.0 lucide-react@^0.400.0 framer-motion@^11.0.0
  If auth: react-hook-form@^7.52.0 zod@^3.23.0 @hookform/resolvers@^3.9.0
  devDependencies: typescript@^5.5.0 vite@^5.4.0 @vitejs/plugin-react@^4.3.0
    @types/react@^18.3.0 @types/react-dom@^18.3.0 @types/node@^22.0.0
  scripts: "dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview"
  type: "module" MUST be present.""",

    "tsconfig.json": """\
TSCONFIG.JSON for React/Vite — MUST use project-references pattern (NOT a single flat config):
  Content: { "files": [], "references": [{"path": "./tsconfig.app.json"}, {"path": "./tsconfig.node.json"}] }
  This file MUST exist alongside tsconfig.app.json and tsconfig.node.json.""",

    "tsconfig.node.json": """\
TSCONFIG.NODE.JSON — config for vite.config.ts (required by project-references):
  { "compilerOptions": { "target": "ES2022", "lib": ["ES2023"], "module": "ESNext",
    "skipLibCheck": true, "moduleResolution": "bundler", "allowImportingTsExtensions": true,
    "isolatedModules": true, "moduleDetection": "force", "noEmit": true },
    "include": ["vite.config.ts"] }""",

    "tsconfig.app.json": """\
TSCONFIG.APP.JSON — compiler options for src/ files:
  { "compilerOptions": { "target": "ES2020", "useDefineForClassFields": true, "lib": ["ES2020","DOM","DOM.Iterable"],
    "module": "ESNext", "skipLibCheck": true, "moduleResolution": "bundler",
    "allowImportingTsExtensions": true, "isolatedModules": true, "noEmit": true,
    "jsx": "react-jsx", "strict": true, "paths": { "@/*": ["./src/*"] } },
    "include": ["src"] }""",

    "models.py": """\
MODELS.PY — Pydantic v2 + Motor MongoDB (NO PyObjectId class, NO bson imports here):
  from datetime import datetime
  from typing import Optional
  from pydantic import BaseModel, Field

  # Base models use plain str for id — route/service layer handles ObjectId ↔ str conversion
  class UserInDB(BaseModel):
      id: Optional[str] = None
      email: str; name: str; hashed_password: str
      is_active: bool = True
      created_at: datetime = Field(default_factory=datetime.utcnow)

  class EntityInDB(BaseModel):
      id: Optional[str] = None
      user_id: str; title: str
      description: Optional[str] = None
      created_at: datetime = Field(default_factory=datetime.utcnow)

  # Helper used in routes/services to convert MongoDB doc _id → id
  # def doc_to_dict(doc: dict) -> dict: return {{"id": str(doc["_id"]), **{{k:v for k,v in doc.items() if k!="_id"}}}}
  NEVER use SQLAlchemy. NEVER define PyObjectId. NEVER import bson here.""",

    "database.py": """\
DATABASE.PY — Motor MongoDB async connection, exact pattern (no variation):
  from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
  from app.config import settings

  _client: AsyncIOMotorClient | None = None

  async def connect_db() -> None:
      global _client
      _client = AsyncIOMotorClient(settings.MONGO_URL)

  async def disconnect_db() -> None:
      global _client
      if _client is not None:
          _client.close()
          _client = None

  def get_database() -> AsyncIOMotorDatabase:
      if _client is None:
          raise RuntimeError("Database not initialized — call connect_db() first")
      return _client[settings.DATABASE_NAME]

  NEVER use pymongo.MongoClient (sync) — always motor AsyncIOMotorClient.""",

    "config.py": """\
CONFIG.PY — pydantic-settings BaseSettings, reads .env automatically:
  from pydantic_settings import BaseSettings

  class Settings(BaseSettings):
      MONGO_URL: str = "mongodb://localhost:27017"
      DATABASE_NAME: str = "app_db"
      SECRET_KEY: str = "CHANGE-ME-USE-OPENSSL-RAND-HEX-32-IN-PRODUCTION"
      ALGORITHM: str = "HS256"
      ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

      model_config = {{"env_file": ".env", "case_sensitive": True}}

  settings = Settings()

  NEVER use os.getenv() or python-dotenv directly — pydantic-settings handles .env loading.
  NEVER put secrets inline in code — always read from environment.""",

    "schemas.py": """\
SCHEMAS.PY — Pydantic request/response schemas (separate from models.py):
  from pydantic import BaseModel, EmailStr, Field
  from typing import Optional; from datetime import datetime

  # Response schemas (what API returns — includes id: str, no _id, no password)
  class UserResponse(BaseModel):
      id: str; email: str; name: str; created_at: datetime

  class EntityResponse(BaseModel):
      id: str; title: str; description: Optional[str]; user_id: str; created_at: datetime

  # Request schemas (what API receives — no id, no user_id, no created_at)
  class CreateEntityRequest(BaseModel):
      title: str = Field(..., min_length=1, max_length=200)
      description: Optional[str] = Field(None, max_length=2000)

  class UpdateEntityRequest(BaseModel):
      title: Optional[str] = Field(None, min_length=1, max_length=200)
      description: Optional[str] = None

  # Auth schemas
  class LoginRequest(BaseModel): email: EmailStr; password: str
  class RegisterRequest(BaseModel): email: EmailStr; password: str = Field(..., min_length=8); name: str
  class AuthResponse(BaseModel): access_token: str; token_type: str = "bearer"; user: UserResponse

  IMPORTANT: Response schemas NEVER include hashed_password or password fields.""",

    "Footer.tsx": """\
FOOTER.TSX — complete, real footer (not a placeholder):
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({{behavior:'smooth'}})
  Sections in a 4-col grid (2-col tablet, 1-col mobile):
    Brand: logo text + tagline + social icon buttons (Github, Twitter, Linkedin from lucide-react) each with onClick opening external link in new tab
    Product: list of <button onClick={{()=>scrollTo('section-id')}}>Feature Name</button> links — never dead <a href="#">
    Company: 3-4 links (About, Blog, Careers, Contact) as <button> or real <a> with href
    Newsletter: <input type="email"> + <button>Subscribe</button> with useState for email value
  Bottom bar: full-width border-top, flex between "© {{new Date().getFullYear()}} BrandName" and "Privacy · Terms"
  All copyright links: real <button> or <a> elements — NEVER dead href="#"
  CSS: .footer .footer-grid .footer-col .footer-brand .footer-links .footer-bottom — must match index.css""",

    "LoginPage.tsx": """\
LOGINPAGE.TSX — react-hook-form + zod, fully working:
  import {{ useForm }} from 'react-hook-form'; import {{ zodResolver }} from '@hookform/resolvers/zod'; import {{ z }} from 'zod'
  import {{ useAuthStore }} from '../stores/authStore'; import {{ useNavigate, Link }} from 'react-router-dom'
  import {{ useEffect }} from 'react'

  const schema = z.object({{ email: z.string().email('Invalid email'), password: z.string().min(8,'Min 8 chars') }})
  type LoginForm = z.infer<typeof schema>

  export default function LoginPage() {{
    const {{ login, isLoading, error, isAuthenticated }} = useAuthStore()
    const navigate = useNavigate()
    const {{ register, handleSubmit, formState: {{ errors }} }} = useForm<LoginForm>({{ resolver: zodResolver(schema) }})
    useEffect(() => {{ if (isAuthenticated) navigate('/dashboard', {{ replace: true }}) }}, [isAuthenticated, navigate])
    const onSubmit = async (data: LoginForm) => {{ await login(data.email, data.password) }}
    return (
      <div className="auth-page"><div className="auth-card glass">
        <h1 className="auth-title">Welcome back</h1>
        {{error && <div className="error-message">{{error}}</div>}}
        <form onSubmit={{handleSubmit(onSubmit)}} noValidate>
          <div className="form-group">
            <label htmlFor="email" className="form-label">Email</label>
            <input id="email" type="email" className="form-input" placeholder="you@example.com" {{...register('email')}} />
            {{errors.email && <span className="form-error">{{errors.email.message}}</span>}}
          </div>
          <div className="form-group">
            <label htmlFor="password" className="form-label">Password</label>
            <input id="password" type="password" className="form-input" placeholder="••••••••" {{...register('password')}} />
            {{errors.password && <span className="form-error">{{errors.password.message}}</span>}}
          </div>
          <button type="submit" className="btn btn-primary btn-full" disabled={{isLoading}}>
            {{isLoading ? 'Signing in...' : 'Sign In'}}
          </button>
        </form>
        <p className="auth-switch">Don't have an account? <Link to="/register">Sign up</Link></p>
      </div></div>
    )
  }}""",

    "RegisterPage.tsx": """\
REGISTERPAGE.TSX — react-hook-form + zod, mirrors LoginPage pattern:
  Schema: name (min 2), email (valid email), password (min 8), confirmPassword must match password
  On submit: call authStore.register(data) → on success navigate to /dashboard
  Show server error from authStore.error
  Link back to /login at bottom
  Same .auth-page .auth-card .form-group .form-input .form-error CSS classes as LoginPage""",

    "HowItWorksSection.tsx": """\
HOWITWORKSSECTION.TSX — numbered steps, real content, working:
  3 steps in a responsive layout (horizontal on desktop with connecting line, vertical on mobile).
  Each step: large gradient number badge (1/2/3), icon from lucide-react, bold title, 2-3 sentence real description.
  Connecting line between steps: CSS ::before/::after with dashed border or gradient line.
  All text is SPECIFIC to the project domain — no generic "Step 1: Get started" placeholders.
  Intersection Observer: each step fades in left/right alternating with 0.2s stagger.
  Mobile: vertical timeline with left border line, steps stack below each other.""",

    "TestimonialsSection.tsx": """\
TESTIMONIALSSECTION.TSX — 3 real testimonials, glass cards:
  3 cards in responsive grid (3→2→1 columns). Each card:
    Top: Quote icon (lucide-react) + 4-5 star rating display (★ chars or lucide Star icons)
    Body: 2-3 sentence quote specific to the project domain — NOT generic praise
    Bottom: avatar circle (CSS gradient bg + initials from name), person name (bold), role + company
  Card style: glass morphism (.glass), subtle glow border on hover
  Intersection Observer: cards fade-in-up with stagger
  Section header: .gradient-text title + .section-subtitle centered above cards""",

    "CTASection.tsx": """\
CTASECTION.TSX — high-conversion final call-to-action:
  Full-width section with DIFFERENT gradient from hero (use secondary accent palette).
  Centered layout: small eyebrow badge, bold H2 (gradient-text), supporting line, 2 buttons.
  Primary button: onClick scrolls to #hero OR navigates to /signup — never a no-op.
  Secondary button: glass style, "View Demo" or "Learn More" → scrolls to #features.
  Subtle background: animated gradient or grid pattern overlay using CSS.
  Optional: floating decoration elements (star/sparkle icons from lucide-react, absolutely positioned).
  Intersection Observer fade-in animation on the content block.""",

    "_entity_route": """\
ENTITY ROUTE FILE — follow EXACT CRUD PATTERNS from the prompt above. Key requirements:
  • router = APIRouter() at top, imported in main.py as app.include_router(entity.router, prefix="/api/entities")
  • All 4 operations: GET / (list), POST / (create), PUT /{id} (update), DELETE /{id} (delete)
  • Every route: async def, Depends(get_database), Depends(get_current_user)
  • _id → id transformation on EVERY return value: {{"id": str(d["_id"]), **{{k:v for k,v in d.items() if k!="_id"}}}}
  • import ObjectId from bson at the top
  • Use response_model= on every route
  • HTTP status codes: list=200, create=201, update=200, delete=204""",

    "_entity_store": """\
ENTITY STORE FILE — follow EXACT CRUD PATTERNS from the prompt above. Key requirements:
  • Interface has: items: Entity[], isLoading: boolean, error: string | null
  • All 4 actions: fetchAll, create, update, remove — all async, all implemented
  • fetchAll: set isLoading true → api.get → set items → catch → set error → finally set isLoading false
  • create: api.post → prepend to items array (optimistic)
  • update: api.put → replace item in array by id
  • remove: api.delete → filter item out of array by id
  • Import Entity types from '@/types' or '../../types/index'
  • Import api from '@/services/api' or '../../services/api'
  • API path: use '/entities' (plural, matches backend router prefix minus /api)""",

    "_entity_page": """\
ENTITY PAGE FILE — complete CRUD page with all states:
  • Import store hook, LoadingSpinner, EmptyState, Button from correct relative paths
  • const {{ items, isLoading, error, fetchAll, remove }} = useEntityStore()
  • useEffect(() => {{ fetchAll() }}, []) — fetch on mount
  • Modal state: const [showForm, setShowForm] = useState(false); const [editing, setEditing] = useState<Entity|null>(null)
  • Render order: isLoading → LoadingSpinner; error → error div; items.length===0 → EmptyState with Create CTA; else → grid of cards
  • Each card: shows entity data, Edit button (sets editing+showForm), Delete button (confirm then remove(id))
  • Form modal: CreateEntityForm or inline form, calls store.create or store.update, closes on success
  • Page header: entity name title + "New Entity" button top-right
  • All className values must exist in index.css (page-header, grid, card, etc.)""",

    "_entity_service": """\
ENTITY SERVICE FILE — business logic layer between routes and MongoDB:
  • All functions async, accept db as first parameter
  • get_all(db, user_id: str) → List[dict]: find all docs for user, map _id→id
  • get_by_id(db, entity_id: str, user_id: str) → dict | None: find one, map _id→id
  • create(db, data: dict, user_id: str) → dict: insert_one, return created with id
  • update(db, entity_id: str, data: dict, user_id: str) → dict | None: find_one_and_update, return updated
  • delete(db, entity_id: str, user_id: str) → bool: delete_one, return deleted_count > 0
  • Always include user_id filter to prevent cross-user data access""",

    "Input.tsx": """\
INPUT.TSX — reusable form input with error display, used by all forms:
  interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
    label?: string
    error?: string
    hint?: string
    leftIcon?: React.ReactNode
  }
  export default function Input({ label, error, hint, leftIcon, id, className, ...props }: InputProps) {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="form-group">
        {label && <label htmlFor={inputId} className="form-label">{label}</label>}
        <div style={{ position: 'relative' }}>
          {leftIcon && <span style={{ position:'absolute', left:'0.75rem', top:'50%', transform:'translateY(-50%)', color:'var(--color-muted)' }}>{leftIcon}</span>}
          <input
            id={inputId}
            className={`form-input${error ? ' error' : ''} ${className ?? ''}`}
            style={leftIcon ? { paddingLeft: '2.5rem' } : undefined}
            {...props}
          />
        </div>
        {error && <span className="form-error">{error}</span>}
        {hint && !error && <span className="form-hint">{hint}</span>}
      </div>
    )
  }
  CSS classes .form-group .form-label .form-input .form-input.error .form-error .form-hint must be in index.css.""",

    "Modal.tsx": """\
MODAL.TSX — animated overlay modal, used by all CRUD forms:
  interface ModalProps {
    isOpen: boolean
    onClose: () => void
    title: string
    children: React.ReactNode
    footer?: React.ReactNode
    size?: 'sm' | 'md' | 'lg'
  }
  export default function Modal({ isOpen, onClose, title, children, footer, size = 'md' }: ModalProps) {
    useEffect(() => {
      const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
      if (isOpen) document.addEventListener('keydown', handler)
      return () => document.removeEventListener('keydown', handler)
    }, [isOpen, onClose])
    if (!isOpen) return null
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal" style={size === 'lg' ? { maxWidth: '700px' } : size === 'sm' ? { maxWidth: '380px' } : undefined}
             onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>{title}</h2>
            <button onClick={onClose} className="btn btn-ghost btn-sm" aria-label="Close">✕</button>
          </div>
          <div>{children}</div>
          {footer && <div className="modal-footer">{footer}</div>}
        </div>
      </div>
    )
  }
  Import useEffect from 'react'. CSS: .modal-overlay .modal .modal-header .modal-footer must be in index.css.""",

    "ErrorMessage.tsx": """\
ERRORMESSAGE.TSX — error display component for API/validation errors:
  interface ErrorMessageProps { message: string | null; onDismiss?: () => void }
  export default function ErrorMessage({ message, onDismiss }: ErrorMessageProps) {
    if (!message) return null
    return (
      <div className="error-message" role="alert">
        <span>{message}</span>
        {onDismiss && <button onClick={onDismiss} className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto' }}>✕</button>}
      </div>
    )
  }
  CSS: .error-message must be in index.css.""",

    "LoadingSpinner.tsx": """\
LOADINGSPINNER.TSX — centered loading indicator, used for page-level loading states:
  interface LoadingSpinnerProps { size?: 'sm' | 'md' | 'lg'; text?: string }
  export default function LoadingSpinner({ size = 'md', text }: LoadingSpinnerProps) {
    const spinnerClass = size === 'sm' ? 'spinner spinner-sm' : 'spinner'
    return (
      <div className="loading-state" style={{ flexDirection: 'column', gap: '1rem' }}>
        <div className={spinnerClass} />
        {text && <p style={{ color: 'var(--color-muted)', fontSize: '0.9rem' }}>{text}</p>}
      </div>
    )
  }
  CSS: .loading-state .spinner .spinner-sm must be in index.css.""",

    "EmptyState.tsx": """\
EMPTYSTATE.TSX — empty data placeholder with optional CTA, used by all entity pages:
  interface EmptyStateProps {
    title?: string
    description?: string
    action?: React.ReactNode
    icon?: React.ReactNode
  }
  export default function EmptyState({ title = 'Nothing here yet', description, action, icon }: EmptyStateProps) {
    return (
      <div className="empty-state">
        {icon && <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>{icon}</div>}
        <p style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.5rem' }}>{title}</p>
        {description && <p style={{ color: 'var(--color-muted)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>{description}</p>}
        {action && <div>{action}</div>}
      </div>
    )
  }
  CSS: .empty-state must be in index.css.""",
}


_validate_prompts()  # Crash at import if a prompt has unescaped { } — catches edits immediately


def _get_specific_instructions(file_paths: list[str], auth: bool = True) -> str:
    instructions = []
    seen: set[str] = set()
    # Inject auth-aware CSS instruction when index.css is in the batch
    for path in file_paths:
        fname = path.split("/")[-1].lower()
        if fname == "index.css" and "index.css_auth" not in seen:
            key = "index.css_auth" if auth else "index.css"
            if key in _SPECIFIC_INSTRUCTIONS and key not in seen:
                instructions.append(_SPECIFIC_INSTRUCTIONS[key])
                seen.add("index.css")
                seen.add("index.css_auth")
    for path in file_paths:
        fname = path.split("/")[-1].lower()
        p = path.lower().replace("\\", "/")
        for key, instruction in _SPECIFIC_INSTRUCTIONS.items():
            if key in seen:
                continue
            k = key.lower()
            # Exact filename match
            if fname == k or p.endswith("/" + k):
                instructions.append(instruction)
                seen.add(key)
            # Pattern: entity route files (backend/app/routes/ENTITY.py, not auth/__init__)
            elif k == "_entity_route" and re.search(r'backend/app/routes/(?!auth|__init__)\w+\.py$', p):
                instructions.append(instruction)
                seen.add(key)
            # Pattern: entity Zustand stores (not authStore)
            elif k == "_entity_store" and re.search(r'frontend/src/stores/(?!auth)\w+[Ss]tore\.ts$', p):
                instructions.append(instruction)
                seen.add(key)
            # Pattern: entity pages (not login/register/dashboard/home)
            elif k == "_entity_page" and re.search(r'frontend/src/pages/(?!login|register|dashboard|home)\w+[Pp]age\.tsx$', p):
                instructions.append(instruction)
                seen.add(key)
            # Pattern: entity service files
            elif k == "_entity_service" and re.search(r'backend/app/services/(?!user_service)\w+_service\.py$', p):
                instructions.append(instruction)
                seen.add(key)
    return "\n\n".join(instructions)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class OrchestratorAgent:
    """
    Lovable-style multi-call project generator.

    Phase 1: small planning call → file manifest (JSON)
    Phase 2: files generated in dependency-ordered groups (max 7 files/group)
             each group call has full 65K token budget + accumulated context
    """

    def __init__(self, llm_client: FallbackLLMClient, llm_options: LLMCallOptions) -> None:
        self._llm = llm_client
        self._opts = llm_options

    # ------------------------------------------------------------------
    # Phase 1: Structure planning
    # ------------------------------------------------------------------

    def _plan_structure(self, user_message: str, plan_steps: list[str], developer_plan: dict | None = None) -> dict:
        plan_str = "\n".join(f"- {s}" for s in plan_steps)
        # Inject rich planner output if available
        extra = ""
        if developer_plan:
            if developer_plan.get("interfaces"):
                iface_lines = []
                for iface in developer_plan["interfaces"][:8]:
                    iface_lines.append(f"  {iface['name']}: {{{', '.join(f'{k}: {v}' for k, v in iface.get('fields', {}).items())}}}")
                extra += "\n\nTYPESCRIPT INTERFACES (use exactly):\n" + "\n".join(iface_lines)
            if developer_plan.get("api_contracts"):
                route_lines = [f"  {r['method']} {r['path']}" for r in developer_plan["api_contracts"][:10]]
                extra += "\n\nAPI ROUTES (implement all):\n" + "\n".join(route_lines)
            if developer_plan.get("models"):
                model_lines = [f"  {m['name']} → collection: {m.get('collection', '?')}" for m in developer_plan["models"]]
                extra += "\n\nPYDANTIC MODELS:\n" + "\n".join(model_lines)
            if developer_plan.get("env_example"):
                extra += f"\n\nREQUIRED ENV VARS: {list(developer_plan['env_example'].keys())}"
        prompt = _STRUCTURE_PLAN_PROMPT.format(
            user_message=user_message + extra,
            plan_steps=plan_str,
        )
        planning_opts = LLMCallOptions(temperature=0.1, max_tokens=8192, timeout_seconds=120)
        result = self._llm.complete([ChatMessage(role="user", content=prompt)], planning_opts)
        raw = (result.text or "").strip()
        # Strip markdown fences
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        raw = raw.strip()
        try:
            spec = json.loads(raw)
            n_be = len(spec.get("backend_files", []))
            n_fe = len(spec.get("frontend_files", []))
            print(f"[Orchestrator] Planned {n_be} backend + {n_fe} frontend files")
            # Store developer_plan contracts in spec for file generation context
            if developer_plan:
                spec["_interfaces"] = developer_plan.get("interfaces", [])
                spec["_api_contracts"] = developer_plan.get("api_contracts", [])
                spec["_flow"] = developer_plan.get("flow", "")
                spec["_rules"] = developer_plan.get("rules", [])
                spec["_env_example"] = developer_plan.get("env_example", {})
            return spec
        except json.JSONDecodeError as e:
            print(f"[Orchestrator] Structure parse error: {e} — using fallback spec")
            return self._fallback_spec(user_message)

    def _fallback_spec(self, user_message: str) -> dict:
        return {
            "project_name": "App",
            "description": user_message,
            "stack": {"frontend": "react-vite", "backend": "fastapi", "database": "mongodb"},
            "auth": True,
            "entities": [],
            "api_routes": {"auth": ["POST /api/auth/register", "POST /api/auth/login"]},
            "backend_files": [
                {"path": "backend/requirements.txt", "description": "Python deps"},
                {"path": "backend/.env.example", "description": "Environment variables"},
                {"path": "backend/main.py", "description": "FastAPI app with CORS"},
                {"path": "backend/app/__init__.py", "description": "empty"},
                {"path": "backend/app/config.py", "description": "pydantic-settings"},
                {"path": "backend/app/database.py", "description": "Motor MongoDB"},
                {"path": "backend/app/models.py", "description": "MongoDB models"},
                {"path": "backend/app/schemas.py", "description": "Pydantic schemas"},
                {"path": "backend/app/utils/__init__.py", "description": "empty"},
                {"path": "backend/app/utils/security.py", "description": "bcrypt + JWT"},
                {"path": "backend/app/services/__init__.py", "description": "empty"},
                {"path": "backend/app/services/user_service.py", "description": "User CRUD"},
                {"path": "backend/app/routes/__init__.py", "description": "empty"},
                {"path": "backend/app/routes/auth.py", "description": "register/login"},
            ],
            "frontend_files": [
                {"path": "frontend/package.json", "description": "npm deps including react-hook-form zod @hookform/resolvers zustand axios lucide-react react-router-dom"},
                {"path": "frontend/vite.config.ts", "description": "port 5959, proxy /api→7979, @/ alias"},
                {"path": "frontend/tsconfig.json", "description": "TypeScript project references config"},
                {"path": "frontend/tsconfig.app.json", "description": "TypeScript compiler options for src/"},
                {"path": "frontend/tsconfig.node.json", "description": "TypeScript config for vite.config.ts"},
                {"path": "frontend/index.html", "description": "HTML entry point"},
                {"path": "frontend/src/types/index.ts", "description": "All TypeScript interfaces"},
                {"path": "frontend/src/services/api.ts", "description": "Axios instance with JWT interceptor"},
                {"path": "frontend/src/stores/authStore.ts", "description": "Zustand auth store persist auth-storage-v2"},
                {"path": "frontend/src/index.css", "description": "Complete design system CSS 250+ lines"},
                {"path": "frontend/src/App.tsx", "description": "React Router with ProtectedRoute wrapper"},
                {"path": "frontend/src/main.tsx", "description": "ReactDOM.createRoot entry"},
                {"path": "frontend/src/components/layout/Header.tsx", "description": "Header with nav and user menu"},
                {"path": "frontend/src/components/layout/Sidebar.tsx", "description": "Sidebar with nav items and active state"},
                {"path": "frontend/src/components/common/Button.tsx", "description": "Reusable button with variants"},
                {"path": "frontend/src/components/common/Input.tsx", "description": "Form input with error display"},
                {"path": "frontend/src/components/common/Modal.tsx", "description": "Animated modal dialog"},
                {"path": "frontend/src/components/common/LoadingSpinner.tsx", "description": "Loading spinner component"},
                {"path": "frontend/src/components/common/EmptyState.tsx", "description": "Empty state with icon and CTA"},
                {"path": "frontend/src/pages/LoginPage.tsx", "description": "Login form with react-hook-form + zod"},
                {"path": "frontend/src/pages/RegisterPage.tsx", "description": "Register form with react-hook-form + zod"},
                {"path": "frontend/src/pages/DashboardPage.tsx", "description": "Dashboard with stats and overview"},
            ],
        }

    # ------------------------------------------------------------------
    # Phase 2: Group assignment + generation
    # ------------------------------------------------------------------

    def _build_execution_plan(self, spec: dict) -> list[list[list[dict]]]:
        """
        Build execution tiers for parallel generation.
        Returns: list of tiers, each tier = list of batches to run in parallel.
        Batches in the same tier run concurrently; tiers run sequentially.
        """
        all_files = {
            **{f["path"]: f for f in spec.get("backend_files", [])},
            **{f["path"]: f for f in spec.get("frontend_files", [])},
        }

        raw_groups: dict[int, list[dict]] = {}
        for path, file_spec in all_files.items():
            g = _group_of(path)
            raw_groups.setdefault(g, []).append(file_spec)

        def split(files: list[dict]) -> list[list[dict]]:
            return [files[i:i + MAX_FILES_PER_GROUP] for i in range(0, len(files), MAX_FILES_PER_GROUP)]

        tiers: list[list[list[dict]]] = []
        processed: set[int] = set()

        for k in sorted(raw_groups.keys()):
            if k in processed:
                continue
            # Check if this group is part of a parallel set
            parallel_set = next((ps for ps in _PARALLEL_SETS if k in ps), None)
            if parallel_set:
                tier_batches: list[list[dict]] = []
                for partner in sorted(parallel_set):
                    if partner in raw_groups:
                        tier_batches.extend(split(raw_groups[partner]))
                        processed.add(partner)
                tiers.append(tier_batches)
            else:
                tiers.append(split(raw_groups[k]))
                processed.add(k)

        return tiers

    # Keep flat list version for compatibility
    def _generation_groups(self, spec: dict) -> list[list[dict]]:
        tiers = self._build_execution_plan(spec)
        return [batch for tier in tiers for batch in tier]

    def _generate_group(
        self,
        files: list[dict],
        spec: dict,
        generated: dict[str, str],
    ) -> dict[str, str]:
        if not files:
            return {}

        # Build entity→route mapping so frontend/backend files use consistent paths
        entity_routes: dict = {}
        for contract in spec.get("_api_contracts", []):
            parts = contract.get("path", "").split("/")
            if len(parts) >= 3:
                key = parts[2]  # e.g. "tasks" from /api/tasks
                entity_routes.setdefault(key, []).append(
                    f"{contract.get('method','GET')} {contract.get('path','')}"
                )

        spec_summary = json.dumps({
            "project_name": spec.get("project_name"),
            "description": spec.get("description"),
            "stack": spec.get("stack", {}),
            "auth": spec.get("auth"),
            "entities": spec.get("entities", []),
            "api_routes": spec.get("api_routes", {}),
            "entity_routes": entity_routes,
            "interfaces": spec.get("_interfaces", []),
            "api_contracts": spec.get("_api_contracts", []),
            "data_flow": spec.get("_flow", ""),
            "rules": spec.get("_rules", [])[:5],
        }, indent=2)

        context = _context_block(generated)
        auth = spec.get("auth", True)
        auth_mode = "AUTH-APP" if auth else "WEBSITE-FIRST"
        _CSS_FILES = {"index.css", "globals.css", "app.css", "main.css", "global.css"}
        _AUTH_FILES = {"auth.py", "loginpage.tsx", "registerpage.tsx", "authstore.ts", "security.py"}
        files_block_lines = []
        for f in files:
            desc = f["description"]
            fname = f["path"].split("/")[-1].lower()
            if fname in _CSS_FILES:
                desc = f"[MODE:{auth_mode}] {desc}"
            elif fname in _AUTH_FILES:
                desc = f"[AUTH-REQUIRED] {desc}"
            files_block_lines.append(f'- "{f["path"]}": {desc}')
        files_block = "\n".join(files_block_lines)
        specific = _get_specific_instructions([f["path"] for f in files], auth=auth)

        prompt = _FILE_GEN_PROMPT.format(
            project_spec=spec_summary,
            context=context if context else "(first group — no prior files yet)",
            n_files=len(files),
            files_to_generate=files_block,
            specific_instructions=specific or "(no extra instructions — follow general quality rules)",
        )

        messages = [ChatMessage(role="user", content=prompt)]
        result = self._llm.complete(messages, self._opts)
        raw = result.text or ""

        if not raw.strip():
            print(f"[Orchestrator] Empty response for group, retrying with simplified prompt")
            raw = self._retry_group(files, spec_summary, context)

        parsed = _extract_files(raw)

        # Single-file fallback: if the LLM didn't use tags but returned content
        if not parsed and len(files) == 1:
            cleaned = raw.strip()
            # Strip markdown fences
            cleaned = re.sub(r'^```\w*\n?', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'\n?```$', '', cleaned, flags=re.MULTILINE)
            parsed = {files[0]["path"]: cleaned.strip()}

        if parsed:
            print(f"[Orchestrator] Generated: {list(parsed.keys())}")
        else:
            print(f"[Orchestrator] WARNING: No output for {[f['path'] for f in files]}")

        return parsed

    def _retry_group(self, files: list[dict], spec_summary: str, context: str) -> str:
        """Simpler retry prompt when Gemini returns empty."""
        files_block = "\n".join(f'- "{f["path"]}": {f["description"]}' for f in files)
        specific = _get_specific_instructions([f["path"] for f in files])
        prompt = (
            f"Generate these files for a web application. "
            f"Project: {spec_summary[:500]}\n\n"
            f"Files:\n{files_block}\n\n"
            f"Previously generated context:\n{context[:10000]}\n\n"
            f"{specific}\n\n"
            f"Use <file path=\"path\">content</file> tags for each file. "
            f"Write complete, production-ready code."
        )
        result = self._llm.complete(
            [ChatMessage(role="user", content=prompt)],
            LLMCallOptions(temperature=0.1, max_tokens=32768, timeout_seconds=120),
        )
        return result.text or ""

    async def _generate_group_async(
        self,
        files: list[dict],
        spec: dict,
        generated: dict[str, str],
    ) -> dict[str, str]:
        return await asyncio.to_thread(self._generate_group, files, spec, generated)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_project(self, project_name: str, steps: list[str], user_message: str, developer_plan: dict | None = None) -> dict:
        print(f"[Orchestrator] Starting for: {project_name}")
        spec = self._plan_structure(user_message, steps, developer_plan)
        spec.setdefault("project_name", project_name)

        tiers = self._build_execution_plan(spec)
        total = sum(len(b) for tier in tiers for b in tier)
        print(f"[Orchestrator] {len(tiers)} tiers, {total} total files")

        generated: dict[str, str] = {}
        for t_idx, tier in enumerate(tiers):
            if not tier:
                continue
            if len(tier) == 1:
                # Single batch — run directly
                print(f"[Orchestrator] Tier {t_idx+1}: {[f['path'] for f in tier[0]]}")
                result = self._generate_group(tier[0], spec, generated)
                generated.update(result)
            else:
                # Multiple batches — run in parallel (each gets snapshot of current context)
                print(f"[Orchestrator] Tier {t_idx+1} PARALLEL: {len(tier)} batches")
                ctx_snapshot = dict(generated)
                with ThreadPoolExecutor(max_workers=min(len(tier), 2)) as pool:
                    futures = {
                        pool.submit(self._generate_group, batch, spec, ctx_snapshot): batch
                        for batch in tier
                    }
                    for fut in as_completed(futures):
                        try:
                            generated.update(fut.result())
                        except Exception as e:
                            print(f"[Orchestrator] Parallel batch failed: {e}")

        print(f"[Orchestrator] Completed: {len(generated)} files")
        return {"project_type": "fullstack", "structure": _flat_to_nested(generated)}

    async def astream_developer_text(
        self, project_name: str, steps: list[str], user_message: str, developer_plan: dict | None = None
    ) -> AsyncIterator[str]:
        """Yield progress text chunks + final JSON as the last chunk."""
        yield f"[Planning structure for: {project_name}]\n"

        spec = await asyncio.to_thread(self._plan_structure, user_message, steps, developer_plan)
        spec.setdefault("project_name", project_name)

        tiers = self._build_execution_plan(spec)
        total_files = sum(len(b) for tier in tiers for b in tier)
        yield f"[{len(tiers)} tiers, {total_files} files to generate]\n"

        generated: dict[str, str] = {}
        for t_idx, tier in enumerate(tiers):
            if not tier:
                continue
            if len(tier) == 1:
                batch = tier[0]
                paths = [f["path"] for f in batch]
                yield f"[Tier {t_idx+1}: {', '.join(p.split('/')[-1] for p in paths)}]\n"
                result = await self._generate_group_async(batch, spec, generated)
                generated.update(result)
                yield f"[✓ {len(result)} files — {len(generated)}/{total_files} total]\n"
            else:
                yield f"[Tier {t_idx+1} PARALLEL: {len(tier)} batches]\n"
                ctx_snapshot = dict(generated)
                tasks = [
                    self._generate_group_async(batch, spec, ctx_snapshot)
                    for batch in tier
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception):
                        print(f"[Orchestrator] Parallel async batch failed: {r}")
                    else:
                        generated.update(r)
                yield f"[✓ parallel done — {len(generated)}/{total_files} total]\n"

        yield f"[Assembling {len(generated)} files...]\n"
        structure = _flat_to_nested(generated)
        project = {"project_type": "fullstack", "structure": structure}
        yield json.dumps(project)

    def parse_project_from_raw(self, raw: str) -> dict:
        """Extract the final JSON from the stream (last chunk is the project JSON)."""
        raw = raw.strip()
        json_start = raw.rfind('{"project_type"')
        if json_start != -1:
            return json.loads(raw[json_start:])
        # Fallback: try the whole string
        return json.loads(raw)
