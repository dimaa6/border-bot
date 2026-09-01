import logging
import os
import random
from datetime import datetime, timezone, timedelta

from log_setup import configure_logging
from clients import send_telegram_request, send_main_menu
from redis_sessions import (
    session_exists,
    get_session,
    upsert_session,
    update_last_user_action,
    delete_session,
    update_session_completed_at,
    increment_main_menu_analytics,
    increment_crossing_country_analytics,
    increment_checkpoint_analytics,
    increment_direction_analytics,
    increment_crossing_funnel_analytics,
    increment_cancel_funnel_analytics,
    increment_crossing_event_analytics,
    increment_stats_country_analytics,
    increment_stats_direction_analytics,
    increment_stats_funnel_analytics,
    increment_stats_cancel_funnel_analytics,
    increment_info_analytics,
    increment_plan_route_funnel_analytics,
    increment_plan_route_cancel_funnel_analytics,
    track_unique_user,
)
from checkpoints import COUNTRIES_AND_CHECKPOINTS
from manual_stats import (
    is_admin,
    handle_addstats_cmd,
    handle_admin_direction_selected,
    handle_admin_reply
)
from constants import *
from db_helpers import (
    save_crossing_and_cleanup,
    get_checkpoint_telegram_handles,
    has_recent_crossing,
    adjust_border_crossing,
    get_checkpoint_statuses,
    get_closed_checkpoints,
)
from ui_helpers import send_default_main_menu, send_db_error_message
from distance_optimizer import handle_plan_route_cmd, handle_plan_callback

configure_logging()
logger = logging.getLogger(__name__)


EXPECTED_SECRET = os.environ.get("TELEGRAM_SECRET_TOKEN")


# ---------------------------------------------------------------------------
# Telegram API wrapper
# ---------------------------------------------------------------------------

async def _answer_callback_query(query_id: str) -> None:
    logger.info("_answer_callback_query | query_id=%s", query_id)
    await send_telegram_request("answerCallbackQuery", {"callback_query_id": query_id})


# ---------------------------------------------------------------------------
# State store
# ---------------------------------------------------------------------------

async def get_user_state(chat_id: int) -> str:
    try:
        return STATE_IN_QUEUE if await session_exists(chat_id) else STATE_IDLE
    except Exception:
        logger.exception("get_user_state | Redis lookup failed | chat_id=%s", chat_id)
        return STATE_IDLE


# ---------------------------------------------------------------------------
# IDLE state handlers
# ---------------------------------------------------------------------------

async def send_country_selection(chat_id: int, prefix: str = "country") -> None:
    logger.info("send_country_selection | chat_id=%s prefix=%s", chat_id, prefix)
    buttons = [
        [{"text": meta["name"], "callback_data": f"{prefix}:{code}"}]
        for code, meta in COUNTRIES_AND_CHECKPOINTS.items()
    ]
    if prefix == "country":
        cancel_callback = "cancel:country"
    elif prefix == "stats_country":
        cancel_callback = "cancel:stats_country"
    else:
        cancel_callback = "cancel:flow"

    buttons.append([{"text": CMD_CANCEL, "callback_data": cancel_callback}])
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": "Оберіть країну:",
        "reply_markup": {"inline_keyboard": buttons},
    })
 

async def handle_idle_input(chat_id: int, text: str) -> None:
    logger.info("handle_idle_input | chat_id=%s text=%r", chat_id, text)

    if text == "/start":
        logger.info("Route: IDLE → /start | chat_id=%s", chat_id)
        await send_main_menu(chat_id, GREETINGS_PROMPT)
    elif text == CMD_START_CROSSING:
        logger.info("Route: IDLE → start_crossing | chat_id=%s", chat_id)
        await increment_main_menu_analytics("start_crossing")
        await increment_crossing_funnel_analytics("step_0_started")
        try:
            if await has_recent_crossing(chat_id, MIN_CROSSING_INTERVAL_MINUTES):
                logger.info("Route: IDLE → start_crossing blocked | recent crossing found | chat_id=%s", chat_id)
                await send_main_menu(chat_id, ERROR_TOO_FREQUENT_CROSSING)
                return
        except Exception:
            logger.exception("Route: IDLE → start_crossing | DB check failed | chat_id=%s", chat_id)
        await send_country_selection(chat_id)
    elif text == "/addstats":
        logger.info("Route: IDLE → /addstats | chat_id=%s", chat_id)
        if is_admin(chat_id):
            await handle_addstats_cmd(chat_id)
        else:
            await send_main_menu(chat_id, PROMPT_CHOOSE_ACTION)
    elif text == CMD_STATS:
        logger.info("Route: IDLE → stats | chat_id=%s", chat_id)
        await increment_main_menu_analytics("view_stats")
        await increment_stats_funnel_analytics("step_0_started")
        await send_country_selection(chat_id, prefix="stats_country")
    elif text == CMD_PLAN_ROUTE:
        logger.info("Route: IDLE → plan route | chat_id=%s", chat_id)
        await increment_main_menu_analytics("plan_route")
        await increment_plan_route_funnel_analytics("step_0_started")
        await handle_plan_route_cmd(chat_id)
    elif text == CMD_INFO:
        logger.info("Route: IDLE → info | chat_id=%s", chat_id)
        await increment_main_menu_analytics("view_info")
        await increment_info_analytics("views")
        await send_main_menu(chat_id, INFO_PROMPT)
    else:
        logger.info("Route: IDLE → unrecognised input | chat_id=%s text=%r", chat_id, text)
        await send_main_menu(chat_id, PROMPT_CHOOSE_ACTION)


