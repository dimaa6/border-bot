import json
import logging
import os
import urllib.request
import urllib.error

from supabase import create_client, Client

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUPABASE_URL       = os.environ.get("SUPABASE_URL")
SUPABASE_KEY       = os.environ.get("SUPABASE_SERVICE_KEY")

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


def delete_active_session(chat_id: int) -> None:
    get_supabase().table("active_sessions") \
        .delete() \
        .eq("chat_id", chat_id) \
        .execute()


def send_telegram_request(method: str, payload: dict) -> dict | None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            logger.info("send_telegram_request | method=%s ok=%s", method, body.get("ok"))
            return body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        logger.error("send_telegram_request | method=%s HTTP %s body=%s", method, e.code, body)
    except urllib.error.URLError as e:
        logger.error("send_telegram_request | method=%s URLError %s", method, e.reason)
    return None
