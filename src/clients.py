import logging
import os

import httpx
from supabase import acreate_client, AsyncClient

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUPABASE_URL       = os.environ.get("SUPABASE_URL")
SUPABASE_KEY       = os.environ.get("SUPABASE_SERVICE_KEY")

_supabase: AsyncClient | None = None
_http: httpx.AsyncClient | None = None


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

async def init_supabase() -> None:
    """Initialise the async Supabase client. Must be called once at startup."""
    global _supabase
    _supabase = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("init_supabase | async client ready")


def get_supabase() -> AsyncClient:
    """Return the already-initialised async Supabase client."""
    return _supabase


# ---------------------------------------------------------------------------
# HTTP (Telegram)
# ---------------------------------------------------------------------------

def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=10.0)
    return _http


async def send_telegram_request(method: str, payload: dict) -> dict | None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        resp = await _get_http().post(url, json=payload)
        body = resp.json()
        logger.info("send_telegram_request | method=%s ok=%s", method, body.get("ok"))
        return body
    except httpx.HTTPStatusError as e:
        logger.error(
            "send_telegram_request | method=%s HTTP %s body=%s",
            method, e.response.status_code, e.response.text,
        )
    except httpx.RequestError as e:
        logger.error("send_telegram_request | method=%s error=%s", method, e)
    return None


async def send_main_menu(
    chat_id: int,
    text_prompt: str,
    cmd_start_crossing: str,
    cmd_stats: str,
    cmd_info: str,
) -> None:
    logger.info("send_main_menu | chat_id=%s", chat_id)
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": text_prompt,
        "parse_mode": "HTML",
        "link_preview_options": {
            "is_disabled": True,
        },
        "reply_markup": {
            "keyboard": [
                [{"text": cmd_start_crossing}],
                [{"text": cmd_stats}, {"text": cmd_info}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False,
            "is_persistent": True,
        },
    })