# ---------------------------------------------------------------------------
# IN_QUEUE state handlers
# ---------------------------------------------------------------------------

async def handle_crossed(chat_id: int) -> None:
    logger.info("handle_crossed | chat_id=%s", chat_id)
    try:
        session = await get_session(chat_id)

        if not session:
            logger.warning("handle_crossed | no active session found | chat_id=%s", chat_id)
            await send_default_main_menu(chat_id)
            return

        checkpoint_id = session.get("checkpoint_id")
        await increment_crossing_event_analytics(checkpoint_id, "passed")

        now = datetime.now(timezone.utc)
        started_at = datetime.fromisoformat(session["started_at"])
        duration_seconds = int((now - started_at).total_seconds())

        if duration_seconds < 180:
            logger.info("handle_crossed | crossing too fast (spam) | chat_id=%s duration_seconds=%s", chat_id, duration_seconds)
            await delete_session(chat_id)
            await send_default_main_menu(chat_id)
            return

        direction = session["direction"]
        min_valid_duration = 600 if direction == "INBOUND" else 1200

        if duration_seconds < min_valid_duration:
            logger.info("handle_crossed | crossing fast, asking for confirmation | chat_id=%s duration_seconds=%s", chat_id, duration_seconds)
            await update_session_completed_at(chat_id, now.isoformat())

            await send_telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "Час, який ви витратили на перетин кордону, здається занадто швидким. Ви впевнені, що надали коректну інформацію?",
                "reply_markup": {"inline_keyboard": [
                    [{"text": "Я натиснув \"почати перетин\" пізніше", "callback_data": "fast_cross:adj"}],
                    [{"text": "Кордон був пустим", "callback_data": "fast_cross:empty"}],
                    [{"text": "Просто тестую", "callback_data": "fast_cross:spam"}],
                ]},
            })
            return

        crossing_id = await save_crossing_and_cleanup(
            chat_id,
            session["checkpoint_id"],
            session["direction"],
            session["started_at"],
            now.isoformat(),
            duration_seconds
        )
        if not crossing_id:
            await send_db_error_message(chat_id, ERROR_DB_SAVE)
            return

    except Exception:
        logger.exception("handle_crossed | DB operation failed | chat_id=%s", chat_id)
        await send_db_error_message(chat_id, ERROR_DB_SAVE)
        return

    hours, remainder = divmod(duration_seconds, 3600)
    minutes = remainder // 60
    duration_str = f"{hours}г {minutes:02d}хв" if hours else f"{minutes} хв"

    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": (
            f"Вітаємо із перетином кордону! 🎉\n"
            f"Час очікування: <b>{duration_str}</b>\n\n"
            "Я зафіксував час проходження. Якщо ви насправді пройшли трохи раніше і "
            "просто пізно згадали про бот, можете скоригувати час для точнішої статистики інших водіїв:"
        ),
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [
            [
                {"text": "15 хв тому",    "callback_data": f"adjust_crossing:{crossing_id}:15"},
                {"text": "30 хв тому",    "callback_data": f"adjust_crossing:{crossing_id}:30"},
            ],
            [
                {"text": "1 година тому",  "callback_data": f"adjust_crossing:{crossing_id}:60"},
                {"text": "2 години тому", "callback_data": f"adjust_crossing:{crossing_id}:120"},
            ],
        ]},
    })
    await send_default_main_menu(chat_id)


