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

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

_redis_client: Redis | None = None

_INDEX_KEY = "active_session_zset"   # Redis ZSET mapping str(chat_id) -> last_event_ts


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
    
    last_event_iso = max(last_reminded_at, last_user_action_at)
    score = datetime.fromisoformat(last_event_iso).timestamp()
    await r.zadd(_INDEX_KEY, {str(chat_id): score})
    
    logger.debug("upsert_session | chat_id=%s", chat_id)


async def update_last_user_action(chat_id: int, timestamp_iso: str) -> None:
    """Update last_user_action_at for an existing session."""
    r = get_redis()
    await r.hset(_session_key(chat_id), "last_user_action_at", timestamp_iso)
    score = datetime.fromisoformat(timestamp_iso).timestamp()
    await r.zadd(_INDEX_KEY, {str(chat_id): score})
    logger.debug("update_last_user_action | chat_id=%s", chat_id)


async def update_last_reminded(chat_id: int, timestamp_iso: str) -> None:
    """Update last_reminded_at for an existing session."""
    r = get_redis()
    await r.hset(_session_key(chat_id), "last_reminded_at", timestamp_iso)
    score = datetime.fromisoformat(timestamp_iso).timestamp()
    await r.zadd(_INDEX_KEY, {str(chat_id): score})
    logger.debug("update_last_reminded | chat_id=%s", chat_id)


async def delete_session(chat_id: int) -> None:
    """Delete the active session for chat_id."""
    r = get_redis()
    await r.delete(_session_key(chat_id))
    await r.zrem(_INDEX_KEY, str(chat_id))
    logger.debug("delete_session | chat_id=%s", chat_id)


async def update_session_completed_at(chat_id: int, timestamp_iso: str) -> None:
    """Set completed_at for an existing session."""
    r = get_redis()
    await r.hset(_session_key(chat_id), "completed_at", timestamp_iso)
    logger.debug("update_session_completed_at | chat_id=%s", chat_id)


from typing import AsyncGenerator

async def iter_potentially_stale_sessions(cutoff_ts: float) -> AsyncGenerator[dict, None]:
    """
    Yields session dicts for chat_ids whose last event timestamp is <= cutoff_ts.
    This avoids loading all sessions into memory at once.
    """
    r = get_redis()
    # Find all chat_ids that haven't been updated since cutoff_ts
    chat_ids = await r.zrange(_INDEX_KEY, 0, cutoff_ts, byscore=True)
    
    for cid_str in chat_ids:
        key = _session_key(int(cid_str))
        data = await r.hgetall(key)
        if data:
            data["chat_id"] = int(cid_str)
            yield data
        else:
            # Index entry without a hash — clean up the stale index entry
            await r.zrem(_INDEX_KEY, cid_str)


def _get_kyiv_date_str() -> str:
    """Return current YYYY-MM-DD date string in Kyiv timezone."""
    return datetime.now(KYIV_TZ).strftime("%Y-%m-%d")


async def increment_hash_analytics(hash_name: str, field: str, amount: int = 1) -> None:
    """
    Increment counter for `field` by `amount` in Redis hash `hash_name`.
    """
    try:
        await get_redis().hincrby(hash_name, field, amount)
        logger.debug("increment_hash_analytics | hash_name=%s field=%s amount=%s", hash_name, field, amount)
    except Exception:
        logger.exception("increment_hash_analytics failed | hash_name=%s field=%s", hash_name, field)


async def increment_main_menu_analytics(action: str) -> None:
    """
    Increment counter for `action` in Redis hash `analytics:main_menu`
    and daily hash `analytics:daily:YYYY-MM-DD:main_menu` (Kyiv timezone).
    Expected actions: 'start_crossing', 'plan_route', 'view_stats', 'view_info'.
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:main_menu", action)
    await increment_hash_analytics(f"analytics:daily:{date_str}:main_menu", action)


async def increment_crossing_country_analytics(country_code: str) -> None:
    """
    Increment counter for `country_code` in Redis hash `analytics:crossing_countries`
    and daily hash `analytics:crossing_countries:YYYY-MM-DD` (Kyiv timezone).
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:crossing_countries", country_code)
    await increment_hash_analytics(f"analytics:crossing_countries:{date_str}", country_code)


