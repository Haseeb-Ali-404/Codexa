import json
import re

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient


class DeveloperAgent:
    """
    Generates a multi-folder, full-stack project as strict JSON via any LLM provider.
    """

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    def _parse_llm_output(self, raw: object) -> dict:
        if isinstance(raw, dict):
            return raw

        if not isinstance(raw, str):
            raise TypeError(f"Unexpected LLM output type: {type(raw)}")

        raw = raw.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        def braces_balanced(s: str) -> bool:
            return s.count("{") == s.count("}")

        if braces_balanced(raw):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        else:
            print("[Developer] LLM output has unbalanced curly braces. Likely incomplete JSON.")
            raise ValueError(
                "LLM output is incomplete or truncated. Please try again or reduce output size."
            )

        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            json_str = json_match.group(0)
            if not braces_balanced(json_str):
                print("[Developer] Extracted JSON string has unbalanced braces. Likely incomplete JSON.")
                raise ValueError(
                    "Extracted JSON is incomplete or truncated. Please try again or reduce output size."
                )
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print("[Developer] Regex-extracted JSON still invalid:", e)

        # Fix common escape sequence issues from LLM
        cleaned = raw.replace("\\'", "'").replace('\\"', '"')
        # Fix any remaining invalid escapes (remove backslash before invalid chars)
        cleaned = cleaned.replace("\\\\", "\\")
        
        if braces_balanced(cleaned):
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                print("[Developer] All attempts to parse LLM output as JSON failed:", e)
                print("Raw output:\n", raw)
                raise e
        print("[Developer] Cleaned LLM output has unbalanced curly braces. Likely incomplete JSON.")
        raise ValueError(
            "LLM output is incomplete or truncated after cleaning. Please try again or reduce output size."
        )

    def _generate_json(self, prompt: str) -> dict:
        messages = [ChatMessage(role="user", content=prompt)]
        result = self._llm.complete(messages, self._opts)
        raw = result.text
        if raw is None or not str(raw).strip():
            raise RuntimeError("LLM returned no text output")
        try:
            return self._parse_llm_output(raw)
        except Exception as e:
            print("[Developer] Failed to parse JSON from DeveloperAgent")
            print("Raw output:\n", raw)
            raise e

    def _build_developer_prompt(self, project_name: str, steps: list, user_message: str) -> str:
        prompt = f"""
You are an elite full-stack engineer. Generate a COMPLETE, WORKING full-stack web application.
The user will run this with ONE CLICK. Every file must be 100% functional. No stubs, no TODOs, no placeholders.
Think Lovable.dev quality — beautiful UI, working CRUD, proper auth, everything wired together.

================================================
USER REQUEST & PLAN
================================================
USER REQUEST: {user_message}

IMPLEMENTATION PLAN:
"""
        for step in steps:
            prompt += f"- {step}\n"

        prompt += """
================================================
WHAT "COMPLETE" MEANS (READ CAREFULLY)
================================================
EVERY feature in the user request MUST be fully working:
- Create, Read, Update, Delete — all 4 operations per entity
- Forms with real-time validation (required fields, format checks, min length)
- Loading states (spinner/skeleton) during API calls
- Error messages displayed in the UI — never silent failures
- Success feedback (toast/notification) after actions
- Protected routes redirect to login if not authenticated
- Beautiful, polished CSS — gradients, shadows, hover effects, transitions
- Mobile-responsive layout (flexbox/grid, works on 375px wide screen)
- Empty states (nice UI when list is empty: icon + message + CTA button)

DO NOT:
- Write "// TODO: implement" or "// placeholder"
- Write empty function bodies
- Skip CSS styling (every component needs proper styles)
- Generate stub components with just a <div>Feature coming soon</div>
- Leave any API endpoint unimplemented
- Include ALL API endpoints with full CRUD + search/filter/pagination
- Add authentication, authorization, security, rate limiting
- Create reusable components, hooks, utilities
- Write tests where appropriate
- DO NOT SKIP FEATURES - implement EVERYTHING requested
- The more detailed and complete your code, the better
- DO NOT be minimal - be THOROUGH
- Add advanced features: caching, optimistic updates, loading skeletons
- Implement proper state management patterns (Context, useReducer)
- Add accessibility features (ARIA, keyboard navigation, screen readers)
- Include performance optimizations (memoization, lazy loading, code splitting)
- Add comprehensive error boundaries and fallback UI
- Implement proper form validation with real-time feedback
- Add data visualization components where appropriate
- Include proper TypeScript types for ALL data structures
- Add proper API error handling with retry logic
- Implement proper loading states and skeleton screens
- Add proper success/error notifications (toast, alerts)
- Include proper data validation on both frontend and backend
- Add proper search, filter, sort, and pagination functionality
- Implement proper authentication flow with token refresh
- Add proper authorization checks on protected routes
- Include proper audit logging for sensitive operations
- Add proper data export/import functionality where appropriate
- Implement proper real-time updates (WebSocket, polling) where needed
- Add proper offline support and service worker where appropriate
- Include proper analytics tracking where appropriate
- Add proper internationalization (i18n) support where needed

================================================
FRONTEND REQUIREMENTS (REACT + TYPESCRIPT)
================================================
Tech Stack:
- React 18.3.1 with TypeScript 5.3.3
- Vite 5.0.10 for build tooling
- React Router DOM 6.22.0 for navigation
- Modern CSS3 with Flexbox/Grid (NO TAILWIND)
- Lucide React for icons (if needed)

Structure (CREATE ALL):
frontend/
├── index.html (proper meta tags, responsive viewport)
├── package.json (ALL dependencies with EXACT versions)
├── vite.config.ts (complete config with plugins)
├── tsconfig.json + tsconfig.node.json
└── src/
    ├── main.tsx (React 18 createRoot)
    ├── App.tsx (main app component with routing)
    ├── App.css (comprehensive styling system)
    ├── index.css (global styles, CSS variables, reset)
    ├── types/ (TypeScript interfaces for all data)
    ├── components/ (reusable UI components)
    │   ├── common/ (Button, Input, Card, Modal, etc.)
    │   ├── layout/ (Header, Footer, Sidebar, Navigation)
    │   └── features/ (feature-specific components)
    ├── pages/ (route-level page components)
    ├── hooks/ (custom React hooks)
    ├── services/ (API calls, utilities)
    ├── context/ (React Context providers)
    └── utils/ (helper functions, validators)

Frontend Standards:
- TypeScript STRICT mode - all types defined, NO 'any' types
- **CRITICAL: ALL imports must use @/ path aliases - NO relative imports like ../../**
  - Example: `import { useAuth } from '@/hooks/useAuth'`
  - Example: `import { Button } from '@/components/common/Button'`
  - Example: `import DashboardPage from '@/pages/DashboardPage'`
  - NEVER use: `import X from '../../components/X'` or `import X from '../hooks/X'`
  - Path alias `@/` is configured in vite.config.ts and tsconfig.json
  - This is REQUIRED for Vite on Windows to resolve modules correctly
- Functional components with hooks (NO class components)
- Proper state management (useState/useEffect/Context/useReducer)
- Form validation with user feedback and error messages
- Loading states and error boundaries for ALL async operations
- Responsive design (mobile-first with breakpoints)
- Accessibility (ARIA labels, keyboard nav, focus management)
- Clean, semantic HTML (no div soup, use proper elements)
- **CRITICAL: ALL dependencies used in code MUST be in package.json - NO EXCEPTIONS**
- **Common dependencies that MUST be added if used:**
  - react-hook-form (if using useForm)
  - date-fns (if using date formatting)
  - axios (if making API calls)
  - lucide-react (if using icons)
  - jwt-decode (if decoding JWT tokens)
  - react-router-dom (if using routing)
  - recharts (if using charts)
  - zustand (if using state management)
  - react-query (if using data fetching)
- **Check EVERY import statement - if you import it, add it to package.json**
- **This is NOT optional - missing dependencies WILL cause build failures**

MANDATORY FRONTEND PATTERNS (use these EXACTLY for every entity):

1. Zustand store pattern for data (adapt for every entity):
```typescript
export const useItemStore = create<ItemState>((set) => ({
  items: [],
  isLoading: false,
  error: null,
  fetchItems: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.get<Item[]>('/api/items');
      set({ items: res.data ?? [], isLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to load', isLoading: false });
    }
  },
  createItem: async (data) => {
    try { const res = await api.post<Item>('/api/items', data); set((s) => ({ items: [res.data, ...s.items] })); return true; }
    catch (err: any) { set({ error: err.response?.data?.detail || 'Failed to create' }); return false; }
  },
  updateItem: async (id, data) => {
    try { const res = await api.put<Item>(`/api/items/${id}`, data); set((s) => ({ items: s.items.map((x) => x.id === id ? res.data : x) })); return true; }
    catch (err: any) { set({ error: err.response?.data?.detail || 'Failed to update' }); return false; }
  },
  deleteItem: async (id) => {
    try { await api.delete(`/api/items/${id}`); set((s) => ({ items: s.items.filter((x) => x.id !== id) })); return true; }
    catch (err: any) { set({ error: err.response?.data?.detail || 'Failed to delete' }); return false; }
  },
}));
```

2. Every list component MUST have loading/error/empty states:
```typescript
if (isLoading) return <div className="loading"><div className="spinner"/></div>;
if (error) return <div className="error-state">{error} <button onClick={retry}>Retry</button></div>;
if (items.length === 0) return <div className="empty-state"><h3>Nothing here yet</h3><button onClick={onAdd}>+ Create First</button></div>;
```

3. Auth-protected route (include in App.tsx):
```typescript
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
};
```

**CRITICAL: VITE CONFIGURATION - MUST BE EXACTLY AS BELOW:**
vite.config.ts MUST include this exact proxy configuration:
```typescript
export default defineConfig({
  server: {
    port: 5959,
    proxy: {
      '/api': {
        target: 'http://localhost:7979',
        changeOrigin: true,
      },
    },
  },
})
```
- **ABSOLUTELY NO EXCEPTIONS: Frontend port MUST be 5959, backend proxy target MUST be 7979**
- **Frontend runs on 5959, backend runs on 7979, Vite proxy forwards /api to 7979**
- **If you use ANY other port, the project WILL FAIL with CORS errors**
- **This is NOT optional - you MUST use these exact ports**

**CRITICAL: FRONTEND SETUP - PREVENT VITE ERRORS:**
- main.tsx MUST properly mount the React root with error handling:
```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

const root = ReactDOM.createRoot(document.getElementById('root')!)
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```
- App.tsx MUST have proper routing setup with error boundaries
- index.html MUST have a valid div with id="root"
- package.json MUST include ALL dependencies used in code
- tsconfig.json MUST have strict mode enabled
- vite.config.ts MUST have proper path alias configuration
- DO NOT use null values without proper null checks
- DO NOT call .split() on null or undefined values — ALWAYS use (value ?? "").split()
- DO NOT call .map()/.filter() on null — ALWAYS use (array ?? []).map()
- DO NOT access [0] or [1] on a split result without ?? fallback
- ALL useState for strings must default to "" not null
- ALL API response data must be accessed with optional chaining (?.) and fallbacks

================================================
BACKEND REQUIREMENTS (PYTHON + FASTAPI)
================================================
Tech Stack:
- FastAPI 0.109.2 with Pydantic v2
- Uvicorn 0.27.1 (ASGI server)
- Motor 3.3.2 (async MongoDB driver)
- PyMongo 4.6.1
- Python 3.11+

Structure (CREATE ALL):
backend/
├── main.py (FastAPI app factory, CORS, middleware, MUST include uvicorn run command at bottom)
├── requirements.txt (ALL packages pinned)
├── .env.example (environment variables template - see format below)
├── app/
│   ├── __init__.py
│   ├── config.py (pydantic-settings, see format below)
│   ├── database.py (MongoDB connection, helpers)
│   ├── models.py (Pydantic models - ALL entities)
│   ├── schemas.py (request/response schemas)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py (authentication endpoints)
│   │   └── api.py (MAIN API ENDPOINTS - MUST CREATE THIS FILE)
│   ├── services/
│   │   └── business_logic.py (service layer)
│   ├── middleware/
│   │   └── auth.py (JWT/auth middleware)
│   └── utils/
│       ├── security.py (hashing, tokens)
│       └── validators.py (input validation)

CRITICAL: main.py MUST include this exact code at the bottom:
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:create_app", host="0.0.0.0", port=7979, reload=True)
```

CRITICAL: app/routes/api.py MUST be created and include all main CRUD endpoints

.env.example FORMAT - MUST INCLUDE ALL THESE EXACT LINES with REAL VALUES:
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=<appname_db>  (e.g., taskflow_db, myapp_db - MUST match app name)
SECRET_KEY=<generate_a_32_char_random_string_here>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

CRITICAL: The .env.example file MUST contain ALL 5 lines above with ACTUAL VALUES, not placeholders like 'your_database_name'. The user copies this to .env and it must work immediately.

config.py FORMAT (pydantic-settings v2):
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str
    MONGO_DB_NAME: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
```

main.py CORS setup (hardcode origins, don't use env var for lists):
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5959", "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Backend Standards:
- Pydantic v2 models for ALL data with proper validation
- Async/await throughout - NO synchronous database operations
- Proper HTTP status codes (200, 201, 204, 400, 401, 403, 404, 500)
- Comprehensive error handling with specific error messages
- JWT authentication (if auth needed) with proper token validation
- Input validation on every endpoint using Pydantic models
- MongoDB with Motor for async operations
- CORS configured for frontend (allow http://localhost:5959, http://localhost:5173, http://localhost:3000)
- Logging middleware for debugging
- **CRITICAL: ALL API endpoints must be FULLY IMPLEMENTED - no stubs or TODO comments**
- **CRITICAL: API routes in routes/api.py must include complete CRUD for all resources**
- **CRITICAL: If frontend calls /api/products, backend MUST have @router.get("/products")**
- **CRITICAL: Test that every endpoint returns proper JSON - no 404 errors**
- **CRITICAL: Python syntax must be VALID - use 'async def' NOT 'as def', proper indentation, valid imports**
- **CRITICAL: HTTP status codes MUST be correct - use HTTP_204_NO_CONTENT (NOT HTTP_24_NO_CONTENT), HTTP_201_CREATED, HTTP_200_OK, HTTP_404_NOT_FOUND**
- **CRITICAL: ALL dependencies used in code MUST be in package.json - if you use date-fns, axios, lucide-react, jwt-decode, add them to dependencies**
- **CRITICAL: .env.example MUST include ALL required fields: MONGO_URI, MONGO_DB_NAME, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES**
- **CRITICAL: NEVER use placeholder values - use actual working values for .env.example**
- **CRITICAL: Pydantic models MUST have proper field types - NO 'Optional' where required, proper validators**
- **CRITICAL: MongoDB queries MUST use proper ObjectId conversion - string to ObjectId**
- **CRITICAL: PyObjectId MUST use Pydantic v2 validators - use __get_pydantic_core_schema__ NOT __get_validators__**
- **CRITICAL: Bcrypt password hashing MUST truncate passwords > 72 bytes - add password length check in get_password_hash**
- **CRITICAL: ALL schemas imported in services/routes MUST be defined in schemas.py - if you import OrderUpdate, you MUST define it**
- **CRITICAL: schemas.py MUST be COMPLETE - define ALL Create, Update, Response schemas for EVERY entity**
- **CRITICAL: AVOID PyObjectId entirely - use str type for all id fields to prevent Pydantic v2 compatibility issues**
- **CRITICAL: If you use ObjectId, import it: from bson import ObjectId**
- **CRITICAL: NEVER import PyObjectId in schemas.py - use str instead**
- **CRITICAL: .env.example MUST have WORKING values - NO placeholders like "your-secret-key"**
- **CRITICAL: Use mongodb://localhost:27017/ for MONGO_URI (local MongoDB)**
- **CRITICAL: Use "testdb" for MONGO_DB_NAME (or any valid database name)**
- **CRITICAL: Use "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" for SECRET_KEY (real working key)**
- **CRITICAL: Use "HS256" for ALGORITHM**
- **CRITICAL: Use "30" for ACCESS_TOKEN_EXPIRE_MINUTES**
- **CRITICAL: Frontend API calls MUST use relative URLs (/api/...) NOT hardcoded URLs (http://localhost:8000)**
- **CRITICAL: Axios baseURL MUST be '/api' NOT 'http://localhost:8000' - use Vite proxy**
- **CRITICAL: Vite proxy configuration MUST target port 7979 NOT 8000**
- **CRITICAL: src/services/api.ts MUST include an axios request interceptor that attaches the JWT token:**
```typescript
// src/services/api.ts — REQUIRED EXACT PATTERN
import axios from 'axios';

const api = axios.create({ baseURL: '/api', timeout: 15000 });

api.interceptors.request.use((config) => {
  // Read token from localStorage directly to always get fresh value
  const stored = localStorage.getItem('auth-storage-v2') || localStorage.getItem('auth-storage') || '{}';
  try {
    const parsed = JSON.parse(stored);
    const token = parsed?.state?.token;
    if (token) config.headers.Authorization = `Bearer ${token}`;
  } catch {}
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('auth-storage-v2');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default api;
```
- **This interceptor is MANDATORY - without it every authenticated API call returns 401 and nothing works after login**
- **The token key in localStorage MUST match the name in the Zustand persist config**

Backend Quality Requirements (ALL MUST BE IMPLEMENTED):
- Full CRUD for every entity: Create, Read (list + single), Update, Delete
- MongoDB indexes for performance (at minimum: user_id, created_at)
- Pagination: GET /items?page=1&limit=20 returns {items: [...], total: int, page: int}
- Search/filter: GET /items?search=query&status=active
- Sort: GET /items?sort_by=created_at&order=desc
- Proper 404 when item not found, 403 when item belongs to different user
- MongoDB ObjectId to string conversion in all responses (use str(doc['_id']))
- created_at set to datetime.utcnow() on every insert
- ALL routes registered in main.py with include_router()

================================================
CIRCULAR IMPORT PREVENTION (CRITICAL - READ CAREFULLY)
================================================
CIRCULAR IMPORTS ARE FORBIDDEN. They cause ImportError and crash the application.

WRONG PATTERN (CAUSES CRASH):
```python
# app/utils/security.py
from app.services.user_service import get_user_by_id  # ❌ BAD

def get_password_hash(password):
    return hash(password)

# app/services/user_service.py  
from app.utils.security import get_password_hash  # ❌ BAD - creates circular dependency

def create_user():
    hashed = get_password_hash(password)
```

CORRECT PATTERN (NO CIRCULAR IMPORTS):
```python
# app/utils/security.py — use bcrypt DIRECTLY, NEVER passlib (passlib 1.7.4 crashes with bcrypt 4.x)
import bcrypt as _bcrypt_lib

def get_password_hash(password: str) -> str:
    pw = password.encode('utf-8')[:72]
    return _bcrypt_lib.hashpw(pw, _bcrypt_lib.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    pw = plain.encode('utf-8')[:72]
    return _bcrypt_lib.checkpw(pw, hashed.encode('utf-8'))

# app/services/user_service.py - CAN import from security (one-way dependency)
from app.utils.security import get_password_hash, verify_password  # ✅ OK

def create_user(db, user_data):
    hashed = get_password_hash(user_data.password)
    # ...

# app/utils/security.py - if you need user functions, use LAZY IMPORT inside the function
async def get_current_user(token: str = Depends(oauth2_scheme)):
    # Lazy import ONLY inside function to avoid circular import
    from app.services.user_service import get_user_by_id  # ✅ OK - lazy import
    
    user = await get_user_by_id(db, user_id)
    return user
```

MODULE ORGANIZATION RULES:
- utils/security.py: ONLY password hashing, JWT token creation - NO service imports at top
- services/: CAN import from utils - one-way dependency OK
- routes/: CAN import from services and utils
- models.py, schemas.py: NO imports from services or routes
- database.py: NO imports from services

FOLLOW THIS STRICTLY - no circular imports allowed.

================================================
AGENT COLLABORATION (WORK WITH OTHER AGENTS)
================================================
You are the DEVELOPER agent. You work with:
- PLANNER agent: Receives implementation plan
- DEBUGGER agent: Validates your code structure
- INTEGRATOR agent: Verifies frontend-backend integration
- PREVIEW router: Auto-fixes your code before running

Your responsibilities:
- Generate COMPLETE, ERROR-FREE code
- Follow ALL critical instructions above
- Create proper project structure
- Ensure frontend-backend API compatibility
- Use correct ports (backend: 7979, frontend: 5959)
- Use relative URLs (/api) NOT hardcoded URLs
- The debugger agent will catch and fix common mistakes
- The integrator agent will verify routing and API integration
- The preview router will apply auto-fixes before running

Quality goals:
- Generate code that passes debugger validation
- Generate code that passes integrator verification
- Generate code that requires minimal auto-fixes
- Generate code that works on first try

================================================
NULL SAFETY — ABSOLUTE LAW (READ THIS CAREFULLY)
================================================
The #1 runtime crash in generated React apps is calling .split(), .map(), .filter(),
.length, or .join() on a value that is null or undefined at runtime.

EVERY SINGLE TIME you access a property that might be null/undefined, you MUST guard it.

LAW 1 — NEVER call .split() directly on a variable. ALWAYS use one of:
  ✅ (value ?? "").split("/")          ← null coalescing (preferred)
  ✅ value?.split("/") ?? []           ← optional chaining
  ✅ if (!value) return; value.split() ← explicit guard

  ❌ file.path.split("/")             ← CRASHES if path is null
  ❌ user.name.split(" ")             ← CRASHES if name is null
  ❌ data.content.split("\\n")        ← CRASHES if content is null

LAW 2 — NEVER call .map() / .filter() / .forEach() without guarding the array:
  ✅ (items ?? []).map(...)
  ✅ items?.map(...) ?? []
  ❌ items.map(...)  ← CRASHES if items is null/undefined

LAW 3 — NEVER access array index [0] or [1] without a guard:
  ✅ parts[1] ?? ""
  ✅ parts.at(1) ?? ""
  ❌ pathname.split("/c/")[1]  ← CRASHES if split result has no index 1

LAW 4 — ALL API response data MUST be treated as potentially null:
  ✅ const name = data?.user?.name ?? "Unknown"
  ✅ const items = data?.items ?? []
  ❌ const name = data.user.name  ← CRASHES if any level is null

LAW 5 — ALL useState initial values for strings MUST be "" not null:
  ✅ const [name, setName] = useState<string>("")
  ❌ const [name, setName] = useState<string | null>(null)  ← then name.split() crashes

LAW 6 — axios instances MUST have a timeout:
  ✅ axios.create({ timeout: 15000, ... })
  ❌ axios.create({ ... })  ← requests hang forever on backend crash

LAW 7 — NEVER read Zustand state from a stale closure after an await:
  ✅ const currentError = useStoreName.getState().error  ← always fresh
  ❌ const { error } = useStoreName()  ← then checking error after await = stale value

APPLY THESE LAWS TO EVERY LINE OF CODE YOU WRITE. NO EXCEPTIONS.

================================================
BACKEND BUGS TO NEVER REPEAT
================================================
BUG 1 — MISSING created_at WHEN INSERTING TO MONGODB:
  Every MongoDB insert MUST include created_at = datetime.utcnow().
  ALWAYS build the insert dict manually, NEVER use model_dump() and assume all
  fields are present — Pydantic models don't include server-generated fields.
  ✅ doc = {"email": ..., "password_hash": ..., "created_at": datetime.utcnow()}
  ❌ doc = user_data.model_dump()  ← missing created_at, causes KeyError on response

BUG 2 — MISSING IMPORTS IN security.py:
  If security.py has a get_current_user dependency that calls get_user_by_id,
  ALWAYS import get_user_by_id at the top of security.py.
  ✅ from app.services.user_service import get_user_by_id
  ❌ calling get_user_by_id() without importing it ← NameError crashes all auth routes

BUG 3 — CIRCULAR IMPORTS via lazy comment:
  Never write "# Lazy import moved inside function to prevent circular dependency"
  and then not actually move it. Either truly move the import inside the function,
  or restructure so the import is not circular.

BUG 5 — ZUSTAND PERSIST SAVING isLoading (causes instant loading spinner on page reload):
  NEVER persist transient UI state. ALWAYS use partialize:
  ✅ persist(fn, { name: 'store', partialize: (s) => ({ token: s.token, user: s.user, isAuthenticated: s.isAuthenticated }) })
  ❌ persist(fn, { name: 'store' })  ← persists isLoading:true, breaks every page reload

BUG 6 — STALE CLOSURE WHEN READING ZUSTAND STATE AFTER await:
  After awaiting an async action, read fresh state from .getState(), not the destructured variable:
  ✅ const err = useMyStore.getState().error;
  ❌ const { error } = useMyStore(); ... await action(); if (error)  ← stale, always null

BUG 7 — CIRCULAR IMPORT between security.py and user_service.py:
  security.py imports passlib/bcrypt utilities used BY user_service.py.
  user_service.py imports get_password_hash FROM security.py.
  If security.py also imports FROM user_service.py at module level → circular crash.
  ✅ Move the import INSIDE the function that needs it (lazy import):
     async def get_current_user(...):
         from app.services.user_service import get_user_by_id  ← inside function only
  ❌ from app.services.user_service import get_user_by_id  ← at module level in security.py

BUG 4 — RESPONSE MODEL MISMATCH:
  If response_model=UserPublic requires field X, the dict returned from the route
  handler MUST contain field X with the correct type. Pydantic will raise 500 if not.
  Check EVERY route's return value against its response_model before outputting.

================================================
ERROR PREVENTION CHECKLIST (VERIFY BEFORE OUTPUT)
================================================
Before generating your JSON output, verify:
✓ All id fields use 'str' type (NOT PyObjectId)
✓ All API endpoints are fully implemented (no stubs)
✓ Frontend uses relative URLs (/api) NOT hardcoded URLs
✓ Vite proxy targets port 7979
✓ .env.example has working values (not placeholders)
✓ Bcrypt password truncation is implemented
✓ Pydantic v2 validators are used (not v1)
✓ All dependencies are in package.json/requirements.txt
✓ No circular imports (security.py doesn't import services)
✓ HTTP status codes are correct (204, not 24)
✓ Python syntax is valid (async def, not as def)
✓ CORS is configured in main.py
✓ All schemas are defined in schemas.py
✓ Frontend has AuthContext for authentication
✓ Frontend has API service for HTTP calls
✓ React Router is set up in main.tsx
✓ TypeScript is configured properly
✓ __init__.py files exist in all directories
✓ EVERY .split() call is guarded with ?? "" or optional chaining
✓ EVERY .map()/.filter() call is guarded with ?? []
✓ EVERY array index access [n] is guarded with ?? fallback
✓ EVERY useState for string/array uses "" or [] as initial value (NOT null)
✓ EVERY API response property access uses optional chaining (?.)
✓ src/services/api.ts has axios interceptor that reads JWT from localStorage and sets Authorization header
✓ Backend main.py CORS allows_origins includes "http://localhost:5959"
✓ ALL backend route files (auth.py, api.py, etc.) are registered with app.include_router() in main.py
✓ Frontend localStorage key in api.ts interceptor matches Zustand persist name
✓ Zustand persist uses partialize to exclude isLoading and error (prevents stale loading on refresh)

If any item is not checked, FIX IT before outputting your JSON.

================================================
BACKEND FILE STRUCTURE EXAMPLE (COPY THIS PATTERN)
================================================
backend/
├── main.py
├── app/
│   ├── models.py          # Pydantic models - NO service imports
│   ├── schemas.py         # Request/response schemas - NO service imports  
│   ├── database.py        # MongoDB connection - NO service imports
│   ├── config.py          # Settings - NO service imports
│   ├── utils/
│   │   └── security.py    # Password hashing, JWT - NO service imports at top
│   ├── services/
│   │   └── user_service.py # Business logic - CAN import from utils
│   └── routes/
│       └── auth.py        # Endpoints - CAN import from services and utils

IMPORT FLOW (one-way dependencies):
models.py → (nothing)
schemas.py → models.py
database.py → config.py
utils/security.py → config.py, database.py
services/ → models.py, schemas.py, database.py, utils/
routes/ → models.py, schemas.py, services/, utils/
main.py → routes/, database.py

API ROUTE STRUCTURE (main.py must include):
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

================================================
DATABASE SCHEMA (MongoDB)
================================================
Design proper collections with:
- Clear document schemas
- Indexes for performance
- Relationships where needed
- Validation rules

================================================
API INTEGRATION
================================================
- Frontend base URL: http://localhost:7979
- All routes prefixed with /api/
- RESTful conventions
- JSON request/response bodies
- Proper Content-Type headers

================================================
DEPENDENCY MANAGEMENT (CRITICAL)
================================================
Use EXACT, LATEST STABLE versions:

FRONTEND package.json:
{{
  "name": "app",
  "version": "1.0.0",
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  }},
  "dependencies": {{
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "react-router-dom": "6.22.0",
    "date-fns": "3.3.1",
    "axios": "1.6.7",
    "lucide-react": "0.344.0",
    "jwt-decode": "4.0.0"
  }},
  "devDependencies": {{
    "@types/react": "18.2.61",
    "@types/react-dom": "18.2.19",
    "@vitejs/plugin-react": "4.2.1",
    "typescript": "5.3.3",
    "vite": "5.0.10"
  }}
}}

BACKEND requirements.txt:
fastapi==0.109.2
uvicorn[standard]==0.27.1
motor==3.3.2
pymongo==4.5.0
pydantic==2.6.1
python-jose[cryptography]==3.3.0
bcrypt==4.1.2
python-multipart==0.0.6
python-dotenv==1.0.0
email-validator==2.1.0

================================================
QUALITY CHECKLIST (VERIFY BEFORE OUTPUT)
================================================
□ Every component is COMPLETE (not a stub)
□ All imports resolve correctly
□ TypeScript has ZERO errors
□ Forms have validation + error messages
□ API calls handle loading + error states
□ Backend has ALL CRUD operations
□ Authentication works if included
□ MongoDB schemas are complete
□ Responsive design implemented
□ CSS is comprehensive (not minimal)
□ No TODO comments or placeholders
□ Code is production-ready

================================================
CONSISTENCY VERIFICATION (CRITICAL - MUST CHECK)
================================================
BEFORE OUTPUT, VERIFY:

1. SCHEMA CONSISTENCY:
   - If a file imports "OrderUpdate" from schemas.py, schemas.py MUST define "OrderUpdate"
   - If a file imports "UserCreate" from schemas.py, schemas.py MUST define "UserCreate"
   - EVERY schema imported in services/routes MUST be defined in schemas.py
   - For EVERY entity, schemas.py must have: EntityCreate, EntityUpdate, EntityResponse

2. IMPORT CONSISTENCY:
   - Every import must resolve to an actual file
   - If you import from '@/components/X', src/components/X.tsx MUST exist
   - If you import from '@/hooks/Y', src/hooks/Y.ts MUST exist
   - NO circular imports (utils/services, services/utils)

3. DEPENDENCY CONSISTENCY:
   - If you use "date-fns" in code, package.json MUST have "date-fns"
   - If you use "axios" in code, package.json MUST have "axios"
   - If you use "lucide-react" in code, package.json MUST have "lucide-react"
   - ALL libraries used in frontend MUST be in package.json

4. ENDPOINT CONSISTENCY:
   - If frontend calls "/api/products", backend MUST have @router.get("/products")
   - If frontend calls "/api/orders", backend MUST have @router.get("/orders")
   - ALL API routes referenced in frontend MUST exist in backend
   - **CRITICAL: Auth endpoints - if backend auth router is at /api/auth, then frontend MUST call /api/auth/register and /api/auth/token**
   - **CRITICAL: NEVER call /api/users/register if backend has auth router at /api/auth - use /api/auth/register instead**
   - **CRITICAL: Verify main.py route prefixes match frontend API calls**

5. FILE COMPLETENESS:
   - ALL files in structure MUST have content (no empty strings)
   - main.py MUST include ALL route includes
   - schemas.py MUST have ALL schema definitions
   - .env.example MUST have ALL 5 required fields

6. VALIDATION CONSISTENCY:
   - If backend UserCreate schema has password min_length=8, frontend MUST validate password >= 8 characters
   - If backend requires EmailStr, frontend MUST validate email format before sending
   - Frontend form validation MUST match backend Pydantic schema requirements
   - Add frontend validation to prevent 422 errors from backend

FAIL VERIFICATION IF ANY INCONSISTENCY FOUND. FIX IT BEFORE OUTPUT.

================================================
OUTPUT FORMAT (JSON ONLY)
================================================
Return ONLY this JSON structure with COMPLETE file contents:

{{
  "project_type": "fullstack",
  "structure": [
    {{
      "type": "folder",
      "name": "frontend",
      "children": [
        {{ "type": "file", "name": "index.html", "content": "<!DOCTYPE html>..." }},
        {{ "type": "file", "name": "package.json", "content": '{{"name":"app"...}}' }},
        {{ "type": "file", "name": "vite.config.ts", "content": "import {{ defineConfig }} from 'vite'\\nimport react from '@vitejs/plugin-react'\\nimport path from 'path'\\n\\nexport default defineConfig({{\\n  plugins: [react()],\\n  resolve: {{\\n    alias: {{\\n      '@': path.resolve(__dirname, './src'),\\n    }},\\n  }},\\n  server: {{\\n    port: 5173,\\n    proxy: {{\\n      '/api': {{\\n        target: 'http://localhost:7979',\\n        changeOrigin: true,\\n      }},\\n    }},\\n  }},\\n}})" }},
        {{ "type": "file", "name": "tsconfig.json", "content": '{{"compilerOptions":{{"target":"ES2020","useDefineForClassFields":true,"lib":["ES2020","DOM","DOM.Iterable"],"module":"ESNext","skipLibCheck":true,"moduleResolution":"bundler","allowImportingTsExtensions":true,"resolveJsonModule":true,"isolatedModules":true,"noEmit":true,"jsx":"react-jsx","strict":true,"noUnusedLocals":true,"noUnusedParameters":true,"noFallthroughCasesInSwitch":true,"baseUrl":".","paths":{{"@/*":["./src/*"]}}}},"include":["src"],"references":[{{"path":"./tsconfig.node.json"}}]}}' }},
        {{ "type": "file", "name": "tsconfig.node.json", "content": "..." }},
        {{
          "type": "folder",
          "name": "src",
          "children": [
            {{ "type": "file", "name": "main.tsx", "content": "import React from 'react'\\nimport ReactDOM from 'react-dom/client'\\nimport App from '@/App'\\nimport './index.css'\\nimport {{ AuthProvider }} from '@/context/AuthContext'\\nimport {{ BrowserRouter }} from 'react-router-dom'\\n\\nReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter></React.StrictMode>)" }},
            {{ "type": "file", "name": "App.tsx", "content": "import {{ Routes, Route }} from 'react-router-dom'\\nimport {{ useAuth }} from '@/hooks/useAuth'\\nimport Layout from '@/components/layout/Layout'\\nimport HomePage from '@/pages/HomePage'\\n// ... ALL imports use @/ path alias" }},
            {{ "type": "file", "name": "App.css", "content": "..." }},
            {{ "type": "file", "name": "index.css", "content": "..." }},
            {{
              "type": "folder",
              "name": "components",
              "children": [
                {{ "type": "file", "name": "Header.tsx", "content": "..." }},
                // ... ALL components
              ]
            }},
            {{
              "type": "folder",
              "name": "pages",
              "children": [
                {{ "type": "file", "name": "Home.tsx", "content": "..." }},
                // ... ALL pages
              ]
            }},
            {{
              "type": "folder",
              "name": "types",
              "children": [
                {{ "type": "file", "name": "index.ts", "content": "export interface User..." }}
              ]
            }},
            {{
              "type": "folder",
              "name": "hooks",
              "children": [
                {{ "type": "file", "name": "useAuth.ts", "content": "..." }}
              ]
            }},
            {{
              "type": "folder",
              "name": "services",
              "children": [
                {{ "type": "file", "name": "api.ts", "content": "..." }}
              ]
            }}
          ]
        }}
      ]
    }},
    {{
      "type": "folder",
      "name": "backend",
      "children": [
        {{ "type": "file", "name": "main.py", "content": "from fastapi import FastAPI..." }},
        {{ "type": "file", "name": "requirements.txt", "content": "fastapi==0.109.2..." }},
        {{ "type": "file", "name": ".env.example", "content": "MONGO_URI=..." }},
        {{
          "type": "folder",
          "name": "app",
          "children": [
            {{ "type": "file", "name": "__init__.py", "content": "" }},
            {{ "type": "file", "name": "config.py", "content": "..." }},
            {{ "type": "file", "name": "database.py", "content": "..." }},
            {{ "type": "file", "name": "models.py", "content": "..." }},
            {{ "type": "file", "name": "schemas.py", "content": "..." }},
            {{
              "type": "folder",
              "name": "routes",
              "children": [
                {{ "type": "file", "name": "__init__.py", "content": "" }},
                {{ "type": "file", "name": "auth.py", "content": "..." }},
                {{ "type": "file", "name": "api.py", "content": "..." }}
              ]
            }},
            {{
              "type": "folder",
              "name": "services",
              "children": [
                {{ "type": "file", "name": "__init__.py", "content": "" }},
                {{ "type": "file", "name": "business_logic.py", "content": "..." }}
              ]
            }},
            {{
              "type": "folder",
              "name": "middleware",
              "children": [
                {{ "type": "file", "name": "__init__.py", "content": "" }},
                {{ "type": "file", "name": "auth.py", "content": "..." }}
              ]
            }},
            {{
              "type": "folder",
              "name": "utils",
              "children": [
                {{ "type": "file", "name": "__init__.py", "content": "" }},
                {{ "type": "file", "name": "security.py", "content": "..." }},
                {{ "type": "file", "name": "validators.py", "content": "..." }}
              ]
            }}
          ]
        }}
      ]
    }}
  ]
}}

REMEMBER:
- USE YOUR FULL TOKEN BUDGET
- BE THOROUGH, NOT MINIMAL
- PRODUCTION-GRADE CODE ONLY
- EVERY FILE MUST BE COMPLETE AND FUNCTIONAL
"""
        return prompt
    
    async def astream_developer_text(
        self, project_name: str, steps: list, user_message: str
    ):
        """Stream raw JSON text from the LLM (WebSocket UX)."""
        prompt = self._build_developer_prompt(project_name, steps, user_message)
        messages = [ChatMessage(role="user", content=prompt)]
        async for chunk in self._llm.acomplete_stream(messages, self._opts):
            if chunk:
                yield chunk

    def parse_project_from_raw(self, raw: str) -> dict:
        return self._parse_llm_output(raw)

    def generate_project(self, project_name: str, steps: list, user_message: str):
        print("[DeveloperAgent] Generating full-stack project...")

        prompt = self._build_developer_prompt(project_name, steps, user_message)
        project_json = self._generate_json(prompt)

        if not isinstance(project_json, dict):
            raise RuntimeError("DeveloperAgent output is not a JSON object")

        if "structure" not in project_json:
            raise RuntimeError("DeveloperAgent output missing 'structure'")

        return project_json