async def handle_still_waiting(
    chat_id: int,
    callback_query_id: str | None = None,
    message_id: int | None = None,
) -> None:
    try:
        session = await get_session(chat_id)
        checkpoint_id = session.get("checkpoint_id") if session else None
        await increment_crossing_event_analytics(checkpoint_id, "still_waiting")
        await update_last_user_action(chat_id, datetime.now(timezone.utc).isoformat())
        logger.info("handle_still_waiting | session updated | chat_id=%s", chat_id)
    except Exception:
        logger.exception("handle_still_waiting | DB update failed | chat_id=%s", chat_id)
        if callback_query_id:
            await send_telegram_request("answerCallbackQuery", {
                "callback_query_id": callback_query_id,
                "text": ERROR_DB_UPDATE,
                "show_alert": True,
            })
        else:
            await send_telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": ERROR_DB_UPDATE,
            })
        return

    response_text = random.choice(STILL_WAITING_RESPONSES)
    if callback_query_id:
        await send_telegram_request("answerCallbackQuery", {
            "callback_query_id": callback_query_id,
            "text": response_text,
        })
    else:
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": response_text,
        })


async def handle_cancel_queue(chat_id: int) -> None:
    logger.info("handle_cancel_queue | chat_id=%s", chat_id)
    try:
        session = await get_session(chat_id)
        checkpoint_id = session.get("checkpoint_id") if session else None
        await increment_crossing_event_analytics(checkpoint_id, "cancel")
        await delete_session(chat_id)
        logger.info("handle_cancel_queue | session deleted | chat_id=%s", chat_id)
    except Exception:
        logger.exception("handle_cancel_queue | DB delete failed | chat_id=%s", chat_id)
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": ERROR_DB_CANCEL,
        })
        return
    await send_default_main_menu(chat_id)


async def handle_active_queue_input(chat_id: int, text: str) -> None:
    logger.info("handle_active_queue_input | chat_id=%s text=%r", chat_id, text)

    if text == CMD_CROSSED:
        logger.info("Route: IN_QUEUE → handle_crossed | chat_id=%s", chat_id)
        await handle_crossed(chat_id)
    elif text == CMD_STILL_WAITING:
        logger.info("Route: IN_QUEUE → handle_still_waiting | chat_id=%s", chat_id)
        await handle_still_waiting(chat_id)
    elif text == CMD_CANCEL:
        logger.info("Route: IN_QUEUE → handle_cancel_queue | chat_id=%s", chat_id)
        await handle_cancel_queue(chat_id)
    else:
        logger.info("Route: IN_QUEUE → unrecognised input, re-sending queue keyboard | chat_id=%s text=%r", chat_id, text)
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "Ви вже в черзі. Скористайтесь кнопками нижче.",
            "reply_markup": {
                "keyboard": [
                    [{"text": CMD_CROSSED}],
                    [{"text": CMD_STILL_WAITING}],
                    [{"text": CMD_CANCEL}],
                ],
                "resize_keyboard": True,
                "one_time_keyboard": False,
            },
        })


# ---------------------------------------------------------------------------
# Callback query routing
# ---------------------------------------------------------------------------

async def handle_inline_cancel(chat_id: int, message_id: int) -> None:
    logger.info("handle_inline_cancel | chat_id=%s message_id=%s", chat_id, message_id)
    await send_telegram_request("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": "❌ Введення скасовано.",
        "reply_markup": {},
    })
    await send_default_main_menu(chat_id)


async def handle_country_selected(chat_id: int, country_code: str, prefix: str = "checkpoint") -> None:
    logger.info("handle_country_selected | chat_id=%s country=%s prefix=%s", chat_id, country_code, prefix)
    country = COUNTRIES_AND_CHECKPOINTS.get(country_code)
    if not country:
        logger.warning("handle_country_selected | unknown country_code=%s", country_code)
        return

    if prefix == "checkpoint":
        await increment_crossing_country_analytics(country_code)
        await increment_crossing_funnel_analytics("step_1_country_selected")

    closed_checkpoints = await get_closed_checkpoints()
    buttons = [
        [{
            "text": f"{CHECKPOINT_CLOSED_ICON} {name} (закрито)" if cp_id in closed_checkpoints else name,
            "callback_data": f"{prefix}:{country_code}:{cp_id}",
        }]
        for cp_id, name in country["checkpoints"].items()
    ]
    cancel_callback = "cancel:checkpoint" if prefix == "checkpoint" else "cancel:flow"
    buttons.append([{"text": CMD_CANCEL, "callback_data": cancel_callback}])
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"Оберіть пункт пропуску ({country['name']}):",
        "reply_markup": {"inline_keyboard": buttons},
    })


