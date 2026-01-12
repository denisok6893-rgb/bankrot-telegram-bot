import os
import sqlite3
from pathlib import Path
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

# Определяем базовую директорию проекта
project_root = Path(__file__).parent.resolve()
DB_PATH = os.getenv("DB_PATH") or str(project_root / "bankrot.db")

router = Router()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL,
            code_name TEXT NOT NULL,
            case_number TEXT,
            court TEXT,
            judge TEXT,
            fin_manager TEXT,
            stage TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        con.commit()


def create_case(owner_user_id: int, code_name: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        now = _now()
        cur.execute(
            "INSERT INTO cases(owner_user_id, code_name, created_at, updated_at) VALUES(?,?,?,?)",
            (owner_user_id, code_name.strip(), now, now),
        )
        con.commit()
        return int(cur.lastrowid)


def list_cases(owner_user_id: int, limit: int = 20):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id, code_name, case_number, stage, updated_at "
            "FROM cases WHERE owner_user_id=? ORDER BY id DESC LIMIT ?",
            (owner_user_id, limit),
        )
        return cur.fetchall()


def get_case(owner_user_id: int, cid: int):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id, code_name, case_number, court, judge, fin_manager, stage, notes, created_at, updated_at "
            "FROM cases WHERE owner_user_id=? AND id=?",
            (owner_user_id, cid),
        )
        return cur.fetchone()


@router.message(Command("case_new"))
async def case_new_cmd(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Формат: /case_new КОДОВОЕ_НАЗВАНИЕ\nПример: /case_new Test_01")
        return
    case_id = create_case(message.from_user.id, parts[1])
    await message.answer(f"✅ Дело создано. ID: {case_id}")


@router.message(Command("cases"))
async def cases_cmd(message: Message):
    rows = list_cases(message.from_user.id)
    if not rows:
        await message.answer("Пока нет дел. Создай: /case_new КОДОВОЕ_НАЗВАНИЕ")
        return
    lines = ["📋 Ваши дела (последние 20):"]
    for (cid, code_name, case_number, stage, updated_at) in rows:
        lines.append(f"#{cid} | {code_name} | № {case_number or '—'} | стадия: {stage or '—'} | upd: {updated_at}")
    await message.answer("\n".join(lines))


@router.message(Command("case"))
async def case_cmd(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: /case ID\nПример: /case 3")
        return
    cid = int(parts[1])
    row = get_case(message.from_user.id, cid)
    if not row:
        await message.answer("Не найдено (или это не ваше дело).")
        return

    (cid, code_name, case_number, court, judge, fin_manager, stage, notes, created_at, updated_at) = row
    text = (
        f"📌 Дело #{cid}\n"
        f"Код: {code_name}\n"
        f"Номер дела: {case_number or '—'}\n"
        f"Суд: {court or '—'}\n"
        f"Судья: {judge or '—'}\n"
        f"ФУ: {fin_manager or '—'}\n"
        f"Стадия: {stage or '—'}\n"
        f"Заметки: {notes or '—'}\n"
        f"Создано: {created_at}\n"
        f"Обновлено: {updated_at}\n"
    )
    await message.answer(text)
