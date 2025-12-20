import asyncio
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from docx import Document
from dotenv import load_dotenv
from keyboards import cases_menu_ikb, docs_menu_ikb, main_menu_kb
class CaseCreate(StatesGroup):
    code_name = State()
    case_number = State()
    court = State()
    judge = State()
    fin_manager = State()
class ProfileFill(StatesGroup):
    full_name = State()
    role = State()
    address = State()
    phone = State()
    email = State()
class CaseEdit(StatesGroup):
    value = State()

# =========================
# env
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Pro")

RAW_ALLOWED = (os.getenv("ALLOWED_USERS") or "").strip()
RAW_ADMINS = (os.getenv("ADMIN_USERS") or "").strip()
GENERATED_DIR = Path("generated")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

DOCUMENTS = {
    "online_hearing": {
        "title": "Ходатайство о ВКС",
        "template": "templates/motions/online_hearing.docx",
        "output_prefix": "online_hearing",
    },
    "bankruptcy_petition": {
        "title": "Заявление о банкротстве",
        "template": "templates/petitions/bankruptcy_petition.docx",
        "output_prefix": "bankruptcy_petition",
    },
}


def build_docx_from_template(template_path: str, owner_user_id: int, case_row) -> Path:
    """
    Подготовка DOCX через шаблон
    """
    cid, row_owner_id, code_name, case_number, court, judge, fin_manager, stage, notes, created_at, updated_at = case_row

    template_file = Path(template_path)
    doc = Document(template_file)

    doc.add_paragraph(f"Дело: {case_number or '-'}")
    doc.add_paragraph(f"Кодовое имя: {code_name}")
    doc.add_paragraph(f"Суд: {court or '-'}")
    doc.add_paragraph(f"Судья: {judge or '-'}")

    fname = f"document_case_{cid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    out_path = GENERATED_DIR / fname
    doc.save(out_path)

    return out_path


def _doc_has_placeholders(doc: Document) -> bool:
    for paragraph in doc.paragraphs:
        if "{{" in paragraph.text and "}}" in paragraph.text:
            return True

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if "{{" in paragraph.text and "}}" in paragraph.text:
                        return True
    return False


def _replace_placeholders(doc: Document, mapping: Dict[str, Any]) -> None:
    def replace_in_paragraph(paragraph):
        for run in paragraph.runs:
            for key, value in mapping.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in run.text:
                    run.text = run.text.replace(placeholder, str(value) if value is not None else "-")

    def replace_in_table(table):
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_in_paragraph(paragraph)
                for nested_table in cell.tables:
                    replace_in_table(nested_table)

    for paragraph in doc.paragraphs:
        replace_in_paragraph(paragraph)

    for table in doc.tables:
        replace_in_table(table)


def build_bankruptcy_petition_doc(case_row: tuple) -> Path:
    (
        cid,
        owner_user_id,
        code_name,
        case_number,
        court,
        judge,
        fin_manager,
        stage,
        notes,
        created_at,
        updated_at,
    ) = case_row

    template_path = Path("templates/bankruptcy_petition_template.docx")
    doc = Document(template_path) if template_path.exists() else Document()

    mapping: Dict[str, Any] = {
        "id": cid,
        "owner_user_id": owner_user_id,
        "code_name": code_name,
        "case_number": case_number or "-",
        "court": court or "-",
        "judge": judge or "-",
        "fin_manager": fin_manager or "-",
        "stage": stage or "-",
        "notes": notes or "-",
        "created_at": created_at,
        "updated_at": updated_at,
    }

    if _doc_has_placeholders(doc):
        _replace_placeholders(doc, mapping)
    else:
        doc.add_paragraph("")
        p = doc.add_paragraph("Данные дела")
        try:
            p.style = "Heading 2"
        except KeyError:
            try:
                p.style = "Заголовок 2"
            except KeyError:
                pass

        doc.add_paragraph(f"ID дела: {cid}")
        doc.add_paragraph(f"Кодовое имя: {code_name}")
        doc.add_paragraph(f"Номер дела: {case_number or '-'}")
        doc.add_paragraph(f"Суд: {court or '-'}")
        doc.add_paragraph(f"Судья: {judge or '-'}")
        doc.add_paragraph(f"Финансовый управляющий: {fin_manager or '-'}")
        doc.add_paragraph(f"Стадия: {stage or '-'}")
        doc.add_paragraph(f"Примечания: {notes or '-'}")

        out_name = f"petition_case_{cid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        out_path = GENERATED_DIR / out_name
        doc.save(out_path)
        return out_path