async def handle_checkpoint_selected(
    chat_id: int, country_code: str, checkpoint_id: str, prefix: str = "direction"
) -> None:
    logger.info(
        "handle_checkpoint_selected | chat_id=%s country=%s checkpoint=%s prefix=%s",
        chat_id, country_code, checkpoint_id, prefix,
    )
    checkpoint_name = COUNTRIES_AND_CHECKPOINTS.get(country_code, {}).get("checkpoints", {}).get(checkpoint_id, checkpoint_id)

    if prefix == "direction":
        closed_checkpoints = await get_closed_checkpoints()
        if checkpoint_id in closed_checkpoints:
            logger.info("handle_checkpoint_selected | blocked closed checkpoint | checkpoint=%s", checkpoint_id)
            reason = closed_checkpoints[checkpoint_id] or "Пункт пропуску тимчасово недоступний."
            await send_telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": CHECKPOINT_CLOSED_MESSAGE.format(icon=CHECKPOINT_CLOSED_ICON, name=checkpoint_name, reason=reason),
                "parse_mode": "HTML",
            })
            await handle_country_selected(chat_id, country_code, prefix="checkpoint")
            return
        await increment_checkpoint_analytics(checkpoint_id)
        await increment_crossing_funnel_analytics("step_2_checkpoint_selected")
    cancel_callback = "cancel:direction" if prefix == "direction" else "cancel:flow"
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"Оберіть напрямок руху ({checkpoint_name}):",
        "reply_markup": {"inline_keyboard": [
            [{"text": "🇪🇺 Виїзд з України", "callback_data": f"{prefix}:{checkpoint_id}:OUTBOUND"}],
            [{"text": "🇺🇦 В'їзд в Україну",  "callback_data": f"{prefix}:{checkpoint_id}:INBOUND"}],
            [{"text": CMD_CANCEL,              "callback_data": cancel_callback}],
        ]},
    })


async def handle_direction_selection(
    chat_id: int, message_id: int, checkpoint_id: str, direction: str
) -> None:
    logger.info(
        "handle_direction_selection | chat_id=%s checkpoint=%s direction=%s",
        chat_id, checkpoint_id, direction,
    )
    await increment_direction_analytics(checkpoint_id, direction)
    await increment_crossing_funnel_analytics("step_3_completed")
    now = datetime.now(timezone.utc).isoformat()
    try:
        await upsert_session(
            chat_id=chat_id,
            checkpoint_id=checkpoint_id,
            direction=direction,
            started_at=now,
            last_reminded_at=now,
            last_user_action_at=now,
        )
        logger.info("handle_direction_selection | session upserted | chat_id=%s", chat_id)
    except Exception:
        logger.exception("handle_direction_selection | DB upsert failed | chat_id=%s", chat_id)
        await send_db_error_message(chat_id, ERROR_DB_SAVE)
        return

    checkpoint_name = None
    for country in COUNTRIES_AND_CHECKPOINTS.values():
        if checkpoint_id in country["checkpoints"]:
            checkpoint_name = country["checkpoints"][checkpoint_id]
            break

    direction_text = "🇪🇺 Виїзд з України" if direction == "OUTBOUND" else "🇺🇦 В'їзд в Україну"

    await send_telegram_request("editMessageText", {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       f"⏱ Сесія розпочата.\n\nПункт пропуску: <b>{checkpoint_name}</b>\nНапрямок: {direction_text}\n\nУдачі вам!",
        "parse_mode": "HTML",
        "reply_markup": {},
    })
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": (
            "Натисніть <b>✅ Я проїхав!</b> одразу, як проїдете кордон, або "
            "<b>❌ Скасувати</b> якщо ви змінили плани."
        ),
        "parse_mode": "HTML",
        "reply_markup": {
            "keyboard": [
                [{"text": CMD_CROSSED}],
                [{"text": CMD_STILL_WAITING}],
                [{"text": CMD_CANCEL}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False,
        },
    })
    logger.info("handle_direction_selection | IN_QUEUE keyboard sent | chat_id=%s", chat_id)


