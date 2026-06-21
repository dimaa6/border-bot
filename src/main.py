"""
BorderBot – standalone FastAPI webhook server.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import json
import logging
import os

from log_setup import configure_logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

# Load .env when running locally; harmless in production if file is absent.
load_dotenv()

configure_logging()
logger = logging.getLogger(__name__)


EXPECTED_SECRET = os.environ.get("TELEGRAM_SECRET_TOKEN")

# ---------------------------------------------------------------------------
# Scheduler (replaces the stale_sessions Lambda cron trigger)
# ---------------------------------------------------------------------------

# Import here so the module is ready before the scheduler fires
from stale_sessions import check_stale_sessions  # noqa: E402

scheduler = BackgroundScheduler(timezone="UTC")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        check_stale_sessions,
        trigger="cron",
        minute="0,30",
        id="check_stale_sessions",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started – stale-session job runs at :00 and :30 every hour (UTC)")
    yield
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


app = FastAPI(title="BorderBot Webhook", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Webhook route (replaces handler.lambda_handler)
# ---------------------------------------------------------------------------

@app.post("/webhook")
async def webhook(request: Request) -> Response:
    # --- Secret token validation ---
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if received_secret != EXPECTED_SECRET:
        logger.error("Unauthorized webhook request – bad or missing secret token")
        return Response(content="Unauthorized", status_code=401)

    # --- Parse body ---
    try:
        body = await request.json()
    except Exception:
        logger.exception("Failed to parse webhook body as JSON")
        return Response(content="Bad Request", status_code=400)

    # --- Dispatch to business logic ---
    from handler import process_update  # local import keeps startup fast
    try:
        process_update(body)
    except Exception:
        logger.exception("Unhandled error in process_update")

    return Response(content="ok", status_code=200)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
