import os
from pathlib import Path
from dotenv import load_dotenv


def load_settings():
    """Load settings from .env and return as dict."""
    load_dotenv()

    # Определяем базовую директорию проекта
    project_root = Path(__file__).parent.parent.resolve()

    bot_token = (os.getenv("BOT_TOKEN") or "").strip()
    auth_key = (os.getenv("GIGACHAT_AUTH_KEY") or "").strip()
    scope = (os.getenv("GIGACHAT_SCOPE") or "GIGACHAT_API_PERS").strip()
    model = (os.getenv("GIGACHAT_MODEL") or "GigaChat-2-Pro").strip()
    db_path = (os.getenv("DB_PATH") or str(project_root / "bankrot.db")).strip()

    raw_allowed = (os.getenv("ALLOWED_USERS") or "").strip()
    raw_admins = (os.getenv("ADMIN_USERS") or "").strip()

    generated_dir = Path(os.getenv("GENERATED_DIR") or str(project_root / "generated"))
    generated_dir.mkdir(parents=True, exist_ok=True)

    if not bot_token or not auth_key:
        raise SystemExit("Ошибка: не заполнен .env (BOT_TOKEN / GIGACHAT_AUTH_KEY)")

    return {
        "BOT_TOKEN": bot_token,
        "GIGACHAT_AUTH_KEY": auth_key,
        "GIGACHAT_SCOPE": scope,
        "GIGACHAT_MODEL": model,
        "DB_PATH": db_path,
        "RAW_ALLOWED": raw_allowed,
        "RAW_ADMINS": raw_admins,
        "GENERATED_DIR": generated_dir,
    }