async def handle_fast_cross(
    chat_id: int, message_id: int, query_id: str, sub_action: str, parts: list[str]
) -> None:
    logger.info("handle_fast_cross | chat_id=%s sub_action=%s", chat_id, sub_action)
    try:
        session = await get_session(chat_id)
        if not session:
            await send_telegram_request("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "Час дії сесії вичерпано.",
                "reply_markup": {}
            })
            return

        if sub_action == "spam":
            await delete_session(chat_id)
            await send_telegram_request("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "Дякуємо, дані не збережено.",
                "reply_markup": {}
            })
            await send_default_main_menu(chat_id)
            return

        elif sub_action == "empty":
            completed_at_str = session.get("completed_at") or datetime.now(timezone.utc).isoformat()
            completed_at = datetime.fromisoformat(completed_at_str)
            started_at = datetime.fromisoformat(session["started_at"])
            duration_seconds = int((completed_at - started_at).total_seconds())

            crossing_id = await save_crossing_and_cleanup(
                chat_id,
                session["checkpoint_id"],
                session["direction"],
                session["started_at"],
                completed_at.isoformat(),
                duration_seconds
            )
            if not crossing_id:
                raise Exception("save_crossing_and_cleanup failed")

            await send_telegram_request("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "✅ Дані успішно збережено до бази!",
                "reply_markup": {}
            })
            await send_default_main_menu(chat_id)
            return

        elif sub_action == "adj":
            if len(parts) == 2:
                await send_telegram_request("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": "На скільки раніше ви насправді почали перетин?",
                    "reply_markup": {"inline_keyboard": [
                        [
                            {"text": "-15 хв", "callback_data": "fast_cross:adj:15"},
                            {"text": "-30 хв", "callback_data": "fast_cross:adj:30"},
                            {"text": "-1 год", "callback_data": "fast_cross:adj:60"},
                        ],
                        [
                            {"text": "-2 год", "callback_data": "fast_cross:adj:120"},
                            {"text": "-4 год", "callback_data": "fast_cross:adj:240"},
                            {"text": "набагато раніше", "callback_data": "fast_cross:ask_custom"},
                        ],
                    ]},
                })
                return
            elif len(parts) == 3:
                minutes = int(parts[2])
                started_at = datetime.fromisoformat(session["started_at"]) - timedelta(minutes=minutes)
                completed_at_str = session.get("completed_at") or datetime.now(timezone.utc).isoformat()
                completed_at = datetime.fromisoformat(completed_at_str)
                duration_seconds = int((completed_at - started_at).total_seconds())

                crossing_id = await save_crossing_and_cleanup(
                    chat_id,
                    session["checkpoint_id"],
                    session["direction"],
                    started_at.isoformat(),
                    completed_at.isoformat(),
                    duration_seconds
                )
                if not crossing_id:
                    raise Exception("save_crossing_and_cleanup failed")

                await send_telegram_request("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": "✅ Час відкориговано та збережено!",
                    "reply_markup": {}
                })
                await send_default_main_menu(chat_id)
                return

        elif sub_action == "ask_custom":
            await send_telegram_request("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "Введення власного часу...",
                "reply_markup": {}
            })
            await send_telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "Не проблема! Дайте мені знати, скільки годин тому ви почали перетин. Наприклад: 8",
                "reply_markup": {"force_reply": True}
            })
            return

    except Exception:
        logger.exception("handle_fast_cross | operation failed | chat_id=%s", chat_id)
        await send_telegram_request("answerCallbackQuery", {
            "callback_query_id": query_id,
            "text": ERROR_DB_SAVE,
            "show_alert": True,
        })
        return


async def handle_fast_cross_custom_reply(chat_id: int, text: str) -> None:
    logger.info("handle_fast_cross_custom_reply | chat_id=%s text=%r", chat_id, text)
    try:
        hours = float(text.strip().replace(',', '.'))
        if hours < 0:
            raise ValueError("Negative hours")
        minutes = int(hours * 60)
    except ValueError:
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "Не розпізнано число. Будь ласка, надішліть число (наприклад, 8).",
            "reply_markup": {"force_reply": True}
        })
        return

    try:
        session = await get_session(chat_id)
        if not session:
            await send_telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "Час дії сесії вичерпано."
            })
            return

        started_at = datetime.fromisoformat(session["started_at"]) - timedelta(minutes=minutes)
        completed_at_str = session.get("completed_at") or datetime.now(timezone.utc).isoformat()
        completed_at = datetime.fromisoformat(completed_at_str)
        duration_seconds = int((completed_at - started_at).total_seconds())

        crossing_id = await save_crossing_and_cleanup(
            chat_id,
            session["checkpoint_id"],
            session["direction"],
            started_at.isoformat(),
            completed_at.isoformat(),
            duration_seconds
        )
        if not crossing_id:
            raise Exception("save_crossing_and_cleanup failed")

        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "✅ Час відкориговано та збережено!"
        })
        await send_default_main_menu(chat_id)

    except Exception:
        logger.exception("handle_fast_cross_custom_reply | DB operation failed | chat_id=%s", chat_id)
        await send_db_error_message(chat_id, ERROR_DB_SAVE)


