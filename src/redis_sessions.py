"""
redis_sessions.py
-----------------
All interactions with the active_sessions store, backed by Redis.

Session data is stored as a Redis hash at key  session:{chat_id}
with the following fields:
    checkpoint_id       str
    direction           str  ("INBOUND" | "OUTBOUND")
    started_at          str  (ISO-8601, UTC)
    last_reminded_at    str  (ISO-8601, UTC)
    last_user_action_at str  (ISO-8601, UTC)

A set  "active_session_ids"  maps  str(chat_id) → member
so that check_stale_sessions can enumerate all active sessions efficiently.
"""

import logging
import os

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

_redis_client: Redis | None = None

_INDEX_KEY = "active_session_ids"   # Redis Set of str(chat_id)


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(
            host=_REDIS_HOST,
            port=_REDIS_PORT,
            decode_responses=True,
        )
    return _redis_client


def _session_key(chat_id: int) -> str:
    return f"session:{chat_id}"


# ---------------------------------------------------------------------------
# Public API (fully async)
# ---------------------------------------------------------------------------

async def session_exists(chat_id: int) -> bool:
    """Return True if an active session exists for chat_id."""
    return await get_redis().exists(_session_key(chat_id)) == 1


async def get_session(chat_id: int) -> dict | None:
    """Return the session dict for chat_id, or None if it does not exist."""
    data = await get_redis().hgetall(_session_key(chat_id))
    return data if data else None


async def upsert_session(
    chat_id: int,
    checkpoint_id: str,
    direction: str,
    started_at: str,
    last_reminded_at: str,
    last_user_action_at: str,
) -> None:
    """Create or overwrite the active session for chat_id."""
    r = get_redis()
    key = _session_key(chat_id)
    await r.hset(key, mapping={
        "checkpoint_id":       checkpoint_id,
        "direction":           direction,
        "started_at":          started_at,
        "last_reminded_at":    last_reminded_at,
        "last_user_action_at": last_user_action_at,
    })
    await r.sadd(_INDEX_KEY, str(chat_id))
    logger.debug("upsert_session | chat_id=%s", chat_id)


async def update_last_user_action(chat_id: int, timestamp_iso: str) -> None:
    """Update last_user_action_at for an existing session."""
    await get_redis().hset(_session_key(chat_id), "last_user_action_at", timestamp_iso)
    logger.debug("update_last_user_action | chat_id=%s", chat_id)


async def update_last_reminded(chat_id: int, timestamp_iso: str) -> None:
    """Update last_reminded_at for an existing session."""
    await get_redis().hset(_session_key(chat_id), "last_reminded_at", timestamp_iso)
    logger.debug("update_last_reminded | chat_id=%s", chat_id)


async def delete_session(chat_id: int) -> None:
    """Delete the active session for chat_id."""
    r = get_redis()
    await r.delete(_session_key(chat_id))
    await r.srem(_INDEX_KEY, str(chat_id))
    logger.debug("delete_session | chat_id=%s", chat_id)


async def get_all_sessions() -> list[dict]:
    """
    Return a list of all active session dicts (each includes a 'chat_id' int field).
    Used by the stale-session checker.
    """
    r = get_redis()
    chat_ids = await r.smembers(_INDEX_KEY)
    sessions = []
    for cid_str in chat_ids:
        key = _session_key(int(cid_str))
        data = await r.hgetall(key)
        if data:
            data["chat_id"] = int(cid_str)
            sessions.append(data)
        else:
            # Index entry without a hash — clean up the stale index entry
            await r.srem(_INDEX_KEY, cid_str)
    return sessions
