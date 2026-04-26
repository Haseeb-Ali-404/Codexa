from fastapi import APIRouter

from core.utils.usage_logger import get_usage_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/usage")
def llm_usage_aggregates():
    """
    Aggregated usage totals from the structured JSONL log when present,
    with a fallback to in-memory process totals.
    """
    return {"ok": True, **get_usage_metrics()}