async def handle_adjust_crossing(
    chat_id: int, crossing_id: str, adjust_minutes: int, message_id: int, query_id: str
) -> None:
    logger.info(
        "handle_adjust_crossing | chat_id=%s crossing_id=%s adjust_minutes=%s",
        chat_id, crossing_id, adjust_minutes,
    )
    try:
        success = await adjust_border_crossing(crossing_id, adjust_minutes)
        if not success:
            return await send_telegram_request("answerCallbackQuery", {
                "callback_query_id": query_id,
                "text": "⚠️ Невірне коригування. Час проходження не може бути раніше часу початку черги.",
                "show_alert": True,
            })
        logger.info(
            "handle_adjust_crossing | updated | crossing_id=%s adjust_minutes=%s",
            crossing_id, adjust_minutes,
        )
    except Exception:
        logger.exception("handle_adjust_crossing | DB update failed | chat_id=%s", chat_id)
        await send_telegram_request("answerCallbackQuery", {
            "callback_query_id": query_id,
            "text": ERROR_DB_UPDATE,
            "show_alert": True,
        })
        return

    await send_telegram_request("editMessageText", {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       f"✅ Час скориговано на {adjust_minutes} хв раніше. Дякуємо за точні дані! 👍",
        "reply_markup": {},
    })

def format_interval_minutes(total_minutes: int) -> str:
    d_hours = total_minutes // 60
    d_minutes = total_minutes % 60
    if d_hours >= 24:
        return f"{d_hours // 24} дн."
    elif d_hours > 0:
        return f"{d_hours} год {d_minutes} хв"
    else:
        return f"{d_minutes} хв"


async def handle_stats_country_selected(chat_id: int, country_code: str) -> None:
    logger.info("handle_stats_country_selected | chat_id=%s country=%s", chat_id, country_code)
    country = COUNTRIES_AND_CHECKPOINTS.get(country_code)
    if not country:
        return
    await increment_stats_country_analytics(country_code)
    await increment_stats_funnel_analytics("step_1_country_selected")
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"📊 Статистика ({country['name']})\nОберіть напрямок:",
        "reply_markup": {"inline_keyboard": [
            [{"text": "🇪🇺 Виїзд з України", "callback_data": f"stats_dir:{country_code}:OUTBOUND"}],
            [{"text": "🇺🇦 В'їзд в Україну",  "callback_data": f"stats_dir:{country_code}:INBOUND"}],
            [{"text": CMD_CANCEL,              "callback_data": "cancel:stats_direction"}],
        ]},
    })


