"""
FastAPI webhook server for Telegram bot.

NO IMPORTS FROM bot.py - uses dependency injection to break circular imports.
Dependencies are injected via init_web_app() called during bot startup.
"""
from fastapi import FastAPI, Request, HTTPException, Depends
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from pydantic import ValidationError
import os
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="bankrot_bot web")

# ============================================
# Dependency Injection - set by bot.py at startup
# ============================================
_bot_token: str | None = None
_dispatcher: Dispatcher | None = None
_webhook_bot: Bot | None = None


def init_web_app(bot_token: str, dispatcher: Dispatcher) -> None:
    """
    Initialize web app with bot dependencies.

    Called by bot.py during startup to inject dependencies.
    MUST be called before FastAPI starts serving requests.

    Args:
        bot_token: Telegram bot token
        dispatcher: Configured aiogram Dispatcher with all handlers registered

    Example:
        >>> from web import init_web_app
        >>> init_web_app(BOT_TOKEN, dp)
        >>> # Now FastAPI can handle webhook requests
    """
    global _bot_token, _dispatcher
    _bot_token = bot_token
    _dispatcher = dispatcher
    logger.info("Web app initialized with bot dependencies")


def get_bot_token() -> str:
    """
    Dependency: Get bot token.

    Raises:
        RuntimeError: If bot token not initialized (init_web_app() not called)
    """
    if _bot_token is None:
        raise RuntimeError(
            "Bot token not initialized. Call init_web_app() before starting web server."
        )
    return _bot_token


def get_dispatcher() -> Dispatcher:
    """
    Dependency: Get dispatcher.

    Raises:
        RuntimeError: If dispatcher not initialized (init_web_app() not called)
    """
    if _dispatcher is None:
        raise RuntimeError(
            "Dispatcher not initialized. Call init_web_app() before starting web server."
        )
    return _dispatcher


def _get_webhook_bot(token: str = Depends(get_bot_token)) -> Bot:
    """
    Get or create webhook bot instance (singleton).

    Args:
        token: Bot token from dependency

    Returns:
        Cached Bot instance
    """
    global _webhook_bot
    if _webhook_bot is None:
        _webhook_bot = Bot(token=token)
        logger.info("Created webhook bot instance")
    return _webhook_bot


# ============================================
# Endpoints
# ============================================
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    dp: Dispatcher = Depends(get_dispatcher),
    bot: Bot = Depends(_get_webhook_bot),
) -> dict:
    """
    Telegram webhook endpoint.

    Receives updates from Telegram API and feeds them to dispatcher.

    Args:
        secret: URL path secret (must match TELEGRAM_WEBHOOK_SECRET env var)
        request: FastAPI request with JSON payload
        dp: Injected dispatcher
        bot: Injected bot instance

    Returns:
        {"ok": True} on success

    Raises:
        HTTPException: On authentication failure or validation error
    """
    if not TELEGRAM_WEBHOOK_SECRET:
        logger.error("TELEGRAM_WEBHOOK_SECRET environment variable not set")
        raise HTTPException(
            status_code=500, detail="TELEGRAM_WEBHOOK_SECRET is not set"
        )

    if secret != TELEGRAM_WEBHOOK_SECRET:
        logger.warning(f"Webhook authentication failed: invalid secret")
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        payload = await request.json()
        update = Update.model_validate(payload)
        logger.debug(f"Received webhook update: {update.update_id}")
    except ValidationError as e:
        logger.error(f"Webhook validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/healthz")
def healthz() -> dict:
    """
    Health check endpoint.

    Returns:
        Status information with timestamp
    """
    return {
        "status": "ok",
        "service": "bankrot_bot",
        "ts": datetime.utcnow().isoformat(),
    }


@app.get("/")
def root() -> dict:
    """
    Root endpoint.

    Returns:
        Service identification
    """
    return {"service": "bankrot_bot", "status": "running"}