async def _selected_case_id(state: FSMContext) -> int | None:
    data = await state.get_data()
    try:
        return int(data.get("docs_case_id"))
    except (TypeError, ValueError):
        return None

DB_PATH = os.getenv("DB_PATH", "/root/bankrot_bot/bankrot.db")

if not BOT_TOKEN or not AUTH_KEY:
    raise SystemExit("Ошибка: не заполнен .env (BOT_TOKEN / GIGACHAT_AUTH_KEY)")


def _parse_ids(s: str) -> set[int]:
    out = set()
    for x in (s.split(",") if s else []):
        x = x.strip()
        if x.isdigit():
            out.add(int(x))
    return out


ALLOWED_USERS = _parse_ids(RAW_ALLOWED)
ADMIN_USERS = _parse_ids(RAW_ADMINS)


def is_allowed(uid: int) -> bool:
    return (not ALLOWED_USERS) or (uid in ALLOWED_USERS) or (uid in ADMIN_USERS)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_USERS


# =========================
# sqlite (cases)
# =========================
def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL;")

        # ===== cases =====
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
        );
        """)

        # ===== profiles (для документов) =====
        con.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            owner_user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            role TEXT,
            address TEXT,
            phone TEXT,
            email TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        con.commit()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def create_case(owner_user_id: int, code_name: str) -> int:
    now = _now()
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO cases (owner_user_id, code_name, created_at, updated_at) VALUES (?,?,?,?)",
            (owner_user_id, code_name.strip(), now, now),
        )
        con.commit()
        return int(cur.lastrowid)


def list_cases(owner_user_id: int, limit: int = 20) -> List[Tuple]:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id, code_name, case_number, stage, updated_at "
            "FROM cases WHERE owner_user_id=? ORDER BY id DESC LIMIT ?",
            (owner_user_id, limit),
        )
        return cur.fetchall()


def get_case(owner_user_id: int, cid: int) -> Tuple | None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, owner_user_id, code_name, case_number, court, judge, fin_manager,
                   stage, notes, created_at, updated_at
              FROM cases
             WHERE owner_user_id = ?
               AND id = ?
             """,
             (owner_user_id, cid),
        )
        return cur.fetchone()

def get_profile(owner_user_id: int) -> tuple | None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT owner_user_id, full_name, role, address, phone, email, created_at, updated_at "
            "FROM profiles WHERE owner_user_id=?",
            (owner_user_id,),
        )
        return cur.fetchone()