async def handle_stats_direction_selected(
    chat_id: int, message_id: int, country_code: str, direction: str
) -> None:
    logger.info(
        "handle_stats_direction_selected | chat_id=%s country=%s dir=%s",
        chat_id, country_code, direction,
    )
    country = COUNTRIES_AND_CHECKPOINTS.get(country_code)
    if not country:
        return

    await increment_stats_direction_analytics(country_code, direction)
    await increment_stats_funnel_analytics("step_2_completed")

    await send_telegram_request("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": "⏳ Збираємо останні дані...",
        "reply_markup": {}
    })

    checkpoint_ids = list(country["checkpoints"].keys())
    try:
        stats_data = await get_checkpoint_statuses(checkpoint_ids, direction)
        handles = await get_checkpoint_telegram_handles(checkpoint_ids)
        closed_checkpoints = await get_closed_checkpoints()
    except Exception:
        logger.exception("handle_stats_direction_selected | DB query failed")
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "⚠️ Помилка отримання даних. Спробуйте пізніше."
        })
        return

    latest_stats = {}
    for row in stats_data:
        cp_id = row["checkpoint_id"]
        latest_stats[cp_id] = row

    direction_str = "Виїзд з України 🇪🇺" if direction == "OUTBOUND" else "В'їзд в Україну 🇺🇦"
    lines = [
        f"📊 <b>Статистика: {country['name']} ({direction_str})</b>\n",
        "<blockquote>ℹ️ <b>Зверніть увагу:</b> Поки наша спільнота зростає, ми тимчасово збираємо дані вручну з профільних чатів. Щойно кількість користувачів збільшиться, тут з'являтиметься автоматична статистика від реальних водіїв!</blockquote>\n"
    ]

    now = datetime.now(timezone.utc)
    has_stats, no_stats = [], []

    for cp_id, cp_name in country["checkpoints"].items():
        if cp_id in closed_checkpoints:
            continue
        if cp_id in latest_stats:
            has_stats.append((cp_id, cp_name, latest_stats[cp_id]))
        else:
            no_stats.append((cp_id, cp_name))

    # Sort checkpoints by the most recently updated to help users find the "best" info first
    has_stats.sort(key=lambda x: x[2]["updated_at"], reverse=True)

    for cp_id, cp_name in country["checkpoints"].items():
        if cp_id not in closed_checkpoints:
            continue
        reason = closed_checkpoints[cp_id] or "Пункт пропуску тимчасово недоступний."
        lines.append(f"{CHECKPOINT_CLOSED_ICON} <b>{cp_name} — ЗАКРИТО</b>\n{reason}\n")

    for cp_id, cp_name, row in has_stats:
        handle = handles.get(cp_id)
        if handle:
            cp_display = f"<a href='https://t.me/{handle}'>{cp_name}</a>"
        else:
            cp_display = cp_name

        # Safely parse Supabase timestamp
        updated_at_str = row["updated_at"].replace("Z", "+00:00")
        updated_at = datetime.fromisoformat(updated_at_str)

        diff = now - updated_at
        total_minutes = int(diff.total_seconds() // 60)
        time_ago = f"{format_interval_minutes(total_minutes)} тому"

        dur = row.get("avg_duration_minutes")
        dur_str = f" (~{format_interval_minutes(int(dur))})" if dur is not None else ""

        icon = "🔹"
        if row.get("is_jammed"):
            icon = "🛑"
        elif row.get("is_warning"):
            icon = "⚠️"

        data_source = row.get("data_source", "UNKNOWN")
        if data_source == "ACTUAL":
            ds_text = f"(на основі {row.get('reports_count', 0)} реальних звітів)"
        else:
            ds_text = "(на основі аналізу публічних даних)"

        lines.append(f"{icon} <b>{cp_display}</b>{dur_str}\n🕒 <i>Оновлено: {time_ago} {ds_text}</i>\n")

    for cp_id, cp_name in no_stats:
        handle = handles.get(cp_id)
        if handle:
            cp_display = f"<a href='https://t.me/{handle}'>{cp_name}</a>"
        else:
            cp_display = cp_name
        lines.append(f"🔹 <b>{cp_display}</b>\n🤷 Немає свіжих даних\n")

    lines.append("💡 Натисніть на назву пункту пропуску, щоб перейти в його чат.")

    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": "\n".join(lines),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "link_preview_options": {"is_disabled": True}
    })


