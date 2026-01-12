import asyncio
import json
import time
import uuid
from typing import Optional

import aiohttp


_GC_TOKEN: Optional[str] = None
_GC_TOKEN_EXPIRES_AT: float = 0.0
_GC_TOKEN_LOCK = asyncio.Lock()


async def get_access_token(
    session: aiohttp.ClientSession,
    *,
    auth_key: str,
    scope: str,
    force_refresh: bool = False,
) -> str:
    global _GC_TOKEN, _GC_TOKEN_EXPIRES_AT
    now = time.time()

    async with _GC_TOKEN_LOCK:
        if (not force_refresh) and _GC_TOKEN and now < _GC_TOKEN_EXPIRES_AT:
            return _GC_TOKEN

        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with session.post(url, headers=headers, data={"scope": scope}, timeout=30) as r:
            text = await r.text()
            if r.status != 200:
                raise RuntimeError(text)

        data = json.loads(text)
        token = data["access_token"]

        if "expires_in" in data:
            exp = time.time() + int(data["expires_in"])
        elif "expires_at" in data:
            raw = int(data["expires_at"])
            exp = (raw / 1000) if raw > 10_000_000_000 else raw
        else:
            exp = time.time() + 1800

        _GC_TOKEN = token
        _GC_TOKEN_EXPIRES_AT = float(exp) - 30
        return _GC_TOKEN


async def gigachat_chat(
    *,
    auth_key: str,
    scope: str,
    model: str,
    system_prompt: str,
    user_text: str,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
    }

    async with aiohttp.ClientSession() as session:
        token = await get_access_token(session, auth_key=auth_key, scope=scope)

        async def _call(tkn: str):
            headers = {"Authorization": f"Bearer {tkn}", "Content-Type": "application/json"}
            return await session.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=90,
            )

        r = await _call(token)
        if r.status == 401:
            await r.release()
            token = await get_access_token(session, auth_key=auth_key, scope=scope, force_refresh=True)
            r = await _call(token)

        if r.status != 200:
            raise RuntimeError(await r.text())

        data = await r.json()
        return data["choices"][0]["message"]["content"].strip()
