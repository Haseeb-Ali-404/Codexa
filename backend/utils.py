# backend/utils.py
import os
import json
from google import genai
from google.genai.errors import APIError
from dotenv import load_dotenv
from typing import Optional, List, Dict

# --- Configuration Constants ---
PLANNER_MODEL = "gemini-2.5-pro"
DEVELOPER_MODEL = "gemini-2.5-flash"

# --- Client Initialization ---
load_dotenv()

GEMINI_CLIENT: Optional[genai.Client] = None

try:
    GEMINI_CLIENT = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    print("✅ Gemini Client initialized successfully in utils.py.")
except Exception as e:
    print(f"❌ ERROR: Could not initialize Gemini Client: {e}")

# --- Core API Wrapper Function ---
def generate_content(model: str, prompt: str, system_instruction: str = None, tools: Optional[List] = None, **kwargs) -> str:
    """Unified function to call the Gemini API safely with JSON output."""
    global GEMINI_CLIENT
    
    if not GEMINI_CLIENT:
        return "ERROR: AI client is not available."

    config: Dict = {}
    if system_instruction:
        config['system_instruction'] = system_instruction
    if tools:
        config['tools'] = tools
    config.update(kwargs)

    try:
        response = GEMINI_CLIENT.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

        # --- Handle Structured Function Calls ---
        if hasattr(response, "function_calls") and response.function_calls:
            args = dict(response.function_calls[0].args)
            return json.dumps(args, indent=2)  # ✅ Always return JSON

        # --- Fallback: Use response.text (wrap as JSON) ---
        if hasattr(response, "text") and response.text:
            return json.dumps({
                "project_title": "Untitled Project",
                "architecture_overview": response.text[:1000],  # limit size
                "required_steps": [
                    {"step_id": 1, "description": "Generate system architecture", "target_agent": "developer"},
                    {"step_id": 2, "description": "Create main backend file", "target_agent": "developer"}
                ]
            }, indent=2)

        return json.dumps({"error": "Empty response from Gemini model."}, indent=2)

    except APIError as e:
        return json.dumps({"error": f"API ERROR: {e}"}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"UNEXPECTED ERROR: {e}"}, indent=2)
