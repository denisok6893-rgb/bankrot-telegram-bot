from fastapi import FastAPI
from datetime import datetime

app = FastAPI(title="bankrot_bot web")

import os
from fastapi import Request, HTTPException
from aiogram import Bot
from aiogram.types import Update
from pydantic import ValidationError

# IMPORTANT:
# We import dp and BOT_TOKEN from bot.py. bot.py must not start polling on import
# (it doesn't; polling is under __main__).
from bot import dp, BOT_TOKEN

TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
_webhook_bot: Bot | None = None


def _get_webhook_bot() -> Bot:
    global _webhook_bot
    if _webhook_bot is None:
        _webhook_bot = Bot(token=BOT_TOKEN)
    return _webhook_bot


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if not TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="TELEGRAM_WEBHOOK_SECRET is not set")
    if secret != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    payload = await request.json()
    try:
        update = Update.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    bot = _get_webhook_bot()
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": "bankrot_bot",
        "ts": datetime.utcnow().isoformat(),
    }


@app.get("/")
def root():
    return {"service": "bankrot_bot", "status": "running"}
