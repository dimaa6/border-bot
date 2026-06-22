import logging

from log_setup import configure_logging
from datetime import datetime, timezone, timedelta

from clients import get_supabase, send_telegram_request, send_main_menu
from redis_sessions import get_all_sessions, update_last_reminded, delete_session
from checkpoints import COUNTRIES_AND_CHECKPOINTS
from handler import CMD_START_CROSSING, CMD_STATS, CMD_INFO, GREETINGS_PROMPT_SHORT

configure_logging()
logger = logging.getLogger(__name__)

EVICTION_HOURS = 24

# (max_hours_in_queue, silence_minutes) — matched top-to-bottom
_REMINDER_THRESHOLDS = [
    (2,   55),
    (5,  115),
    (None, 175),
]


def _required_silence_minutes(started_at_iso: str, now: datetime) -> int:
    started_at = datetime.fromisoformat(started_at_iso)
    hours_in_queue = (now - started_at).total_seconds() / 3600
    for max_hours, silence_minutes in _REMINDER_THRESHOLDS:
        if max_hours is None or hours_in_queue < max_hours:
            return silence_minutes


def _last_event_iso(session: dict) -> str:
    """Latest of last_reminded_at and last_user_action_at."""
    return max(session["last_reminded_at"], session["last_user_action_at"])


def _get_checkpoint_name(checkpoint_id: str) -> str:
    for country in COUNTRIES_AND_CHECKPOINTS.values():
        name = country["checkpoints"].get(checkpoint_id)
        if name:
            return name
    return checkpoint_id


async def _expire_session(session: dict) -> None:
    chat_id = session["chat_id"]
    logger.info("check_stale_sessions | expiring session | chat_id=%s", chat_id)
    await delete_session(chat_id)
    logger.info("check_stale_sessions | session deleted | chat_id=%s", chat_id)
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": "Ми не чули від вас довгий час, тому ми видалили вас зі списку очікування. Щасливої дороги🚗",
    })
    await send_main_menu(
        chat_id,
        GREETINGS_PROMPT_SHORT,
        CMD_START_CROSSING,
        CMD_STATS,
        CMD_INFO,
    )


async def _notify_session(session: dict, now_iso: str) -> None:
    chat_id       = session["chat_id"]
    checkpoint_id = session["checkpoint_id"]
    checkpoint    = _get_checkpoint_name(checkpoint_id)

    logger.info("check_stale_sessions | notifying | chat_id=%s checkpoint=%s", chat_id, checkpoint_id)

    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"Ви все ще на КПП *{checkpoint}*? Будь ласка, оновіть свій статус ⬇️",
        "parse_mode": "Markdown",
        "reply_markup": {
            "keyboard": [
                [{"text": "✅ Я проїхав!"}],
                [{"text": "⏳ Все ще стою"}],
                [{"text": "❌ Скасувати"}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False,
        },
    })

    await update_last_reminded(chat_id, now_iso)
    logger.info("check_stale_sessions | last_reminded_at updated | chat_id=%s", chat_id)


async def check_stale_sessions() -> None:
    now     = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    eviction_cutoff = (now - timedelta(hours=EVICTION_HOURS)).isoformat()

    logger.info("check_stale_sessions | started | now=%s", now_iso)

    sessions = await get_all_sessions()
    logger.info("check_stale_sessions | total active sessions=%d", len(sessions))

    expired = 0
    reminded = 0
    skipped = 0

    for session in sessions:
        try:
            if session["last_user_action_at"] < eviction_cutoff:
                logger.info("check_stale_sessions | no user action for 24h | chat_id=%s", session["chat_id"])
                await _expire_session(session)
                expired += 1
                continue

            silence_minutes = _required_silence_minutes(session["started_at"], now)
            last_event      = _last_event_iso(session)
            silence_cutoff  = (now - timedelta(minutes=silence_minutes)).isoformat()

            if last_event < silence_cutoff:
                logger.info(
                    "check_stale_sessions | silence exceeded %dm | chat_id=%s",
                    silence_minutes, session["chat_id"],
                )
                await _notify_session(session, now_iso)
                reminded += 1
            else:
                skipped += 1

        except Exception:
            logger.exception("check_stale_sessions | failed for chat_id=%s", session.get("chat_id"))

    logger.info("check_stale_sessions | done | expired=%d reminded=%d skipped=%d", expired, reminded, skipped)