def upsert_profile(
    owner_user_id: int,
    *,
    full_name: str | None = None,
    role: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO profiles (owner_user_id, full_name, role, address, phone, email, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(owner_user_id) DO UPDATE SET
                full_name = COALESCE(excluded.full_name, profiles.full_name),
                role      = COALESCE(excluded.role, profiles.role),
                address   = COALESCE(excluded.address, profiles.address),
                phone     = COALESCE(excluded.phone, profiles.phone),
                email     = COALESCE(excluded.email, profiles.email),
                updated_at = CURRENT_TIMESTAMP
            """,
            (owner_user_id, full_name, role, address, phone, email),
        )
        con.commit()

def update_case_fields(
    owner_user_id: int,
    cid: int,
    *,
    case_number: str | None = None,
    court: str | None = None,
    judge: str | None = None,
    fin_manager: str | None = None,
) -> None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            """
            UPDATE cases
               SET case_number = COALESCE(?, case_number),
                   court = COALESCE(?, court),
                   judge = COALESCE(?, judge),
                   fin_manager = COALESCE(?, fin_manager),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
               AND owner_user_id = ?
            """,
            (case_number, court, judge, fin_manager, cid, owner_user_id),
        )
        con.commit()

def update_case_meta(
    owner_user_id: int,
    cid: int,
    *,
    stage: str | None = None,
    notes: str | None = None,
) -> None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            """
            UPDATE cases
               SET stage = COALESCE(?, stage),
                   notes = COALESCE(?, notes),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
               AND owner_user_id = ?
            """,
            (stage, notes, cid, owner_user_id),
        )
        con.commit()

# =========================
# GigaChat (token cache + retry)
# =========================
_GC_TOKEN: str | None = None
_GC_TOKEN_EXPIRES_AT: float = 0.0
_GC_TOKEN_LOCK = asyncio.Lock()


async def get_access_token(session: aiohttp.ClientSession, force_refresh: bool = False) -> str:
    global _GC_TOKEN, _GC_TOKEN_EXPIRES_AT
    now = time.time()

    async with _GC_TOKEN_LOCK:
        if (not force_refresh) and _GC_TOKEN and now < _GC_TOKEN_EXPIRES_AT:
            return _GC_TOKEN

        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {AUTH_KEY}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with session.post(url, headers=headers, data={"scope": SCOPE}, ssl=False, timeout=30) as r:
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


async def gigachat_chat(system_prompt: str, user_text: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
    }

    async with aiohttp.ClientSession() as session:
        token = await get_access_token(session)

        async def _call(tkn: str):
            headers = {"Authorization": f"Bearer {tkn}", "Content-Type": "application/json"}
            return await session.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=90,
                ssl=False,
            )

        r = await _call(token)
        if r.status == 401:
            await r.release()
            token = await get_access_token(session, force_refresh=True)
            r = await _call(token)

        if r.status != 200:
            raise RuntimeError(await r.text())

        data = await r.json()
        return data["choices"][0]["message"]["content"].strip()


# =========================
# bot logic
# =========================
from aiogram.fsm.storage.memory import MemoryStorage

dp = Dispatcher(storage=MemoryStorage())

USER_FLOW: Dict[int, Dict[str, Any]] = {}
LAST_RESULT: Dict[int, str] = {}


def cancel_flow(uid: int) -> None:
    USER_FLOW.pop(uid, None)


def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Ходатайство", callback_data="flow:motion")
    kb.button(text="🤝 Мировое соглашение", callback_data="flow:settlement")
    kb.adjust(1)
    return kb.as_markup()


def export_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Экспорт (показать текст)", callback_data="export:word")
    kb.adjust(1)
    return kb.as_markup()


def court_type_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Арбитражный суд", callback_data="motion:court:arbitr")
    kb.button(text="Суд общей юрисдикции", callback_data="motion:court:general")
    kb.adjust(1)
    return kb.as_markup()


def motion_actions_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="flow:cancel")
    kb.adjust(1)
    return kb.as_markup()


def settlement_actions_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="flow:cancel")
    kb.adjust(1)
    return kb.as_markup()


MOTION_STEPS = [
    ("fio", "ФИО заявителя (должника):"),
    ("case_number", "Номер дела (если есть) или напиши «нет»:"),
    ("court", "Суд (полное наименование):"),
    ("judge", "Судья (если известно) или «нет»:"),
    ("reason", "Причина ходатайства (кратко):"),
]

SETTLEMENT_STEPS = [
    ("parties", "Стороны (кто с кем заключает мировое):"),
    ("dispute", "Суть спора / что урегулируем:"),
    ("terms", "Условия (что и в какие сроки):"),
    ("expenses", "Расходы/госпошлина (если есть) или «нет»:"),
    ("execution", "Исполнение/ответственность за нарушение:"),
    ("other", "Особые условия (если есть) или «нет»:"),
]


def system_prompt_for_motion(court_type: str) -> str:
    return (
        "Ты — юрист по банкротству в России. Составь проект ходатайства об участии в заседании онлайн "
        "или посредством ВКС. Стиль официальный, корректный, без выдумывания фактов."
        f" Тип суда: {court_type}."
    )


def system_prompt_for_settlement() -> str:
    return (
        "Ты — юрист по банкротству в России. Составь проект мирового соглашения. "
        "Стиль официальный, без выдумывания фактов; если данных не хватает — оставь места для заполнения."
    )


def _val(ans: Dict[str, str], key: str) -> str:
    v = (ans.get(key) or "").strip()
    return v if v else "не указано"


def build_motion_user_text(ans: Dict[str, str], court_type: str) -> str:
    return (
        f"ФИО: {_val(ans,'fio')}\n"
        f"Номер дела: {_val(ans,'case_number')}\n"
        f"Суд: {_val(ans,'court')}\n"
        f"Судья: {_val(ans,'judge')}\n"
        f"Причина: {_val(ans,'reason')}\n"
        f"Тип суда: {court_type}\n"
        "Сформируй текст ходатайства."
    )


def build_settlement_user_text(ans: Dict[str, str]) -> str:
    return (
        f"Стороны: {_val(ans,'parties')}\n"
        f"Суть урегулирования: {_val(ans,'dispute')}\n"
        f"Условия: {_val(ans,'terms')}\n"
        f"Расходы: {_val(ans,'expenses')}\n"
        f"Исполнение/ответственность: {_val(ans,'execution')}\n"
        f"Особые условия: {_val(ans,'other')}\n"
        "Сформируй проект мирового соглашения."
    )


# =========================
# commands
# =========================
@dp.message(CommandStart())
async def start_cmd(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    cancel_flow(uid)
    await message.answer("Выбери задачу 👇", reply_markup=main_menu_kb())
@dp.message(lambda m: m.text == "📂 Дела")
async def cases_entry(message: Message):
    await message.answer("Раздел «Дела». Выбери действие:", reply_markup=cases_menu_ikb())


@dp.message(lambda m: m.text == "🧑‍⚖️ Клиенты")
async def clients_entry(message: Message):
    await message.answer("Раздел «Клиенты». (Сделаем дальше)")

@dp.message(lambda m: m.text == "📝 Документы")
async def docs_entry(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    cid = await _selected_case_id(state)
    await message.answer("Документы: выбери действие 👇", reply_markup=docs_menu_ikb(cid))

@dp.callback_query(lambda c: c.data == "docs:choose_case")
async def docs_choose_case(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    rows = list_cases(uid)
    if not rows:
        await call.message.answer("Нет дел. Сначала создай дело в «📂 Дела».")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    for (cid, code_name, case_number, stage, updated_at) in rows:
        num = case_number or "-"
        kb.button(text=f"📄 {code_name} (№ {num})", callback_data=f"docs:case:{cid}")
    kb.button(text="🔙 Назад", callback_data="docs:back_menu")
    kb.adjust(1)

    await call.message.answer("Выбери дело для документа:", reply_markup=kb.as_markup())
    await call.answer()
@dp.callback_query(lambda c: c.data == "profile:menu")
async def profile_menu(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    row = get_profile(uid)

    if not row:
        text = "Профиль пока не заполнен.\n\nНажми «✏️ Заполнить профиль»."
    else:
        _, full_name, role, address, phone, email, *_ = row
        text = (
            "👤 Мой профиль:\n"
            f"ФИО/Орг: {full_name or '-'}\n"
            f"Статус: {role or '-'}\n"
            f"Адрес: {address or '-'}\n"
            f"Телефон: {phone or '-'}\n"
            f"Email: {email or '-'}\n\n"
            "Нажми «✏️ Заполнить профиль», чтобы изменить."
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Заполнить профиль", callback_data="profile:edit")
    kb.button(text="🔙 Назад", callback_data="docs:back_menu")
    kb.adjust(1)

    await call.message.answer(text, reply_markup=kb.as_markup())
    await call.answer()
@dp.callback_query(lambda c: c.data == "profile:edit")
async def profile_edit_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await state.clear()
    await state.set_state(ProfileFill.full_name)
    await call.message.answer("Введи ФИО или название организации (как будет в документах).")
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("docs:case:"))
async def docs_case_selected(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    row = get_case(uid, cid)
    if not row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    await state.update_data(docs_case_id=cid)
    await call.message.answer(
        f"✅ Выбрано дело #{cid}. Теперь выбери документ 👇", reply_markup=docs_menu_ikb(cid)
    )
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("docs:gen:"))
async def docs_generate(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":", 2)
    doc_key = parts[2] if len(parts) == 3 else ""
    if doc_key != "online_hearing":
        await call.message.answer("Документ не найден")
        await call.answer()
        return

    cid = await _selected_case_id(state)
    if cid is None:
        await call.message.answer("Сначала выбери дело…")
        await docs_choose_case(call)
        await call.answer()
        return

    case_row = get_case(uid, cid)
    if not case_row:
        await state.update_data(docs_case_id=None)
        await call.message.answer("Дело не найдено. Выбери его заново.")
        await docs_choose_case(call)
        await call.answer()
        return

    path = build_online_hearing_docx(case_row)
    await call.message.answer_document(
        FSInputFile(path),
        caption=f"Готово ✅ Ходатайство о ВКС (дело #{cid})",
    )
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("docs:petition:"))
async def docs_petition(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":", 2)
    cid_raw = parts[2] if len(parts) == 3 else ""
    if not cid_raw or cid_raw == "select":
        await call.message.answer("Сначала выбери дело…")
        await docs_choose_case(call)
        await call.answer()
        return

    try:
        cid = int(cid_raw)
    except (TypeError, ValueError):
        await call.message.answer("Дело не найдено. Выбери его заново.")
        await docs_choose_case(call)
        await call.answer()
        return

    case_row = get_case(uid, cid)
    if not case_row:
        await state.update_data(docs_case_id=None)
        await call.message.answer("Дело не найдено. Выбери его заново.")
        await docs_choose_case(call)
        await call.answer()
        return

    await state.update_data(docs_case_id=cid)
    path = build_bankruptcy_petition_doc(case_row)
    await call.message.answer_document(
        FSInputFile(path),
        caption=f"Готово ✅ Заявление о банкротстве для дела #{cid}",
    )
    await call.answer()


@dp.callback_query(lambda c: c.data == "docs:back_menu")
async def docs_back_menu(call: CallbackQuery, state: FSMContext):
    cid = await _selected_case_id(state)
    await call.message.answer("Документы: выбери действие 👇", reply_markup=docs_menu_ikb(cid))
    await call.answer()

@dp.message(lambda m: m.text == "ℹ️ Помощь")
async def help_entry(message: Message):
    await message.answer("Помощь: выбери раздел кнопками. Если что-то сломалось — напиши /start")
@dp.callback_query(lambda c: c.data == "back:main")
async def back_to_main(call: CallbackQuery):
    await call.message.answer("Главное меню 👇", reply_markup=main_menu_kb())
    await call.answer()
@dp.message(Command("doc_test"))
async def doc_test(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    rows = list_cases(uid)
    if not rows:
        await message.answer("Нет дел. Сначала создай дело в «📂 Дела».")
        return

    # возьмём самое свежее дело
    cid = rows[0][0]
    case_row = get_case(uid, cid)
    if not case_row:
        await message.answer("Не нашёл дело для теста.")
        return

    meta = DOCUMENTS["online_hearing"]
    path = build_docx_from_template(
        meta["template"], uid, case_row, meta["output_prefix"]
    )
    await message.answer_document(
        FSInputFile(path), caption=f"Тестовый документ {meta['title']} для дела #{cid}"
    )


@dp.callback_query(lambda c: c.data == "case:new")
async def case_new(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await state.clear()
    await state.set_state(CaseCreate.code_name)
    await call.message.answer("Введи кодовое название дела (например: ИВАНОВ_2025).")
    await call.answer()

@dp.message(CaseCreate.code_name)
async def case_step_code_name(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи кодовое название дела.")
        return

    await state.update_data(code_name=text)
    await state.set_state(CaseCreate.case_number)
    await message.answer("Теперь введи номер дела (можно '-' если пока нет).")

@dp.message(CaseCreate.case_number)
async def case_step_case_number(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи номер дела или '-'.")
        return

    await state.update_data(case_number=None if text == "-" else text)
    await state.set_state(CaseCreate.court)
    await message.answer("Укажи суд (например: АС г. Москвы) или '-'.")

@dp.message(ProfileFill.full_name)
async def profile_step_full_name(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи ФИО/организацию.")
        return

    await state.update_data(full_name=text)
    await state.set_state(ProfileFill.role)
    await message.answer("Статус в деле (например: должник / представитель / кредитор).")

@dp.message(ProfileFill.role)
async def profile_step_role(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи статус (должник/представитель/кредитор).")
        return

    await state.update_data(role=text)
    await state.set_state(ProfileFill.address)
    await message.answer("Адрес (для шапки документа). Можно '-' если не нужно.")

@dp.message(ProfileFill.address)
async def profile_step_address(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи адрес или '-'.")
        return

    await state.update_data(address=None if text == "-" else text)
    await state.set_state(ProfileFill.phone)
    await message.answer("Телефон. Можно '-' если не нужно.")

@dp.message(ProfileFill.phone)
async def profile_step_phone(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи телефон или '-'.")
        return

    await state.update_data(phone=None if text == "-" else text)
    await state.set_state(ProfileFill.email)
    await message.answer("Email. Можно '-' если не нужно.")
@dp.message(ProfileFill.email)
async def profile_step_email(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи email или '-'.")
        return

    data = await state.get_data()

    upsert_profile(
        uid,
        full_name=data.get("full_name"),
        role=data.get("role"),
        address=data.get("address"),
        phone=data.get("phone"),
        email=None if text == "-" else text,
    )

    await state.clear()

    await message.answer(
        "✅ Профиль сохранён.\n\n"
        "Теперь эти данные будут автоматически подставляться в документы.\n"
        "Можешь открыть «👤 Мой профиль», чтобы проверить."
    )

@dp.message(CaseCreate.court)
async def case_step_court(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Укажи суд или '-'.")
        return

    await state.update_data(court=None if text == "-" else text)
    await state.set_state(CaseCreate.judge)
    await message.answer("Укажи судью (ФИО) или '-'.")


@dp.message(CaseCreate.judge)
async def case_step_judge(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Укажи судью или '-'.")
        return

    await state.update_data(judge=None if text == "-" else text)
    await state.set_state(CaseCreate.fin_manager)
    await message.answer("Укажи финансового управляющего или '-'.")


@dp.message(CaseCreate.fin_manager)
async def case_step_fin_manager(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Укажи ФУ или '-'.")
        return

    await state.update_data(fin_manager=None if text == "-" else text)
    data = await state.get_data()

    code_name = data.get("code_name")
    case_number = data.get("case_number")
    court = data.get("court")
    judge = data.get("judge")
    fin_manager = data.get("fin_manager")

    # создаём дело и заполняем поля
    cid = create_case(uid, code_name)
    update_case_fields(uid, cid, case_number=case_number, court=court, judge=judge, fin_manager=fin_manager)

    await state.clear()

    await message.answer(
        "✅ Дело создано.\n"
        f"ID: {cid}\n"
        f"Код: {code_name}\n"
        f"Номер: {case_number or '-'}\n"
        f"Суд: {court or '-'}\n"
        f"Судья: {judge or '-'}\n"
        f"ФУ: {fin_manager or '-'}"
    )

from aiogram.utils.keyboard import InlineKeyboardBuilder

@dp.callback_query(lambda c: c.data == "case:list")
async def case_list(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    rows = list_cases(uid)  # берём последние 20 дел
    if not rows:
        await call.message.answer("Пока нет дел. Нажми «➕ Создать дело».")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    lines = ["📄 Ваши дела (последние 20):"]

    for (cid, code_name, case_number, stage, updated_at) in rows:
        num = case_number or "-"
        st = stage or "-"
        lines.append(f"#{cid} | {code_name} | № {num} | стадия: {st}")
        kb.button(text=f"Открыть #{cid}", callback_data=f"case:open:{cid}")

    kb.button(text="🔙 Назад", callback_data="back:cases")
    kb.adjust(1)

    await call.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(lambda c: c.data == "back:cases")
async def back_to_cases(call: CallbackQuery):
    await call.message.answer(
        "Раздел «Дела». Выбери действие:",
        reply_markup=cases_menu_ikb()
    )
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("case:open:"))
async def case_open(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    row = get_case(uid, cid)
    if not row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    (cid, _owner_user_id, code_name, case_number, court, judge, fin_manager, stage, notes, created_at, updated_at) = row

    text = (
        f"📌 Дело #{cid}\n"
        f"Код: {code_name}\n"
        f"Номер: {case_number or '-'}\n"
        f"Суд: {court or '-'}\n"
        f"Судья: {judge or '-'}\n"
        f"ФУ: {fin_manager or '-'}\n"
        f"Стадия: {stage or '-'}\n"
        f"Заметки: {notes or '-'}\n"
        f"Создано: {created_at}\n"
        f"Обновлено: {updated_at}"
    )

    kb = InlineKeyboardBuilder()
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Номер дела", callback_data=f"case:edit:{cid}:case_number")
    kb.button(text="✏️ Суд", callback_data=f"case:edit:{cid}:court")
    kb.button(text="✏️ Судья", callback_data=f"case:edit:{cid}:judge")
    kb.button(text="✏️ ФУ", callback_data=f"case:edit:{cid}:fin_manager")
    kb.button(text="✏️ Стадия", callback_data=f"case:edit:{cid}:stage")
    kb.button(text="🗒 Заметки", callback_data=f"case:edit:{cid}:notes")
    kb.button(text="🔙 К списку дел", callback_data="case:list")
    kb.adjust(2, 2, 2, 1)

    await call.message.answer(text, reply_markup=kb.as_markup())
    await call.answer()
@dp.callback_query(lambda c: c.data.startswith("case:edit:"))
async def case_edit_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":")
    cid = int(cid_str)

    # проверим, что дело существует и твоё
    row = get_case(uid, cid)
    if not row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    await state.clear()
    await state.update_data(edit_cid=cid, edit_field=field)
    await state.set_state(CaseEdit.value)

    field_titles = {
        "case_number": "номер дела",
        "court": "суд",
        "judge": "судью",
        "fin_manager": "финансового управляющего",
        "stage": "стадию",
        "notes": "заметки",
    }
    title = field_titles.get(field, field)

    await call.message.answer(f"Введи новое значение для «{title}».\nЕсли нужно очистить поле — отправь `-`.")
    await call.answer()
@dp.message(CaseEdit.value)
async def case_edit_apply(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    data = await state.get_data()
    cid = data.get("edit_cid")
    field = data.get("edit_field")

    if not cid or not field:
        await state.clear()
        await message.answer("Что-то пошло не так. Начни заново через карточку дела.")
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи значение или '-' чтобы очистить.")
        return

    value = None if text == "-" else text

    if field in ("case_number", "court", "judge", "fin_manager"):
        update_case_fields(
            uid,
            cid,
            case_number=value if field == "case_number" else None,
            court=value if field == "court" else None,
            judge=value if field == "judge" else None,
            fin_manager=value if field == "fin_manager" else None,
        )
    elif field in ("stage", "notes"):
        update_case_meta(
            uid,
            cid,
            stage=value if field == "stage" else None,
            notes=value if field == "notes" else None,
        )
    else:
        await message.answer("Неизвестное поле для редактирования.")
        await state.clear()
        return

    await state.clear()
    await message.answer("✅ Обновлено. Нажми «🔙 К списку дел» или открой дело снова из списка.")

@dp.message(Command("case_new"))
async def case_new_cmd(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Формат: /case_new КОДОВОЕ_НАЗВАНИЕ\nПример: /case_new Дело_Иванов_01")
        return
    cid = create_case(uid, parts[1])
    await message.answer(f"✅ Дело создано. ID: {cid}")

@dp.message(Command("cases"))
async def cases_cmd(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    rows = list_cases(uid)
    if not rows:
        await message.answer("Пока нет дел. Создай: /case_new КОДОВОЕ_НАЗВАНИЕ")
        return
    lines = ["📋 Ваши дела (последние 20):"]
    for (cid, code_name, case_number, stage, updated_at) in rows:
        lines.append(f"#{cid} | {code_name} | № {case_number or '—'} | стадия: {stage or '—'} | upd: {updated_at}")
    await message.answer("\n".join(lines))


@dp.message(Command("case"))
async def case_cmd(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: /case ID\nПример: /case 3")
        return
    cid = int(parts[1])
    row = get_case(uid, cid)
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


# =========================
# callbacks
# =========================
@dp.callback_query()
async def on_callback(call: CallbackQuery):
    uid = call.from_user.id
    data = call.data or ""
    flow = USER_FLOW.get(uid) or {}

    if data.startswith(("docs:", "case:", "profile:", "back:")):
        await call.answer()
        return

    if not is_allowed(uid):
        await call.answer("Нет доступа", show_alert=True)
        return

    is_flow_callback = (
        data == "export:word"
        or data == "flow:cancel"
        or data == "flow:motion"
        or data == "flow:settlement"
        or data.startswith("motion:court:")
    )

    if not is_flow_callback:
        await call.answer()
        return

    if data == "export:word":
        await call.answer()
        text = LAST_RESULT.get(uid)
        if text:
            await call.message.answer(text)
        else:
            await call.message.answer("Пока нечего экспортировать.")
        return

    if data == "flow:cancel":
        await call.answer()
        cancel_flow(uid)
        await call.message.answer("Ок, отменил. Меню 👇", reply_markup=main_keyboard())
        return

    if data == "flow:motion":
        await call.answer()
        USER_FLOW[uid] = {"flow": "motion", "stage": "choose_court", "court_type": None, "step": 0, "answers": {}}
        await call.message.answer("Выбери тип суда:", reply_markup=court_type_keyboard())
        return

    if data.startswith("motion:court:"):
        await call.answer()
        ct = data.split(":")[-1]
        if uid not in USER_FLOW or USER_FLOW[uid].get("flow") != "motion":
            USER_FLOW[uid] = {"flow": "motion", "stage": "fill", "court_type": ct, "step": 0, "answers": {}}
        else:
            USER_FLOW[uid]["stage"] = "fill"
            USER_FLOW[uid]["court_type"] = ct
            USER_FLOW[uid]["step"] = 0
            USER_FLOW[uid]["answers"] = {}
        await call.message.answer(MOTION_STEPS[0][1], reply_markup=motion_actions_keyboard())
        return

    if data == "flow:settlement":
        await call.answer()
        USER_FLOW[uid] = {"flow": "settlement", "step": 0, "answers": {}}
        await call.message.answer(SETTLEMENT_STEPS[0][1], reply_markup=settlement_actions_keyboard())
        return

    await call.answer()
    return


@dp.message()
async def main_text_router(message: Message, state: FSMContext):
    # Если идёт FSM (создание дела и т.п.) — не мешаем
    if await state.get_state() is not None:
        return

    uid = message.from_user.id
    if not is_allowed(uid):
        return

    if uid not in USER_FLOW:
        await message.answer("Сначала выбери задачу через /start.")
        return

    # дальше — твоя старая логика USER_FLOW (motion / settlement)
    flow = USER_FLOW[uid]
    text = (message.text or "").strip()

    if flow.get("flow") == "settlement":
        step = int(flow.get("step", 0))
        if step >= len(SETTLEMENT_STEPS):
            cancel_flow(uid)
            await message.answer("Анкета завершена. Меню 👇", reply_markup=main_keyboard())
            return

        key = SETTLEMENT_STEPS[step][0]
        flow["answers"][key] = text
        step += 1
        flow["step"] = step

        if step < len(SETTLEMENT_STEPS):
            await message.answer(SETTLEMENT_STEPS[step][1], reply_markup=settlement_actions_keyboard())
            return

        await message.answer("Принял данные. Готовлю проект мирового…")
        try:
            user_text = build_settlement_user_text(flow.get("answers", {}))
            result = await gigachat_chat(system_prompt_for_settlement(), user_text)
            LAST_RESULT[uid] = result
            await message.answer(result)
            await message.answer("Экспорт 👇", reply_markup=export_keyboard())
        except Exception as e:
            await message.answer(f"Ошибка GigaChat:\n{e}")

        cancel_flow(uid)
        return


async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
