import json
import logging
import os
from datetime import datetime, timezone

from clients import get_supabase, send_telegram_request, delete_active_session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPECTED_SECRET = os.environ.get("TELEGRAM_SECRET_TOKEN")

# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

COUNTRIES_AND_CHECKPOINTS = {
    "PL": {
        "name": "Польща",
        "checkpoints": {
            "PL_KRAKOVETS":     "Краківець",
            "PL_SHEHYNI":       "Шегині",
            "PL_RAVA":          "Рава-Руська",
            "PL_USTYLUH":       "Устилуг",
            "PL_UHRYNIV":       "Угринів",
            "PL_HRUSHIV":       "Грушів",
            "PL_NIZHANKOVICHI": "Нижанковичі",
            "PL_SMILNYTSIA":    "Смільниця",
        },
    },
}

# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------

STATE_IDLE = "IDLE"
STATE_IN_QUEUE = "IN_QUEUE"

# ---------------------------------------------------------------------------
# Text command constants
# ---------------------------------------------------------------------------
GREETINGS_PROMPT = (
    "<b>Вітаємо!</b>\n\n"
    "Цей бот створено, щоб ми разом могли бачити реальний час очікування у пунктах пропуску та оптимально планувати поїздки.\n\n"
    "📢 <b>Важливе оголошення для перших користувачів:</b>\n"
    "Зараз ми запускаємо відкрите бета-тестування. Статистика перетинів поки порожня — і саме ви можете допомогти її наповнити! "
    "Що більше реальних поїздок ми зафіксуємо, то точнішими будуть прогнози для кожного з нас.\n\n"
    "<b>Як допомогти спільноті прямо зараз?</b>\n"
    "Коли ви будете під'їжджати до кордону, просто запустіть моніторинг у боті. "
    "Натискайте кнопку \"Все ще стою\", поки чекаєте, і обов'язково натисніть \"Я проїхав!\", коли перетнете лінію.\n\n"
    "Кожна ваша хвилина в черзі перетвориться на корисну статистику для наступних водіїв!\n\n"
    "Натисніть <b>«🚗 Почати перетин»</b> у момент, коли ви "
    "реально встали в чергу, щоб зафіксувати точний час початку очікування."
)
CMD_START_CROSSING = "🚗 Почати перетин"
CMD_CROSSED = "✅ Я проїхав!"
CMD_STILL_WAITING = "⏳ Все ще стою"
CMD_CANCEL = "❌ Скасувати"
CMD_STATS = "📊 Статистика"
CMD_INFO = "ℹ️ Інформація"

# ---------------------------------------------------------------------------
# Telegram API wrapper (placeholder)
# ---------------------------------------------------------------------------

def _answer_callback_query(query_id: str):
    logger.info("_answer_callback_query | query_id=%s", query_id)
    send_telegram_request("answerCallbackQuery", {"callback_query_id": query_id})


# ---------------------------------------------------------------------------
# State store (mock)
# ---------------------------------------------------------------------------

def get_user_state(chat_id: int) -> str:
    try:
        result = get_supabase().table("active_sessions") \
            .select("chat_id") \
            .eq("chat_id", chat_id) \
            .maybe_single() \
            .execute()
        return STATE_IN_QUEUE if result.data else STATE_IDLE
    except Exception:
        logger.exception("get_user_state | DB lookup failed | chat_id=%s", chat_id)
        return STATE_IDLE


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------

def send_main_menu(chat_id: int, text_prompt: str):
    logger.info("send_main_menu | chat_id=%s", chat_id)
    send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": text_prompt,
        "parse_mode": "HTML",
        "link_preview_options": {
            "is_disabled": True,
        },
        "reply_markup": {
            "keyboard": [
                [{"text": CMD_START_CROSSING}],
                [{"text": CMD_STATS}, {"text": CMD_INFO}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False,
            "is_persistent": True,
        },
    })


# ---------------------------------------------------------------------------
# IDLE state handlers
# ---------------------------------------------------------------------------

def send_country_selection(chat_id: int):
    logger.info("send_country_selection | chat_id=%s", chat_id)
    buttons = [
        [{"text": meta["name"], "callback_data": f"country:{code}"}]
        for code, meta in COUNTRIES_AND_CHECKPOINTS.items()
    ]
    buttons.append([{"text": CMD_CANCEL, "callback_data": "cancel:flow"}])
    send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": "Оберіть країну:",
        "reply_markup": {"inline_keyboard": buttons},
    })


