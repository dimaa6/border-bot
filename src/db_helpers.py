import logging
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
