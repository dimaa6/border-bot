import logging
import os
import re

from clients import get_supabase, send_telegram_request
from checkpoints import COUNTRIES_AND_CHECKPOINTS

logger = logging.getLogger(__name__)

ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID")


def is_admin(chat_id: int) -> bool:
    if not ADMIN_USER_ID:
        return False
    return str(chat_id) == str(ADMIN_USER_ID)


def handle_addstats_cmd(chat_id: int):
    logger.info("handle_addstats_cmd | starting admin flow for chat_id=%s", chat_id)
    buttons = [
        [{"text": meta["name"], "callback_data": f"admin_country:{code}"}]
        for code, meta in COUNTRIES_AND_CHECKPOINTS.items()
    ]
    buttons.append([{"text": "❌ Скасувати", "callback_data": "cancel:flow"}])
    
    send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": "🛡 <b>Адмін-панель</b>\nОберіть країну для додавання статистики:",
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": buttons},
    })


def handle_admin_direction_selected(chat_id: int, message_id: int, checkpoint_id: str, direction: str):
    logger.info("handle_admin_direction_selected | chat_id=%s checkpoint=%s dir=%s", chat_id, checkpoint_id, direction)
    
    # 1. Clear out the inline keyboard so it doesn't clutter the chat
    send_telegram_request("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": "Готую форму введення...",
        "reply_markup": {}
    })
    
    # 2. Send the ForceReply prompt containing the hidden context we need
    send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"✍️ Введіть статус із чату (просто текст):\n\n[ADMIN:{checkpoint_id}:{direction}]",
        "reply_markup": {
            "force_reply": True,
            "input_field_placeholder": "Напр: Черга 10 машин..."
        }
    })


def handle_admin_reply(chat_id: int, text: str, reply_to_message: dict) -> bool:
    """Parses a reply to the bot. Returns True if handled, False otherwise."""
    if not is_admin(chat_id):
        return False
        
    original_text = reply_to_message.get("text", "")
    match = re.search(r"\[ADMIN:([\w_]+):(INBOUND|OUTBOUND)\]", original_text)
    if not match:
        return False
        
    checkpoint_id, direction = match.groups()
    
    # Replace severity flags with corresponding emojis (case-insensitive)
    formatted_text = re.sub(r'(?i)\(s\)', '🛑', text)
    formatted_text = re.sub(r'(?i)\(w\)', '⚠️', formatted_text)
    
    logger.info("handle_admin_reply | parsed %s %s text=%r", checkpoint_id, direction, formatted_text)
    
    try:
        get_supabase().table("time_stat").insert({
            "checkpoint_id": checkpoint_id,
            "direction": direction,
            "comment": formatted_text,
            "is_manual": True
        }).execute()
        
        country_code = checkpoint_id.split('_')[0]
        country_name = COUNTRIES_AND_CHECKPOINTS.get(country_code, {}).get("name", country_code)

        send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "✅ Дані успішно збережено до бази!",
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": f"🔄 Додати ще ({country_name})", "callback_data": f"admin_country:{country_code}"}],
                    [{"text": "🌍 Інша країна", "callback_data": "admin_start"}],
                    [{"text": "❌ Закрити", "callback_data": "close_success"}]
                ]
            }
        })
    except Exception:
        logger.exception("handle_admin_reply | DB insert failed")
        send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "⚠️ Помилка збереження в базу даних."
        })
        
    return True