def handle_idle_input(chat_id: int, text: str):
    logger.info("handle_idle_input | chat_id=%s text=%r", chat_id, text)

    if text == "/start":
        logger.info("Route: IDLE → /start | chat_id=%s", chat_id)
        send_main_menu(chat_id, GREETINGS_PROMPT)
    elif text == CMD_START_CROSSING:
        logger.info("Route: IDLE → start_crossing | chat_id=%s", chat_id)
        send_country_selection(chat_id)
    elif text == CMD_STATS:
        logger.info("Route: IDLE → stats | chat_id=%s", chat_id)
        send_main_menu(chat_id, "Статистика збирається спільнотою. Станьте першим, хто зафіксує чергу сьогодні! 🚀")
    elif text == CMD_INFO:
        logger.info("Route: IDLE → info | chat_id=%s", chat_id)
        send_main_menu(chat_id,
            (
                "📌 <b>Корисна інформація та спільнота</b>\n\n"
                "Наш бот допомагає автоматично збирати та фіксувати час очікування, але для живого обговорення, "
                "форс-мажорів чи додаткових питань обов'язково користуйтеся іншими ресурсами спільноти:\n\n"
                "<a href=\"https://t.me/Ukrainians_border/94\">Актуальні новини на кордоні з Україною</a> — "
                "Головний чат водіїв щодо пунктів пропуску через держкордон України. "
                "Тут можна запитати поради в тих, хто зараз у дорозі.\n\n"
                "<a href=\"https://dpsu.gov.ua/uk\">Держприкордонслужба України</a> — "
                "Офіційний сайт із загальними правилами перетину.\n\n"
                "🤖 <b>Як працює цей бот?</b>\n"
                "Бот працює на принципі взаємодопомоги. Ви фіксуєте свій час початку черги, періодично підтверджуєте присутність, "
                "а коли проїжджаєте — тиснете «Я проїхав!». Ваші дані миттєво формують реальну статистику для наступних водіїв."
            )
        )
    else:
        logger.info("Route: IDLE → unrecognised input | chat_id=%s text=%r", chat_id, text)
        send_main_menu(chat_id, "Оберіть дію:")


# ---------------------------------------------------------------------------
# IN_QUEUE state handlers
# ---------------------------------------------------------------------------

def handle_crossed(chat_id: int):
    logger.info("handle_crossed | chat_id=%s", chat_id)
    try:
        session = get_supabase().table("active_sessions") \
            .select("checkpoint_id, direction, started_at") \
            .eq("chat_id", chat_id) \
            .single() \
            .execute()

        if not session.data:
            logger.warning("handle_crossed | no active session found | chat_id=%s", chat_id)
            send_main_menu(chat_id, GREETINGS_PROMPT)
            return

        now = datetime.now(timezone.utc)
        started_at = datetime.fromisoformat(session.data["started_at"])
        duration_seconds = int((now - started_at).total_seconds())

        get_supabase().table("border_crossings").insert({
            "chat_id":          chat_id,
            "checkpoint_id":    session.data["checkpoint_id"],
            "direction":        session.data["direction"],
            "started_at":       session.data["started_at"],
            "completed_at":     now.isoformat(),
            "duration_seconds": duration_seconds,
        }).execute()

        delete_active_session(chat_id)
        logger.info("handle_crossed | session deleted | chat_id=%s duration_seconds=%s", chat_id, duration_seconds)

    except Exception:
        logger.exception("handle_crossed | DB operation failed | chat_id=%s", chat_id)
        send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "⚠️ Помилка збереження даних. Спробуйте ще раз.",
        })
        return

    hours, remainder = divmod(duration_seconds, 3600)
    minutes = remainder // 60
    duration_str = f"{hours}г {minutes:02d}хв" if hours else f"{minutes} хв"

    send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": (
            f"Вітаємо з перетином кордону! 🎉\n"
            f"Час очікування: <b>{duration_str}</b>\n"
            "Щасливої дороги! 🚗"
        ),
        "parse_mode": "HTML",
        "reply_markup": {"remove_keyboard": True},
    })
    send_main_menu(chat_id, GREETINGS_PROMPT)