async def increment_checkpoint_analytics(checkpoint_id: str) -> None:
    """
    Increment counter for `checkpoint_id` in Redis hash `analytics:checkpoints`
    and daily hash `analytics:checkpoints:YYYY-MM-DD` (Kyiv timezone).
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:checkpoints", checkpoint_id)
    await increment_hash_analytics(f"analytics:checkpoints:{date_str}", checkpoint_id)


async def increment_direction_analytics(checkpoint_id: str, direction: str) -> None:
    """
    Increment counter for `direction` ('OUTBOUND' / 'INBOUND') in Redis hashes:
    - `analytics:direction`
    - `analytics:direction:YYYY-MM-DD`
    - `analytics:direction:<checkpoint_id>`
    - `analytics:direction:<checkpoint_id>:YYYY-MM-DD`
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:direction", direction)
    await increment_hash_analytics(f"analytics:direction:{date_str}", direction)
    await increment_hash_analytics(f"analytics:direction:{checkpoint_id}", direction)
    await increment_hash_analytics(f"analytics:direction:{checkpoint_id}:{date_str}", direction)


async def increment_crossing_funnel_analytics(step: str) -> None:
    """
    Increment counter for `step` in Redis hash `analytics:funnel:crossing`
    and daily hash `analytics:funnel:crossing:YYYY-MM-DD` (Kyiv timezone).
    Expected steps: 'step_0_started', 'step_1_country_selected', 'step_2_checkpoint_selected', 'step_3_completed'.
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:funnel:crossing", step)
    await increment_hash_analytics(f"analytics:funnel:crossing:{date_str}", step)


async def increment_cancel_funnel_analytics(cancel_type: str) -> None:
    """
    Increment counter for `cancel_type` in Redis hash `analytics:funnel:cancels`
    and daily hash `analytics:funnel:cancels:YYYY-MM-DD` (Kyiv timezone).
    Expected cancel_types: 'cancel_at_country', 'cancel_at_checkpoint', 'cancel_at_direction'.
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:funnel:cancels", cancel_type)
    await increment_hash_analytics(f"analytics:funnel:cancels:{date_str}", cancel_type)


async def increment_crossing_event_analytics(checkpoint_id: str | None, event: str) -> None:
    """
    Increment counter for `event` ('passed', 'still_waiting', 'cancel') in Redis hashes:
    - `analytics:crossing_events`
    - `analytics:crossing_events:YYYY-MM-DD` (Kyiv timezone)
    - `analytics:crossing_events:<checkpoint_id>` (if checkpoint_id is present)
    - `analytics:crossing_events:<checkpoint_id>:YYYY-MM-DD` (if checkpoint_id is present, Kyiv timezone)
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:crossing_events", event)
    await increment_hash_analytics(f"analytics:crossing_events:{date_str}", event)
    if checkpoint_id:
        await increment_hash_analytics(f"analytics:crossing_events:{checkpoint_id}", event)
        await increment_hash_analytics(f"analytics:crossing_events:{checkpoint_id}:{date_str}", event)


async def increment_stats_country_analytics(country_code: str) -> None:
    """
    Increment counter for `country_code` in Redis hash `analytics:stats_countries`
    and daily hash `analytics:stats_countries:YYYY-MM-DD` (Kyiv timezone).
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:stats_countries", country_code)
    await increment_hash_analytics(f"analytics:stats_countries:{date_str}", country_code)


async def increment_stats_direction_analytics(country_code: str, direction: str) -> None:
    """
    Increment counter for `direction` ('OUTBOUND' / 'INBOUND') in Redis hashes:
    - `analytics:stats_direction`
    - `analytics:stats_direction:YYYY-MM-DD`
    - `analytics:stats_direction:<country_code>`
    - `analytics:stats_direction:<country_code>:YYYY-MM-DD`
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:stats_direction", direction)
    await increment_hash_analytics(f"analytics:stats_direction:{date_str}", direction)
    await increment_hash_analytics(f"analytics:stats_direction:{country_code}", direction)
    await increment_hash_analytics(f"analytics:stats_direction:{country_code}:{date_str}", direction)


async def increment_stats_funnel_analytics(step: str) -> None:
    """
    Increment counter for `step` in Redis hash `analytics:funnel:stats`
    and daily hash `analytics:funnel:stats:YYYY-MM-DD` (Kyiv timezone).
    Expected steps: 'step_0_started', 'step_1_country_selected', 'step_2_completed'.
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:funnel:stats", step)
    await increment_hash_analytics(f"analytics:funnel:stats:{date_str}", step)


