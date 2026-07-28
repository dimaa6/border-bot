import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from clients import get_supabase
from redis_sessions import delete_session

logger = logging.getLogger(__name__)

async def save_crossing_and_cleanup(
    chat_id: int,
    checkpoint_id: str,
    direction: str,
    started_at: str,
    completed_at: str,
    duration_seconds: int
) -> Optional[str]:
    """
    Saves the border crossing event to Supabase and deletes the user's active session.
    Returns the crossing_id if successful, otherwise None.
    """
    try:
        result = await get_supabase().table("border_crossings").insert({
            "chat_id":          chat_id,
            "checkpoint_id":    checkpoint_id,
            "direction":        direction,
            "started_at":       started_at,
            "completed_at":     completed_at,
            "duration_seconds": duration_seconds,
        }).execute()
        crossing_id = result.data[0]["id"]

        await delete_session(chat_id)
        logger.info("save_crossing_and_cleanup | session deleted | chat_id=%s duration_seconds=%s", chat_id, duration_seconds)
        return crossing_id
    except Exception:
        logger.exception("save_crossing_and_cleanup | DB operation failed | chat_id=%s", chat_id)
        return None


async def get_checkpoint_telegram_handles(checkpoint_ids: list[str] = None) -> dict:
    """
    Fetch telegram handles from checkpoint_scraper_config.
    Returns a dict mapping checkpoint_id to telegram_handle.
    """
    try:
        query = get_supabase().table("checkpoint_scraper_config").select("checkpoint_id, telegram_handle")
        if checkpoint_ids:
            query = query.in_("checkpoint_id", checkpoint_ids)
            
        result = await query.execute()
        
        handles = {
            row["checkpoint_id"]: row["telegram_handle"] 
            for row in result.data or [] 
            if row.get("telegram_handle")
        }
        return handles
    except Exception:
        logger.exception("Failed to fetch checkpoint telegram handles")
        return {}


async def has_recent_crossing(chat_id: int, interval_minutes: int) -> bool:
    """
    Checks whether the user has completed a border crossing within the past `interval_minutes`.
    Returns True if a recent crossing exists, False otherwise.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=interval_minutes)).isoformat()
    result = await get_supabase().table("border_crossings") \
        .select("id") \
        .eq("chat_id", chat_id) \
        .gt("completed_at", cutoff) \
        .maybe_single() \
        .execute()
    return bool(result and result.data)


async def adjust_border_crossing(crossing_id: str, adjust_minutes: int) -> bool:
    """
    Adjusts completed_at time for border crossing `crossing_id` by subtracting `adjust_minutes`.
    Returns True if update was successful, False if invalid (completed_at < started_at).
    """
    row = await get_supabase().table("border_crossings") \
        .select("started_at, completed_at") \
        .eq("id", crossing_id) \
        .single() \
        .execute()

    started_at   = datetime.fromisoformat(row.data["started_at"])
    completed_at = datetime.fromisoformat(row.data["completed_at"]) - timedelta(minutes=adjust_minutes)
    if completed_at < started_at:
        return False

    duration_seconds = max(0, int((completed_at - started_at).total_seconds()))

    await get_supabase().table("border_crossings") \
        .update({
            "completed_at":     completed_at.isoformat(),
            "duration_seconds": duration_seconds,
        }) \
        .eq("id", crossing_id) \
        .execute()

    return True


async def get_checkpoint_statuses(checkpoint_ids: list[str], direction: str, transport_type: str = "car") -> list[dict]:
    """
    Fetch checkpoint statuses from checkpoint_status table for given checkpoint_ids, direction, and transport_type.
    Returns list of status records.
    """
    result = await get_supabase().table("checkpoint_status") \
        .select("*") \
        .in_("checkpoint_id", checkpoint_ids) \
        .eq("direction", direction) \
        .eq("transport_type", transport_type) \
        .execute()
    return result.data or []