def handle_still_waiting(chat_id: int, callback_query_id: str | None = None, message_id: int | None = None):
    try:
        get_supabase().table("active_sessions") \
            .update({"last_user_action_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("chat_id", chat_id) \
            .execute()
        logger.info("handle_still_waiting | session updated | chat_id=%s", chat_id)
    except Exception:
        logger.exception("handle_still_waiting | DB update failed | chat_id=%s", chat_id)
        if callback_query_id:
            send_telegram_request("answerCallbackQuery", {
                "callback_query_id": callback_query_id,
                "text": "⚠️ Помилка оновлення. Спробуйте ще раз.",
                "show_alert": True,
            })
        else:
            send_telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "⚠️ Помилка оновлення. Спробуйте ще раз.",
            })
        return

    if callback_query_id:
        send_telegram_request("answerCallbackQuery", {
            "callback_query_id": callback_query_id,
            "text": "✅ Статус оновлено!",
        })
    else:
        send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "✅ Статус оновлено!",
        })


def handle_cancel_queue(chat_id: int):
    logger.info("handle_cancel_queue | chat_id=%s", chat_id)
    try:
        delete_active_session(chat_id)
        logger.info("handle_cancel_queue | session deleted | chat_id=%s", chat_id)
    except Exception:
        logger.exception("handle_cancel_queue | DB delete failed | chat_id=%s", chat_id)
        send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "⚠️ Помилка скасування. Спробуйте ще раз.",
        })
        return
    send_main_menu(chat_id, GREETINGS_PROMPT)


def handle_active_queue_input(chat_id: int, text: str):
    logger.info("handle_active_queue_input | chat_id=%s text=%r", chat_id, text)

    if text == CMD_CROSSED:
        logger.info("Route: IN_QUEUE → handle_crossed | chat_id=%s", chat_id)
        handle_crossed(chat_id)
    elif text == CMD_STILL_WAITING:
        logger.info("Route: IN_QUEUE → handle_still_waiting | chat_id=%s", chat_id)
        handle_still_waiting(chat_id)
    elif text == CMD_CANCEL:
        logger.info("Route: IN_QUEUE → handle_cancel_queue | chat_id=%s", chat_id)
        handle_cancel_queue(chat_id)
    else:
        logger.info("Route: IN_QUEUE → unrecognised input, re-sending queue keyboard | chat_id=%s text=%r", chat_id, text)
        send_telegram_request("sendMessage", {
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

def handle_inline_cancel(chat_id: int, message_id: int):
    logger.info("handle_inline_cancel | chat_id=%s message_id=%s", chat_id, message_id)
    send_telegram_request("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": "❌ Введення скасовано.",
        "reply_markup": {},
    })
    send_main_menu(chat_id, GREETINGS_PROMPT)


def handle_country_selected(chat_id: int, country_code: str):
    logger.info("handle_country_selected | chat_id=%s country=%s", chat_id, country_code)
    country = COUNTRIES_AND_CHECKPOINTS.get(country_code)
    if not country:
        logger.warning("handle_country_selected | unknown country_code=%s", country_code)
        return
    buttons = [
        [{"text": name, "callback_data": f"checkpoint:{country_code}:{cp_id}"}]
        for cp_id, name in country["checkpoints"].items()
    ]
    buttons.append([{"text": CMD_CANCEL, "callback_data": "cancel:flow"}])
    send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"Оберіть пункт пропуску ({country['name']}):",
        "reply_markup": {"inline_keyboard": buttons},
    })


def handle_checkpoint_selected(chat_id: int, country_code: str, checkpoint_id: str):
    logger.info("handle_checkpoint_selected | chat_id=%s country=%s checkpoint=%s", chat_id, country_code, checkpoint_id)
    checkpoint_name = COUNTRIES_AND_CHECKPOINTS.get(country_code, {}).get("checkpoints", {}).get(checkpoint_id, checkpoint_id)
    send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"Оберіть напрямок руху ({checkpoint_name}):",
        "reply_markup": {"inline_keyboard": [
            [{"text": "🇪🇺 Виїзд з України", "callback_data": f"direction:{checkpoint_id}:OUTBOUND"}],
            [{"text": "🇺🇦 В'їзд в Україну",  "callback_data": f"direction:{checkpoint_id}:INBOUND"}],
            [{"text": CMD_CANCEL,              "callback_data": "cancel:flow"}],
        ]},
    })