async def increment_stats_cancel_funnel_analytics(cancel_type: str) -> None:
    """
    Increment counter for `cancel_type` in Redis hash `analytics:funnel:stats_cancels`
    and daily hash `analytics:funnel:stats_cancels:YYYY-MM-DD` (Kyiv timezone).
    Expected cancel_types: 'cancel_at_country', 'cancel_at_direction'.
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:funnel:stats_cancels", cancel_type)
    await increment_hash_analytics(f"analytics:funnel:stats_cancels:{date_str}", cancel_type)


async def increment_info_analytics(field: str = "views") -> None:
    """
    Increment counter for `field` in Redis hash `analytics:info`
    and daily hash `analytics:info:YYYY-MM-DD` (Kyiv timezone).
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:info", field)
    await increment_hash_analytics(f"analytics:info:{date_str}", field)


async def increment_plan_route_country_analytics(country_code: str) -> None:
    """
    Increment counter for `country_code` in Redis hash `analytics:plan_route_countries`
    and daily hash `analytics:plan_route_countries:YYYY-MM-DD` (Kyiv timezone).
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:plan_route_countries", country_code)
    await increment_hash_analytics(f"analytics:plan_route_countries:{date_str}", country_code)


async def increment_plan_route_direction_analytics(country_code: str, direction: str) -> None:
    """
    Increment counter for `direction` ('OUTBOUND' / 'INBOUND') in Redis hashes:
    - `analytics:plan_route_direction`
    - `analytics:plan_route_direction:YYYY-MM-DD`
    - `analytics:plan_route_direction:<country_code>`
    - `analytics:plan_route_direction:<country_code>:YYYY-MM-DD`
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:plan_route_direction", direction)
    await increment_hash_analytics(f"analytics:plan_route_direction:{date_str}", direction)
    await increment_hash_analytics(f"analytics:plan_route_direction:{country_code}", direction)
    await increment_hash_analytics(f"analytics:plan_route_direction:{country_code}:{date_str}", direction)


async def increment_plan_route_city_analytics(city_type: str, city: str) -> None:
    """
    Increment counter for `city` in Redis hash `analytics:plan_route_<city_type>` ('origin' / 'destination')
    and daily hash `analytics:plan_route_<city_type>:YYYY-MM-DD` (Kyiv timezone).
    """
    date_str = _get_kyiv_date_str()
    hash_name = f"analytics:plan_route_{city_type}"
    await increment_hash_analytics(hash_name, city)
    await increment_hash_analytics(f"{hash_name}:{date_str}", city)


async def increment_plan_route_funnel_analytics(step: str) -> None:
    """
    Increment counter for `step` in Redis hash `analytics:funnel:plan_route`
    and daily hash `analytics:funnel:plan_route:YYYY-MM-DD` (Kyiv timezone).
    Expected steps: 'step_0_started', 'step_1_country_selected', 'step_2_direction_selected', 'step_3_origin_selected', 'step_4_completed'.
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:funnel:plan_route", step)
    await increment_hash_analytics(f"analytics:funnel:plan_route:{date_str}", step)


async def increment_plan_route_cancel_funnel_analytics(cancel_type: str) -> None:
    """
    Increment counter for `cancel_type` in Redis hash `analytics:funnel:plan_route_cancels`
    and daily hash `analytics:funnel:plan_route_cancels:YYYY-MM-DD` (Kyiv timezone).
    Expected cancel_types: 'cancel_at_country', 'cancel_at_direction', 'cancel_at_origin', 'cancel_at_destination'.
    """
    date_str = _get_kyiv_date_str()
    await increment_hash_analytics("analytics:funnel:plan_route_cancels", cancel_type)
    await increment_hash_analytics(f"analytics:funnel:plan_route_cancels:{date_str}", cancel_type)


async def track_unique_user(chat_id: int) -> None:
    """
    Tracks unique users using Redis HyperLogLog.
    Adds `chat_id` to:
    - `analytics:hll_users:global`
    - `analytics:hll_users:daily:YYYY-MM-DD` (Kyiv timezone)
    """
    try:
        date_str = _get_kyiv_date_str()
        r = get_redis()
        chat_id_str = str(chat_id)
        await r.pfadd("analytics:hll_users:global", chat_id_str)
        await r.pfadd(f"analytics:hll_users:daily:{date_str}", chat_id_str)
    except Exception:
        logger.exception("track_unique_user | Redis HyperLogLog operation failed | chat_id=%s", chat_id)















