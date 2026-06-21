"""
Shared logging configuration.

Call ``configure_logging()`` once at module startup in each entry-point
(main.py for the FastAPI server, handler.py for the Lambda entry-point).
Subsequent calls are no-ops because basicConfig skips reconfiguration when
handlers are already attached.

Environment variables
---------------------
LOG_LEVEL   Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Defaults to INFO.
LOG_DIR     Directory for the rotating file handler.
            Defaults to /app/logs.
"""

import logging
import os


def configure_logging() -> None:
    """Configure the root logger from environment variables."""
    level = getattr(
        logging,
        os.environ.get("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )

    # Configure root logger (no-op if already configured)
    logging.basicConfig(level=level)

    root = logging.getLogger()

    # Add a file handler only if one isn't already present
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        log_dir = os.environ.get("LOG_DIR", "/app/logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "tg_webhook.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        root.addHandler(file_handler)