def handle_direction_selection(chat_id: int, message_id: int, checkpoint_id: str, direction: str):
    logger.info("handle_direction_selection | chat_id=%s checkpoint=%s direction=%s", chat_id, checkpoint_id, direction)
    now = datetime.now(timezone.utc).isoformat()
    try:
        get_supabase().table("active_sessions").upsert({
            "chat_id":               chat_id,
            "checkpoint_id":         checkpoint_id,
            "direction":             direction,
            "started_at":            now,
            "last_reminded_at":      now,
            "last_user_action_at":   now,
        }, on_conflict="chat_id").execute()
        logger.info("handle_direction_selection | session upserted | chat_id=%s", chat_id)
    except Exception:
        logger.exception("handle_direction_selection | DB upsert failed | chat_id=%s", chat_id)
        send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "⚠️ Помилка збереження даних. Спробуйте ще раз.",
        })
        return

    send_telegram_request("editMessageText", {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       "⏱ Сесія розпочата. Удачі вам!",
        "reply_markup": {},
    })
    send_telegram_request("sendMessage", {
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


def route_callback_query(chat_id: int, data: str, query_id: str, message_id: int):
    logger.info("route_callback_query | chat_id=%s data=%r", chat_id, data)
    _answer_callback_query(query_id)

    parts = data.split(":")
    action = parts[0]

    if action == "country" and len(parts) == 2:
        logger.info("Route: callback → country_selected | chat_id=%s", chat_id)
        handle_country_selected(chat_id, parts[1])

    elif action == "checkpoint" and len(parts) == 3:
        logger.info("Route: callback → checkpoint_selected | chat_id=%s", chat_id)
        handle_checkpoint_selected(chat_id, parts[1], parts[2])

    elif action == "direction" and len(parts) == 3:
        logger.info("Route: callback → direction_selected | chat_id=%s checkpoint=%s direction=%s", chat_id, parts[1], parts[2])
        handle_direction_selection(chat_id, message_id, parts[1], parts[2])

    elif action == "still_waiting" and len(parts) == 2:
        logger.info("Route: callback → still_waiting | chat_id=%s", chat_id)
        handle_still_waiting(chat_id, query_id, message_id)

    elif action == "cancel":
        logger.info("Route: callback → inline_cancel | chat_id=%s", chat_id)
        handle_inline_cancel(chat_id, message_id)

    else:
        logger.warning("route_callback_query | unrecognised action=%r chat_id=%s", action, chat_id)


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

def _extract_request(body: dict) -> tuple[int | None, str | None, str | None, int | None]:
    """
    Returns (chat_id, text_or_data, query_id, message_id).
    query_id and message_id are set only for callback queries.
    """
    if "callback_query" in body:
        cq = body["callback_query"]
        msg = cq["message"]
        return msg["chat"]["id"], cq.get("data", ""), cq["id"], msg["message_id"]

    message = body.get("message") or body.get("edited_message")
    if message:
        return message["chat"]["id"], message.get("text", ""), None, None

    return None, None, None, None


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    headers = event.get("headers") or {}
    received_secret = headers.get("X-Telegram-Bot-Api-Secret-Token") or \
                      headers.get("x-telegram-bot-api-secret-token")

    if received_secret != EXPECTED_SECRET:
        logger.error("Unauthorized webhook request")
        return {"statusCode": 401, "body": "Unauthorized"}

    body = json.loads(event.get("body") or "{}")
    logger.info("update_id=%s", body.get("update_id"))

    chat_id, payload, query_id, message_id = _extract_request(body)

    if chat_id is None:
        logger.info("No actionable message found, ignoring update")
        return {"statusCode": 200, "body": "ok"}

    if query_id is not None:
        route_callback_query(chat_id, payload, query_id, message_id)
    else:
        state = get_user_state(chat_id)
        logger.info("User state | chat_id=%s state=%s", chat_id, state)

        if state == STATE_IDLE:
            handle_idle_input(chat_id, payload)
        elif state == STATE_IN_QUEUE:
            handle_active_queue_input(chat_id, payload)
        else:
            logger.warning("Unknown state=%r for chat_id=%s", state, chat_id)

    return {"statusCode": 200, "body": "ok"}