async def route_callback_query(
    chat_id: int, data: str, query_id: str, message_id: int
) -> None:
    logger.info("route_callback_query | chat_id=%s data=%r", chat_id, data)
    await _answer_callback_query(query_id)

    parts = data.split(":")
    action = parts[0]

    if action == "country" and len(parts) == 2:
        logger.info("Route: callback → country_selected | chat_id=%s", chat_id)
        await handle_country_selected(chat_id, parts[1])

    elif action == "checkpoint" and len(parts) == 3:
        logger.info("Route: callback → checkpoint_selected | chat_id=%s", chat_id)
        await handle_checkpoint_selected(chat_id, parts[1], parts[2])

    elif action == "direction" and len(parts) == 3:
        logger.info("Route: callback → direction_selected | chat_id=%s checkpoint=%s direction=%s", chat_id, parts[1], parts[2])
        await handle_direction_selection(chat_id, message_id, parts[1], parts[2])

    elif action == "stats_country" and len(parts) == 2:
        logger.info("Route: callback → stats_country | chat_id=%s country=%s", chat_id, parts[1])
        await handle_stats_country_selected(chat_id, parts[1])

    elif action == "stats_dir" and len(parts) == 3:
        logger.info("Route: callback → stats_dir | chat_id=%s country=%s dir=%s", chat_id, parts[1], parts[2])
        await handle_stats_direction_selected(chat_id, message_id, parts[1], parts[2])

    elif action == "admin_country" and len(parts) == 2:
        logger.info("Route: callback → admin_country | chat_id=%s country=%s", chat_id, parts[1])
        await handle_country_selected(chat_id, parts[1], prefix="admin_cp")

    elif action == "admin_cp" and len(parts) == 3:
        logger.info("Route: callback → admin_cp | chat_id=%s cp=%s", chat_id, parts[2])
        await handle_checkpoint_selected(chat_id, parts[1], parts[2], prefix="admin_dir")

    elif action == "admin_dir" and len(parts) == 3:
        logger.info("Route: callback → admin_dir | chat_id=%s dir=%s", chat_id, parts[2])
        await handle_admin_direction_selected(chat_id, message_id, parts[1], parts[2])

    elif action == "admin_start":
        logger.info("Route: callback → admin_start | chat_id=%s", chat_id)
        await handle_addstats_cmd(chat_id)

    elif action.startswith("plan_"):
        logger.info("Route: callback → plan route | chat_id=%s action=%s", chat_id, action)
        await handle_plan_callback(chat_id, message_id, parts)

    elif action == "fast_cross" and len(parts) >= 2:
        logger.info("Route: callback → fast_cross | chat_id=%s sub_action=%s", chat_id, parts[1])
        await handle_fast_cross(chat_id, message_id, query_id, parts[1], parts)

    elif action == "adjust_crossing" and len(parts) == 3:
        logger.info("Route: callback → adjust_crossing | chat_id=%s crossing_id=%s minutes=%s", chat_id, parts[1], parts[2])
        await handle_adjust_crossing(chat_id, parts[1], int(parts[2]), message_id, query_id)

    elif action == "still_waiting" and len(parts) == 2:
        logger.info("Route: callback → still_waiting | chat_id=%s", chat_id)
        await handle_still_waiting(chat_id, query_id, message_id)

    elif action == "cancel":
        logger.info("Route: callback → inline_cancel | chat_id=%s", chat_id)
        screen = parts[1] if len(parts) > 1 else None
        if screen == "country":
            await increment_cancel_funnel_analytics("cancel_at_country")
        elif screen == "checkpoint":
            await increment_cancel_funnel_analytics("cancel_at_checkpoint")
        elif screen == "direction":
            await increment_cancel_funnel_analytics("cancel_at_direction")
        elif screen == "stats_country":
            await increment_stats_cancel_funnel_analytics("cancel_at_country")
        elif screen == "stats_direction":
            await increment_stats_cancel_funnel_analytics("cancel_at_direction")
        elif screen == "plan_country":
            await increment_plan_route_cancel_funnel_analytics("cancel_at_country")
        elif screen == "plan_direction":
            await increment_plan_route_cancel_funnel_analytics("cancel_at_direction")
        elif screen == "plan_origin":
            await increment_plan_route_cancel_funnel_analytics("cancel_at_origin")
        elif screen == "plan_destination":
            await increment_plan_route_cancel_funnel_analytics("cancel_at_destination")
        await handle_inline_cancel(chat_id, message_id)

    elif action == "close_success":
        logger.info("Route: callback → close_success | chat_id=%s", chat_id)
        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "✅ Дані успішно збережено до бази!",
            "reply_markup": {}
        })
        await send_main_menu(chat_id, PROMPT_CHOOSE_ACTION)

    else:
        logger.warning("route_callback_query | unrecognised action=%r chat_id=%s", action, chat_id)


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

def _extract_request(body: dict) -> tuple[int | None, str | None, str | None, int | None, dict | None]:
    """
    Returns (chat_id, text_or_data, query_id, message_id, reply_to_message).
    query_id and message_id are set only for callback queries.
    """
    if "callback_query" in body:
        cq = body["callback_query"]
        msg = cq["message"]
        return msg["chat"]["id"], cq.get("data", ""), cq["id"], msg["message_id"], None

    message = body.get("message") or body.get("edited_message")
    if message:
        return message["chat"]["id"], message.get("text", ""), None, None, message.get("reply_to_message")

    return None, None, None, None, None


# ---------------------------------------------------------------------------
# Web server entry point
# ---------------------------------------------------------------------------

async def process_update(body: dict) -> None:
    """Process a single Telegram update dict. Called from the FastAPI webhook route."""
    logger.info("update_id=%s", body.get("update_id"))

    chat_id, payload, query_id, message_id, reply_to_message = _extract_request(body)

    if chat_id is None:
        logger.info("No actionable message found, ignoring update")
        return

    await track_unique_user(chat_id)

    # Intercept admin's ForceReply before processing normal state
    if reply_to_message:
        if await handle_admin_reply(chat_id, payload, reply_to_message):
            logger.info("Admin ForceReply handled successfully")
            return
        
        reply_text = reply_to_message.get("text", "")
        if "Не проблема! Дайте мені знати, скільки годин тому ви почали перетин." in reply_text or "Не розпізнано число." in reply_text:
            await handle_fast_cross_custom_reply(chat_id, payload)
            return

    if query_id is not None:
        await route_callback_query(chat_id, payload, query_id, message_id)
    else:
        state = await get_user_state(chat_id)
        logger.info("User state | chat_id=%s state=%s", chat_id, state)

        if state == STATE_IDLE:
            await handle_idle_input(chat_id, payload)
        elif state == STATE_IN_QUEUE:
            await handle_active_queue_input(chat_id, payload)
        else:
            logger.warning("Unknown state=%r for chat_id=%s", state, chat_id)
