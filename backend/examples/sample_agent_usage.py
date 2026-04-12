"""
Run from the backend directory:
  python examples/sample_agent_usage.py
Requires GEMINI_API_KEY or other keys per agents.config.json.
"""

from __future__ import annotations

import os
import sys

# Ensure backend root is on path when executed as a script
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from core.factory.agent_factory import create_agent


def main() -> None:
    # Config-driven (reads core/config/agents.config.json + .env)
    planner = create_agent("planner")
    out = planner.plan("A small habit-tracking mobile app with a FastAPI backend")
    print("Planner:", out)

    # Runtime override: different provider/model without code changes to the agent class
    dev = create_agent(
        "developer",
        provider=os.getenv("SAMPLE_DEV_PROVIDER", "gemini"),
        model=os.getenv("SAMPLE_DEV_MODEL", "gemini-2.5-flash"),
    )
    print("Developer agent type:", type(dev))

    # Explicit API key (e.g. tests): only overrides the primary env name for that agent
    # create_agent("classifier", api_key=os.environ["OPENAI_API_KEY"])

    integrator = create_agent("integrator")
    print("Integrator:", type(integrator))


if __name__ == "__main__":
    main()
