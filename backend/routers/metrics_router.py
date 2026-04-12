from fastapi import APIRouter

from core.utils.usage_logger import get_usage_aggregates

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/usage")
def llm_usage_aggregates():
    """
    In-memory totals since process start (per agent_type).
    Protect this route in production (e.g. reverse proxy or auth).
    """
    return {"ok": True, "by_agent": get_usage_aggregates()}
