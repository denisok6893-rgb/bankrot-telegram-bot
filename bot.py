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
from keyboards import (
    main_menu_kb,
    start_ikb,
    home_ikb,
    profile_ikb,
    cases_list_ikb,
    case_card_ikb,
    docs_home_ikb,
    help_ikb,
    docs_menu_ikb,
    case_files_ikb,
)

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
class CaseCardFill(StatesGroup):
    waiting_value = State()


class CaseCardFill(StatesGroup):
    waiting_value = State()

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
BANKRUPTCY_TEMPLATE_PATH = Path("templates/petitions/bankruptcy_petition.docx")

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


def build_docx_from_template(template_path: str, owner_user_id: int, case_row: tuple) -> Path:
    """
    Подготовка DOCX через шаблон:
    - если в шаблоне есть {{placeholders}} → подставляем данные
    - если нет → аккуратно дописываем базовую информацию
    """
    (
        cid,
        row_owner_id,
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

    template_file = Path(template_path)
    doc = Document(template_file)

    mapping = {
        "case_id": cid,
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

        doc.add_paragraph(f"Дело: {case_number or '-'}")
        doc.add_paragraph(f"Кодовое имя: {code_name}")
        doc.add_paragraph(f"Суд: {court or '-'}")
        doc.add_paragraph(f"Судья: {judge or '-'}")



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

def validate_case_card(card: dict) -> list[str]:
    """
    Проверяет обязательные поля карточки дела
    Возвращает список отсутствующих полей
    """
    required_fields = [
        "court_name",
        "court_address",
        "debtor_full_name",
        "debtor_last_name",
        "debtor_first_name",
        "debtor_gender",
        "debtor_birth_date",
        "debtor_address",
        "passport_series",
        "passport_number",
        "passport_issued_by",
        "passport_date",
        "passport_code",
        "total_debt_rubles",
        "total_debt_kopeks",
    ]

    missing = []

    for field in required_fields:
        value = card.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    if card.get("debtor_gender") not in ("male", "female"):
        if "debtor_gender" not in missing:
            missing.append("debtor_gender")

    return missing
def build_gender_forms(gender: str | None) -> dict:
    """
    Возвращает слова в нужном роде для плейсхолдеров шаблона:
    {{debtor_having_word}}, {{debtor_registered_word}}, {{debtor_living_word}},
    {{debtor_not_registered_word}}, {{debtor_insolvent_word}}
    """
    g = (gender or "").strip().lower()
    if g == "female":
        return {
            "debtor_having_word": "имеющая",
            "debtor_registered_word": "зарегистрированная",
            "debtor_living_word": "проживающая",
            "debtor_not_registered_word": "не зарегистрирована",
            "debtor_insolvent_word": "несостоятельной",
        }
    # по умолчанию male
    return {
        "debtor_having_word": "имеющий",
        "debtor_registered_word": "зарегистрированный",
        "debtor_living_word": "проживающий",
        "debtor_not_registered_word": "не зарегистрирован",
        "debtor_insolvent_word": "несостоятельным",
    }


def build_debtor_last_name_initials(card: dict) -> str:
    """
    Из 'Иванов Иван Иванович' делает 'Иванов И. И.'
    Если ФИО пустое/неполное — возвращает как есть.
    """
    full_name = (card.get("debtor_full_name") or "").strip()
    parts = [p for p in full_name.split() if p]
    if len(parts) >= 2:
        last = parts[0]
        first_i = parts[1][0].upper() + "."
        patro_i = (parts[2][0].upper() + ".") if len(parts) >= 3 and parts[2] else ""
        return (last + " " + first_i + (" " + patro_i if patro_i else "")).strip()
    return full_name


def build_family_status_block(card: dict) -> str:
    """
    Возвращает текстовый блок о семейном положении/детях для {{family_status_block}}.
    Поля ожидаются: marital_status, spouse_full_name, has_minor_children, children_count,
    marriage_certificate_number, marriage_certificate_date
    """
    marital_status = (card.get("marital_status") or "").strip()
    spouse_full_name = (card.get("spouse_full_name") or "").strip()
    has_minor_children = card.get("has_minor_children")
    children_count = card.get("children_count")
    cert_no = (card.get("marriage_certificate_number") or "").strip()
    cert_date = (card.get("marriage_certificate_date") or "").strip()

    lines: list[str] = []

    if marital_status == "married":
        line = "Состоит в браке"
        if spouse_full_name:
            line += f" с {spouse_full_name}"
        line += "."
        lines.append(line)

        if cert_no:
            cert_line = f"Свидетельство о заключении брака № {cert_no}"
            if cert_date:
                cert_line += f" от {cert_date}"
            cert_line += "."
            lines.append(cert_line)

    elif marital_status == "single":
        lines.append("В браке не состоит.")

    if has_minor_children is True:
        cnt = ""
        if children_count not in (None, ""):
            cnt = f" ({children_count} ребёнок(детей))"
        lines.append(f"Имеет несовершеннолетних детей{cnt}.")
    elif has_minor_children is False:
        lines.append("Несовершеннолетних детей нет.")

    return "\n".join(lines)


def build_creditors_header_block(creditors: list[dict] | None) -> str:
    return "Сведения о кредиторах:" if creditors else ""


def build_creditors_block(creditors: list[dict] | None) -> str:
    """
    creditors = [
      {"name": "...", "obligations":[{"amount_rubles":123,"amount_kopeks":45,"source":"ОКБ"}]}
    ]
    """
    if not isinstance(creditors, list) or not creditors:
        return ""

    lines: list[str] = []
    for i, c in enumerate(creditors, start=1):
        name = str((c.get("name") or "Кредитор")).strip()
        obs = c.get("obligations") or []
        if not isinstance(obs, list):
            obs = []

        obs_txt: list[str] = []
        for ob in obs:
            if not isinstance(ob, dict):
                continue
            r = ob.get("amount_rubles")
            k = ob.get("amount_kopeks")
            src = (ob.get("source") or "").strip()

            money_parts: list[str] = []
            if r is not None:
                money_parts.append(f"{int(r)} руб.")
            if k is not None:
                money_parts.append(f"{int(k):02d} коп.")
            money = " ".join(money_parts).strip()

            if money and src:
                obs_txt.append(f"{money} ({src})")
            elif money:
                obs_txt.append(money)
            elif src:
                obs_txt.append(f"({src})")

        if obs_txt:
            lines.append(f"{i}) {name} — " + "; ".join(obs_txt))
        else:
            lines.append(f"{i}) {name}")

    return "\n".join(lines)


def build_vehicle_block(card: dict) -> str:
    """
    Если авто нет — 'Отсутствует'.
    Если есть список vehicles или vehicle — печатаем списком.
    """
    vehicles: list[dict] = []

    vlist = card.get("vehicles")
    if isinstance(vlist, list):
        vehicles.extend([v for v in vlist if isinstance(v, dict)])

    one = card.get("vehicle")
    if isinstance(one, dict):
        vehicles.append(one)

    if not vehicles:
        return "Отсутствует"

    lines: list[str] = []
    for i, v in enumerate(vehicles, start=1):
        brand_model = (v.get("brand_model") or "").strip()
        plate = (v.get("plate_number") or "").strip()
        vin = (v.get("vin") or "").strip()
        year = (v.get("year") or "").strip()
        parts = [p for p in [brand_model, plate, vin, year] if p]
        desc = "; ".join(parts) if parts else "Автомобиль"
        lines.append(f"{i}) {desc}")

    return "\n".join(lines)


def build_attachments_list(card: dict) -> str:
    items: list[str] = []
    if card.get("passport_series") and card.get("passport_number"):
        items.append("Копия паспорта гражданина РФ.")
    if card.get("debtor_inn"):
        items.append("Копия ИНН.")
    if card.get("debtor_snils"):
        items.append("Копия СНИЛС.")
    if card.get("creditors"):
        items.append("Документы, подтверждающие задолженность перед кредиторами.")

    if not items:
        return ""
    return "\n".join(f"{i}) {x}" for i, x in enumerate(items, start=1))


def _doc_has_placeholders(doc: Document, placeholders) -> bool:
    targets = list(placeholders)

    def has_in_paragraphs(paragraphs) -> bool:
        return any(any(t in p.text for t in targets) for p in paragraphs)

    if has_in_paragraphs(doc.paragraphs):
        return True

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if has_in_paragraphs(cell.paragraphs):
                    return True
    return False


def _replace_placeholders(doc: Document, context: dict) -> None:
    def replace_text(text: str) -> str:
        for k, v in context.items():
            if k in text:
                text = text.replace(k, v)
        return text

    def process_paragraphs(paragraphs):
        for p in paragraphs:
            if any(k in p.text for k in context.keys()):
                p.text = replace_text(p.text)

    process_paragraphs(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                process_paragraphs(cell.paragraphs)

def _set_paragraph_text_keep_style(paragraph, new_text: str) -> None:
    """
    Надёжная замена текста в параграфе: плейсхолдеры могут быть разорваны по runs.
    Сохраняем стиль параграфа, но runs пересоздаём.
    """
    if paragraph.runs:
        for r in paragraph.runs:
            r.text = ""
    paragraph.add_run(new_text)


def _replace_placeholders_strong(doc: Document, mapping: Dict[str, Any]) -> None:
    """
    Замена плейсхолдеров формата {{key}} по полному тексту параграфов и ячеек таблиц.
    mapping: ключи БЕЗ фигурных скобок, например: {"court_name": "..." }
    """
    def apply_to_paragraph(p):
        text = p.text
        if not text or "{{" not in text:
            return
        changed = False
        for k, v in mapping.items():
            placeholder = f"{{{{{k}}}}}"
            if placeholder in text:
                text = text.replace(placeholder, "" if v is None else str(v))
                changed = True
        if changed:
            _set_paragraph_text_keep_style(p, text)

    for p in doc.paragraphs:
        apply_to_paragraph(p)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    apply_to_paragraph(p)
                for nested in cell.tables:
                    # рекурсивно для вложенных таблиц
                    for nrow in nested.rows:
                        for ncell in nrow.cells:
                            for np in ncell.paragraphs:
                                apply_to_paragraph(np)


def build_bankruptcy_petition_doc(case_row: Tuple, card: dict) -> Path:
    """
    Генерация заявления о банкротстве по шаблону.
    Надёжная подстановка {{placeholders}} даже если Word разорвал их по runs.
    """
    cid = case_row[0]

    template_path = Path("templates/petitions/bankruptcy_petition.docx")
    doc = Document(template_path)

    gender_forms = build_gender_forms(card.get("debtor_gender"))
    creditors = card.get("creditors") if isinstance(card.get("creditors"), list) else []

    certificate_number = card.get("certificate_number") or card.get("marriage_certificate_number")
    certificate_date = card.get("certificate_date") or card.get("marriage_certificate_date")

    mapping = {
        # Базовые поля дела / суда
        "court_name": case_row[4] or "",
        "financial_manager_info": case_row[6] or "",

        # Адрес суда из карточки
        "court_address": card.get("court_address") or "",

        # Данные должника
        "debtor_full_name": card.get("debtor_full_name") or "",
        "debtor_last_name_initials": build_debtor_last_name_initials(card),
        "debtor_address": card.get("debtor_address") or "",
        "debtor_birth_date": card.get("debtor_birth_date") or "",
        "debtor_inn": card.get("debtor_inn") or "",
        "debtor_snils": card.get("debtor_snils") or "",
        "debtor_phone_or_absent": card.get("debtor_phone") or "отсутствует",
        "debtor_inn_or_absent": card.get("debtor_inn") or "отсутствует",
        "debtor_snils_or_absent": card.get("debtor_snils") or "отсутствует",

        # Паспорт
        "passport_series": card.get("passport_series") or "",
        "passport_number": card.get("passport_number") or "",
        "passport_issued_by": card.get("passport_issued_by") or "",
        "passport_date": card.get("passport_date") or "",
        "passport_code": card.get("passport_code") or "",

        # Семья / дети
        "family_status_block": build_family_status_block(card),

        # Кредиторы
        "creditors_header_block": build_creditors_header_block(creditors),
        "creditors_block": build_creditors_block(creditors),

        # Транспорт
        "vehicle_block": build_vehicle_block(card),

        # Сумма долга
        "total_debt_rubles": str(card.get("total_debt_rubles") or ""),
        "total_debt_kopeks": f"{int(card.get('total_debt_kopeks') or 0):02d}",

        # Депозит/рассрочка
        "deposit_deferral_request": card.get("deposit_deferral_request") or "",

        # Приложения
        "attachments_list": build_attachments_list(card),

        # Свидетельства
        "certificate_number": certificate_number or "",
        "certificate_date": certificate_date or "",

        # Текущая дата
        "date": datetime.now().strftime("%d.%m.%Y"),
    }

    # гендерные формы: debtor_having_word, debtor_asked_word и т.п.
    for k, v in gender_forms.items():
        mapping[k] = v

    _replace_placeholders_strong(doc, mapping)

    fname = f"bankruptcy_petition_case_{cid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    case_dir = GENERATED_DIR / "cases" / str(cid)
    case_dir.mkdir(parents=True, exist_ok=True)
    out_path = case_dir / fname
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


def migrate_case_cards_table(con: sqlite3.Connection | None = None) -> set[str]:
    close_con = con is None
    if con is None:
        con = sqlite3.connect(DB_PATH)

    cur = con.cursor()
    cur.execute("PRAGMA table_info(case_cards)")
    cols = {row[1] for row in cur.fetchall()}

    for col in ("data", "court_address", "judge_name", "debtor_full_name"):
        if col not in cols:
            cur.execute(f"ALTER TABLE case_cards ADD COLUMN {col} TEXT")

    con.commit()

    cur.execute("PRAGMA table_info(case_cards)")
    result = {row[1] for row in cur.fetchall()}

    if close_con:
        con.close()

    return result


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

        # ===== case_cards (карточка дела, JSON) =====
        con.execute("""
        CREATE TABLE IF NOT EXISTS case_cards (
            case_id INTEGER NOT NULL,
            owner_user_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (case_id, owner_user_id)
        );
        """)

        con.commit()

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

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS case_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                data TEXT,
                court_name TEXT,
                court_address TEXT,
                judge_name TEXT,
                debtor_full_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_user_id, case_id)
            );
            """
        )

        migrate_case_cards_table(con)
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

def get_case_card(owner_user_id: int, cid: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT data
              FROM case_cards
             WHERE owner_user_id = ?
               AND case_id = ?
            """,
            (owner_user_id, cid),
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None


def upsert_case_card(owner_user_id: int, cid: int, data: dict) -> None:
    now = _now()
    payload = json.dumps(data, ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO case_cards (case_id, owner_user_id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(case_id, owner_user_id) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (cid, owner_user_id, payload, now, now),
        )
        con.commit()

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


CASE_CARD_REQUIRED_FIELDS = [
    "court_name",
    "court_address",
    "debtor_full_name",
    "debtor_last_name",
    "debtor_first_name",
    "debtor_gender",
    "debtor_birth_date",
    "debtor_address",
    "passport_series",
    "passport_number",
    "passport_issued_by",
    "passport_date",
    "passport_code",
    "total_debt_rubles",
    "total_debt_kopeks",
]


def validate_case_card(card: dict[str, Any]) -> dict[str, list[str]]:
    missing = []
    for field in CASE_CARD_REQUIRED_FIELDS:
        val = card.get(field)
        if val is None or str(val).strip() == "":
            missing.append(field)
    return {"missing": missing}


def _compose_debtor_full_name(data: dict[str, Any]) -> str | None:
    last = (data.get("debtor_last_name") or "").strip()
    first = (data.get("debtor_first_name") or "").strip()
    middle = (data.get("debtor_middle_name") or "").strip()
    parts = [p for p in (last, first, middle) if p]
    return " ".join(parts) if parts else None


def get_case_card(owner_user_id: int, cid: int) -> dict[str, Any]:
    migrate_case_cards_table()
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT data, court_name, court_address, judge_name, debtor_full_name
              FROM case_cards
             WHERE owner_user_id = ?
               AND case_id = ?
            """,
            (owner_user_id, cid),
        )
        row = cur.fetchone()

    base: dict[str, Any] = {}
    if row:
        raw_data, court_name, court_address, judge_name, debtor_full_name = row
        if raw_data:
            try:
                base = json.loads(raw_data)
            except Exception:
                base = {}
        if court_name and not base.get("court_name"):
            base["court_name"] = court_name
        if court_address and not base.get("court_address"):
            base["court_address"] = court_address
        if judge_name and not base.get("judge_name"):
            base["judge_name"] = judge_name
        if debtor_full_name and not base.get("debtor_full_name"):
            base["debtor_full_name"] = debtor_full_name

    for field in CASE_CARD_REQUIRED_FIELDS:
        base.setdefault(field, None)

    if base.get("debtor_full_name") is None:
        base["debtor_full_name"] = _compose_debtor_full_name(base)

    return base


def upsert_case_card(owner_user_id: int, case_id: int, data: dict[str, Any]) -> None:
    migrate_case_cards_table()
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(case_cards)")
        columns = {row[1] for row in cur.fetchall()}
        cur.execute(
            """
            SELECT data FROM case_cards
             WHERE owner_user_id = ?
               AND case_id = ?
            """,
            (owner_user_id, case_id),
        )
        row = cur.fetchone()
        current: dict[str, Any] = {}
        if row and row[0]:
            try:
                current = json.loads(row[0])
            except Exception:
                current = {}

        current.update(data)

        payload = json.dumps(current, ensure_ascii=False)

        insert_columns = ["owner_user_id", "case_id", "data"]
        placeholders = ["?", "?", "?"]
        values: list[Any] = [owner_user_id, case_id, payload]

        if "created_at" in columns:
            insert_columns.append("created_at")
            placeholders.append("CURRENT_TIMESTAMP")

        if "updated_at" in columns:
            insert_columns.append("updated_at")
            placeholders.append("CURRENT_TIMESTAMP")

        update_set_parts = ["data = excluded.data"]
        if "updated_at" in columns:
            update_set_parts.append("updated_at = CURRENT_TIMESTAMP")

        sql = f"""
            INSERT INTO case_cards ({', '.join(insert_columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT(owner_user_id, case_id) DO UPDATE SET
                {', '.join(update_set_parts)}
        """

        cur.execute(sql, values)
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
# menu (new)
# =========================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    cancel_flow(uid)

    await message.answer(
        "Бот запущен. Нажмите «Старт», чтобы открыть меню.",
        reply_markup=main_menu_kb(),
    )
    await message.answer("▶️ Запуск:", reply_markup=start_ikb())


@dp.callback_query(F.data == "menu:home")
async def menu_home(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("Главное меню:", reply_markup=home_ikb())
    await call.answer()


@dp.callback_query(F.data == "menu:profile")
async def menu_profile(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("👤 Мой профиль:", reply_markup=profile_ikb())
    await call.answer()


@dp.callback_query(F.data == "menu:docs")
async def menu_docs(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("📄 Документы (общий раздел):", reply_markup=docs_home_ikb())
    await call.answer()


@dp.callback_query(F.data == "menu:help")
async def menu_help(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer(
        "❓ Помощь:\n"
        "1) Главное меню → «Мой профиль»\n"
        "2) В профиле → «Дела»\n"
        "3) Внутри дела: «Документы по делу» или «Редактирование карточки»",
        reply_markup=help_ikb(),
    )
    await call.answer()


@dp.callback_query(F.data == "profile:cases")
async def profile_cases(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    rows = list_cases(uid)
    if not rows:
        await call.message.answer("Пока нет дел.", reply_markup=profile_ikb())
        await call.answer()
        return

    await call.message.answer("📂 Ваши дела:", reply_markup=cases_list_ikb(rows))
    await call.answer()


@dp.callback_query(F.data.startswith("case:open:"))
async def case_open(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])
    await call.message.answer(
        f"🗂 Карточка дела #{case_id}\nВыберите действие:",
        reply_markup=case_card_ikb(case_id),
    )
    await call.answer()

@dp.callback_query(F.data.startswith("case:docs:"))
async def case_docs(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    # сохраним выбранное дело (на будущее)
    await state.update_data(docs_case_id=case_id)

    # показываем уже созданные файлы по делу (ТОЛЬКО новая структура)
    case_dir = GENERATED_DIR / "cases" / str(case_id)
    files = []
    if case_dir.is_dir():
        files = sorted(
            [p.name for p in case_dir.iterdir() if p.is_file() and p.suffix.lower() == ".docx"],
            reverse=True,
        )

    # клавиатура: сначала генерация, потом архив
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Сформировать заявление о банкротстве (новое)", callback_data=f"case:gen:{case_id}:petition")
    kb.button(text="📹 Сформировать ходатайство о ВКС (новое)", callback_data=f"case:gen:{case_id}:online")
    kb.button(text="🔙 Назад", callback_data=f"case:open:{case_id}")

    if files:
        kb.button(text="—— Архив документов ——", callback_data="noop")
        for fn in files[:20]:
            kb.button(text=f"📎 {fn}", callback_data=f"case:file:{case_id}:{fn}")

    kb.adjust(1)

    if not files:
        await call.message.answer(
            f"📎 Документы по делу #{case_id} пока отсутствуют.\n"
            "Нажми кнопку ниже, чтобы сформировать новый документ (он сохранится в архив).",
            reply_markup=kb.as_markup(),
        )
        await call.answer()
        return

    await call.message.answer(
        f"📎 Документы по делу #{case_id} (последние сверху):",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("case:file:"))
async def case_file_send(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    # формат: case:file:<case_id>:<filename>
    parts = call.data.split(":", 3)
    if len(parts) != 4:
        await call.answer("Некорректная команда")
        return

    case_id = int(parts[2])
    filename = parts[3]

    if ("/" in filename) or ("\\" in filename) or (".." in filename):
        await call.message.answer("Некорректное имя файла.")
        await call.answer()
        return

    case_dir = GENERATED_DIR / "cases" / str(case_id)
    path = case_dir / filename

    path = GENERATED_DIR / filename
    if not path.exists():
        await call.message.answer("Файл не найден (возможно, удалён).")
        await call.answer()
        return

    await call.message.answer_document(
        FSInputFile(path),
        caption=f"📄 Документ по делу #{case_id}",
    )
    await call.answer()

@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data.startswith("case:gen:"))
async def case_generate_from_case_docs(call: CallbackQuery, state: FSMContext):
    """
    Генерация нового документа прямо из "Документы по делу"
    callback_data: case:gen:<case_id>:petition|online
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    if len(parts) != 4:
        await call.message.answer("Некорректная команда.")
        await call.answer()
        return

    case_id = int(parts[2])
    doc_kind = parts[3]

    case_row = get_case(uid, case_id)
    if not case_row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    # сохраняем выбранное дело в state
    await state.update_data(docs_case_id=case_id)

    if doc_kind == "petition":
        card = get_case_card(uid, case_id)
        if not card:
            await call.message.answer("Карточка дела ещё не заполнена. Сначала заполни карточку дела.")
            await call.answer()
            return

        validation = validate_case_card(card)
        missing = validation.get("missing", []) if isinstance(validation, dict) else (validation or [])

        if missing:
            await call.message.answer(
                "Не хватает обязательных данных в карточке дела:\n"
                + "- " + _humanize_missing(missing).replace(", ", "\n- ")
                + "\n\nНажми «Редактирование карточки» и заполни поля по шагам."
            )
            await call.answer()
            return

        path = build_bankruptcy_petition_doc(case_row, card)
        await call.message.answer_document(
            FSInputFile(path),
            caption=f"Готово ✅ Заявление о банкротстве (дело #{case_id})",
        )

    elif doc_kind == "online":
        path = build_online_hearing_docx(case_row)
        await call.message.answer_document(
            FSInputFile(path),
            caption=f"Готово ✅ Ходатайство о ВКС (дело #{case_id})",
        )
    else:
        await call.message.answer("Неизвестный тип документа.")
        await call.answer()
        return

    # после генерации — сразу показать обновлённый архив
    fake = type("X", (), {})()
    fake.from_user = call.from_user
    fake.data = f"case:docs:{case_id}"
    fake.message = call.message

    await case_docs(fake, state)
    await call.answer()

@dp.callback_query(F.data.startswith("case:edit:"))
async def case_edit_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    await state.clear()

    card = get_case_card(uid, case_id) or {}
    next_field = None
    for key, _meta in CASE_CARD_FIELDS:
        val = card.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            next_field = key
            break

    if not next_field:
        await state.update_data(card_case_id=case_id)
        await send_card_fill_menu(call.message, uid, case_id)
        await call.answer()
        return

    await state.update_data(card_case_id=case_id, card_field_key=next_field)
    await state.set_state(CaseCardFill.waiting_value)

    filled, total = _card_completion_status(card)
    prompt = CASE_CARD_FIELD_META[next_field]["prompt"] + "\nОтправь '-' чтобы оставить пустым."
    await call.message.answer(
        f"✍️ Заполняем карточку дела #{case_id}. Заполнено {filled}/{total}.\n"
        f"Сейчас: {CASE_CARD_FIELD_META[next_field]['title']}.\n"
        f"{prompt}"
    )
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
            f"✅ Выбрано дело #{cid}. Теперь выбери документ 👇",
            reply_markup=docs_menu_ikb(cid),
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
    doc_key = parts[2] if len(parts) == 3 else ""

    # Берём выбранное дело из state (мы его сохраняем в case:docs:<id>)
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

    card = get_case_card(uid, cid)
    if not card:
        await call.message.answer(
            "Карточка дела ещё не заполнена.\n"
            "Добавь данные дела (пол, паспорт, долги и т.д.)."
        )
        await call.answer()
        return

    missing = validate_case_card(card)
    if missing:
        await call.message.answer(
            "Не хватает обязательных данных в карточке дела:\n"
            + "\n".join(f"- {m}" for m in missing)
        )
        await call.answer()
        return

    if doc_key != "bankruptcy_petition":
        await call.message.answer("Документ не найден")
        await call.answer()
        return

    path = build_bankruptcy_petition_doc(case_row, card)
    await call.message.answer_document(
        FSInputFile(path),
        caption=f"Готово ✅ Заявление о банкротстве для дела #{cid}",
    )
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("case:file:"))
async def case_file_send(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":", maxsplit=3)
    if len(parts) < 4:
        await call.answer()
        return

    cid_str, filename = parts[2], parts[3]

    if any(bad in filename for bad in ("/", "\\", "..")):
        await call.message.answer("Некорректное имя файла")
        await call.answer()
        return

    path = GENERATED_DIR / "cases" / cid_str / filename
    if not path.is_file():
        await call.message.answer("Файл не найден...")
        await call.answer()
        return

    await call.message.answer_document(FSInputFile(path))
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

@dp.message(Command("card_set"))
async def card_set(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    cid = await _selected_case_id(state)
    if cid is None:
        await message.answer("Сначала выбери дело через «📂 Дела», затем повтори /card_set и отправь JSON.")
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Пришли команду так:\n"
            "/card_set {JSON}\n\n"
            "Пример:\n"
            "/card_set {\"debtor_gender\":\"male\"}"
        )
        return

    raw_json = parts[1].strip()
    try:
        data = json.loads(raw_json)
        if not isinstance(data, dict):
            raise ValueError("JSON должен быть объектом (словарём)")
    except Exception as e:
        await message.answer(f"Ошибка JSON: {e}\n\nПроверь кавычки и запятые и пришли снова.")
        return

    # Сохраняем карточку
    upsert_case_card(uid, cid, data)

    missing = validate_case_card(data)
    if missing:
        await message.answer(
            "Карточка сохранена ✅\n"
            "Но пока не хватает обязательных полей:\n"
            + "\n".join(f"- {m}" for m in missing)
        )
        return

    await message.answer(
        "Карточка сохранена ✅\n"
        "Все обязательные поля заполнены. Теперь можно нажать «📄 Заявление о банкротстве»."
    )


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
        kb.button(
            text="🗂 Заполнить карточку дела",
            callback_data=f"card:fill:{cid}"
        )
        kb.button(text="🗂 Заполнить карточку дела", callback_data = f"case:card:{cid}")

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
    kb.button(text="📁 Карточка дела", callback_data=f"case:card:{cid}")
    kb.button(text="✏️ Номер дела", callback_data=f"case:edit:{cid}:case_number")
    kb.button(text="✏️ Суд", callback_data=f"case:edit:{cid}:court")
    kb.button(text="✏️ Судья", callback_data=f"case:edit:{cid}:judge")
    kb.button(text="✏️ ФУ", callback_data=f"case:edit:{cid}:fin_manager")
    kb.button(text="✏️ Стадия", callback_data=f"case:edit:{cid}:stage")
    kb.button(text="🗒 Заметки", callback_data=f"case:edit:{cid}:notes")
    kb.button(text="🔙 К списку дел", callback_data="case:list")
    kb.adjust(1, 2, 2, 2)

    await call.message.answer(text, reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_open(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.update_data(card_case_id=cid)
    card = get_case_card(uid, cid) or {}

    lines = [f"📁 Карточка дела #{cid}"]
    for key, title in [
        ("court_name", "Суд"),
        ("court_address", "Адрес суда"),
        ("debtor_full_name", "Должник"),
        ("debtor_gender", "Пол"),
        ("debtor_birth_date", "Дата рождения"),
        ("debtor_address", "Адрес должника"),
        ("passport_series", "Паспорт серия"),
        ("passport_number", "Паспорт номер"),
        ("passport_issued_by", "Кем выдан паспорт"),
        ("passport_date", "Дата выдачи паспорта"),
        ("passport_code", "Код подразделения"),
        ("total_debt_rubles", "Сумма долга (рубли)"),
        ("total_debt_kopeks", "Сумма долга (копейки)"),
    ]:
        lines.append(f"{title}: {card.get(key) or '—'}")

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Заполнить", callback_data=f"card:fill:{cid}")
    kb.button(text="🔙 Назад", callback_data=f"case:open:{cid}")
    kb.adjust(1)

    await call.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await call.answer()


CASE_CARD_FIELDS = [
    ("court_name", "Суд (название)"),
    ("court_address", "Суд (адрес)"),
    ("debtor_full_name", "Должник (ФИО)"),
    ("debtor_gender", "Пол должника (male/female)"),
    ("debtor_birth_date", "Дата рождения (дд.мм.гггг)"),
    ("debtor_address", "Адрес должника"),
    ("passport_series", "Паспорт серия"),
    ("passport_number", "Паспорт номер"),
    ("passport_issued_by", "Кем выдан паспорт"),
    ("passport_date", "Дата выдачи паспорта"),
    ("passport_code", "Код подразделения"),
    ("total_debt_rubles", "Сумма долга (рубли)"),
    ("total_debt_kopeks", "Сумма долга (копейки)"),
]


def build_case_card_kb(cid: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for key, title in CASE_CARD_FIELDS:
        kb.button(text=f"✏️ {title}", callback_data=f"case:cardfield:{cid}:{key}")
    kb.button(text="🔙 К списку дел", callback_data="case:list")
    kb.adjust(1)
    return kb


@dp.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_open(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.update_data(card_case_id=cid)
    card = get_case_card(uid, cid) or {}
    validation = validate_case_card(card)
    missing = validation.get("missing") if isinstance(validation, dict) else validation
    missing = missing or []

    total = len(CASE_CARD_FIELDS)
    filled = sum(1 for key, _ in CASE_CARD_FIELDS if card.get(key))
    missing_display = ", ".join(missing[:5]) if missing else "—"

    await call.message.answer(
        f"📁 Карточка дела #{cid}\n"
        f"Заполнено: {filled}/{total}\n"
        f"Пустые: {missing_display}",
        reply_markup=build_case_card_kb(cid).as_markup(),
    )
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("case:cardfield:"))
async def case_card_field(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":", maxsplit=3)
    cid = int(cid_str)
    await state.update_data(card_case_id=cid, card_field_key=field)
    await state.set_state(CaseCardFill.waiting_value)

    title = CASE_CARD_FIELD_META.get(field, {}).get("title", field)
    prompt = CASE_CARD_FIELD_META.get(field, {}).get("prompt", "")
    await call.message.answer(
        f"✍️ {title}\n{prompt}\nОтправь '-' чтобы очистить."
    )
    await call.answer()


# DISABLED: legacy handler (conflicts with case_card_value_set)
async def case_card_value(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    data = await state.get_data()
    cid = data.get("card_case_id")
    field = data.get("card_field_key")
    if not cid or not field:
        await state.clear()
        await message.answer("Что-то пошло не так. Открой карточку заново через дело.")
        return

    raw = (message.text or "").strip()
    value: Any = None if raw == "-" else raw

    if field == "debtor_gender" and value is not None:
        gender = str(value).lower()
        if gender not in {"male", "female"}:
            await message.answer("Пол укажи как male или female.")
            return
        value = gender

    if field == "total_debt_rubles" and value is not None:
        if not str(value).isdigit():
            await message.answer("Нужно указать число в рублях.")
            return
        value = int(value)

    if field == "total_debt_kopeks" and value is not None:
        if not str(value).isdigit():
            await message.answer("Нужно число 0-99 для копеек.")
            return
        kop = int(value)
        if kop < 0 or kop > 99:
            await message.answer("Копейки должны быть от 0 до 99.")
            return
        value = kop

    card = get_case_card(uid, int(cid)) or {}
    card[field] = value
    upsert_case_card(uid, int(cid), card)

    validation = validate_case_card(card)
    missing = validation.get("missing") if isinstance(validation, dict) else validation
    missing = missing or []

    if missing:
        next_field = missing[0]
        await state.update_data(card_case_id=int(cid), card_field_key=next_field)
        await state.set_state(CaseCardFill.waiting_value)
        title = next((title for key, title in CASE_CARD_FIELDS if key == next_field), next_field)
        await message.answer(
            f"Сохранено. Следующее поле: {title}.\nОтправь '-' чтобы очистить.")
        return

    await state.clear()
    await message.answer(
        "✅ Карточка заполнена", reply_markup=build_case_card_kb(int(cid)).as_markup()
    )


CASE_CARD_FIELDS = [
    ("court_name", "Суд (название)"),
    ("court_address", "Суд (адрес)"),
    ("debtor_full_name", "Должник (ФИО)"),
    ("debtor_gender", "Пол должника (male/female)"),
    ("debtor_birth_date", "Дата рождения (дд.мм.гггг)"),
    ("debtor_address", "Адрес должника"),
    ("passport_series", "Паспорт серия"),
    ("passport_number", "Паспорт номер"),
    ("passport_issued_by", "Кем выдан паспорт"),
    ("passport_date", "Дата выдачи паспорта"),
    ("passport_code", "Код подразделения"),
    ("total_debt_rubles", "Сумма долга (рубли)"),
    ("total_debt_kopeks", "Сумма долга (копейки)"),
]


def build_case_card_kb(cid: int, fields: list[tuple[str, str]] = CASE_CARD_FIELDS):
    kb = InlineKeyboardBuilder()
    for key, title in fields:
        kb.button(text=f"✏️ {title}", callback_data=f"case:cardfield:{cid}:{key}")
    kb.button(text="🔙 К списку дел", callback_data="case:list")
    kb.adjust(1)
    return kb


@dp.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_open(call: CallbackQuery, state: FSMContext, fields: list[tuple[str, str]] = CASE_CARD_FIELDS):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.update_data(card_case_id=cid)
    card = get_case_card(uid, cid) or {}
    validation_result = validate_case_card(card)
    missing = (
        validation_result.get("missing", [])
        if isinstance(validation_result, dict)
        else validation_result
    )

    total = len(fields)
    filled = sum(1 for key, _ in fields if card.get(key))
    missing_display = ", ".join(missing[:5]) if missing else "—"

    await call.message.answer(
        f"📁 Карточка дела #{cid}\n"
        f"Заполнено: {filled}/{total}\n"
        f"Пустые: {missing_display}",
        reply_markup=build_case_card_kb(cid, fields=fields).as_markup(),
    )
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("case:cardfield:"))
async def case_card_field(call: CallbackQuery, state: FSMContext, fields: list[tuple[str, str]] = CASE_CARD_FIELDS):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":", maxsplit=3)
    cid = int(cid_str)
    await state.update_data(card_case_id=cid, card_field_key=field)
    await state.set_state(CaseCardFill.waiting_value)

    title = CASE_CARD_FIELD_META.get(field, {}).get("title", field)
    prompt = CASE_CARD_FIELD_META.get(field, {}).get("prompt", "")
    await call.message.answer(
        f"✍️ {title}\n{prompt}\nОтправь '-' чтобы очистить."
    )
    await call.answer()

# DISABLED: legacy handler (conflicts with case_card_value_set)
async def case_card_value_legacy(message: Message, state: FSMContext, fields: list[tuple[str, str]] = CASE_CARD_FIELDS):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    data = await state.get_data()
    cid = data.get("card_case_id")
    field = data.get("card_field_key")
    if not cid or not field:
        await state.clear()
        await message.answer("Что-то пошло не так. Открой карточку заново через дело.")
        return

    raw = (message.text or "").strip()
    value: Any = None if raw == "-" else raw

    if field == "debtor_gender" and value is not None:
        gender = str(value).lower()
        if gender not in {"male", "female"}:
            await message.answer("Пол укажи как male или female.")
            return
        value = gender
    if field == "total_debt_rubles" and value is not None:
        if not str(value).isdigit():
            await message.answer("Нужно указать число в рублях.")
            return
        value = int(value)
    if field == "total_debt_kopeks" and value is not None:
        if not str(value).isdigit():
            await message.answer("Нужно число 0-99 для копеек.")
            return
        kop = int(value)
        if kop < 0 or kop > 99:
            await message.answer("Копейки должны быть от 0 до 99.")
            return
        value = kop

    card = get_case_card(uid, int(cid)) or {}
    card[field] = value
    upsert_case_card(uid, int(cid), card)

    missing = validate_case_card(card).get("missing", [])
    if missing:
        next_field = missing[0]
        await state.update_data(card_case_id=int(cid), card_field_key=next_field)
        await state.set_state(CaseCardFill.waiting_value)
        title = next((title for key, title in fields if key == next_field), next_field)
        await message.answer(
            f"Сохранено. Следующее поле: {title}.\nОтправь '-' чтобы очистить.")
        return

    await state.clear()
    await message.answer(
        "✅ Карточка заполнена",
        reply_markup=build_case_card_kb(int(cid), fields=fields).as_markup(),
    )


CASE_CARD_FIELDS = [
    (
        "court_name",
        {
            "title": "Наименование суда",
            "prompt": "Укажи наименование суда.",
        },
    ),
    (
        "court_address",
        {
            "title": "Адрес суда",
            "prompt": "Укажи адрес суда.",
        },
    ),
    (
        "debtor_last_name",
        {
            "title": "Фамилия должника",
            "prompt": "Укажи фамилию должника.",
        },
    ),
    (
        "debtor_first_name",
        {
            "title": "Имя должника",
            "prompt": "Укажи имя должника.",
        },
    ),
    (
        "debtor_full_name",
        {
            "title": "ФИО должника",
            "prompt": "Укажи полное ФИО должника.",
        },
    ),
    (
        "debtor_gender",
        {
            "title": "Пол должника",
            "prompt": "Пол должника (м/ж или male/female).",
        },
    ),
    (
        "debtor_birth_date",
        {
            "title": "Дата рождения",
            "prompt": "Дата рождения должника (ДД.ММ.ГГГГ).",
        },
    ),
    (
        "debtor_address",
        {
            "title": "Адрес должника",
            "prompt": "Адрес регистрации должника.",
        },
    ),
    (
        "passport_series",
        {
            "title": "Серия паспорта",
            "prompt": "Укажи серию паспорта (4 цифры).",
        },
    ),
    (
        "passport_number",
        {
            "title": "Номер паспорта",
            "prompt": "Укажи номер паспорта (6 цифр).",
        },
    ),
    (
        "passport_issued_by",
        {
            "title": "Кем выдан паспорт",
            "prompt": "Кем выдан паспорт (полностью).",
        },
    ),
    (
        "passport_date",
        {
            "title": "Дата выдачи паспорта",
            "prompt": "Дата выдачи паспорта (ДД.ММ.ГГГГ).",
        },
    ),
    (
        "passport_code",
        {
            "title": "Код подразделения",
            "prompt": "Код подразделения (например 123-456).",
        },
    ),
    (
        "total_debt_rubles",
        {
            "title": "Сумма долга (руб.)",
            "prompt": "Общая сумма долга в рублях (целое число).",
        },
    ),
    (
        "total_debt_kopeks",
        {
            "title": "Сумма долга (коп.)",
            "prompt": "Копейки (0-99).",
        },
    ),
]

CASE_CARD_FIELD_META = {k: v for k, v in CASE_CARD_FIELDS}


def _format_case_card(card: dict[str, Any]) -> list[str]:
    lines = []
    for key, meta in CASE_CARD_FIELDS:
        val = card.get(key)
        show_val = "—"
        if val is None or str(val).strip() == "":
            show_val = "—"
        elif isinstance(val, (int, float)):
            show_val = str(val)
        else:
            show_val = str(val)
        lines.append(f"{meta['title']}: {show_val}")
    return lines


def _humanize_missing(missing: list[str]) -> str:
    titles = [CASE_CARD_FIELD_META.get(key, {}).get("title", key) for key in missing]
    return ", ".join(titles)


def _card_completion_status(card: dict[str, Any]) -> tuple[int, int]:
    validation = validate_case_card(card)
    missing = validation.get("missing") or []
    total = len(CASE_CARD_REQUIRED_FIELDS)
    return total - len(missing), total


async def send_card_fill_menu(message_target, uid: int, cid: int) -> None:
    row = get_case(uid, cid)
    if not row:
        await message_target.answer("Дело не найдено.")
        return

    _, _owner_user_id, code_name, *_ = row
    card = get_case_card(uid, cid)
    validation = validate_case_card(card)

    filled, total = _card_completion_status(card)
    text_lines = ["📁 Карточка дела", f"Дело #{cid} | {code_name}"]
    text_lines.append("")
    text_lines.extend(_format_case_card(card))
    text_lines.append("")
    text_lines.append(f"Заполнено: {filled}/{total}")

    if validation.get("missing"):
        text_lines.append("Не заполнено: " + _humanize_missing(validation["missing"]))
    else:
        text_lines.append("Карточка заполнена ✅")

    kb = InlineKeyboardBuilder()
    for key, meta in CASE_CARD_FIELDS:
        kb.button(text=f"✏️ {meta['title']}", callback_data=f"case:cardfield:{cid}:{key}")
    kb.button(text="🔙 Назад к делам", callback_data="case:list")
    kb.adjust(1)

    await message_target.answer("\n".join(text_lines), reply_markup=kb.as_markup())


async def send_case_card_menu(message_target, uid: int, cid: int) -> None:
    row = get_case(uid, cid)
    if not row:
        await message_target.answer("Дело не найдено.")
        return

    _, _owner_user_id, code_name, *_ = row
    card = get_case_card(uid, cid)
    validation = validate_case_card(card)

    text_lines = ["📁 Карточка дела", f"Дело #{cid} | {code_name}"]
    text_lines.append("")
    text_lines.extend(_format_case_card(card))

    if validation.get("missing"):
        text_lines.append("")
        text_lines.append("Не заполнено: " + _humanize_missing(validation["missing"]))
    else:
        text_lines.append("")
        text_lines.append("Карточка заполнена ✅")

    kb = InlineKeyboardBuilder()
    for key, meta in CASE_CARD_FIELDS:
        kb.button(text=f"✏️ {meta['title']}", callback_data=f"case:card_edit:{cid}:{key}")
    kb.button(text="🔙 Готово", callback_data=f"case:open:{cid}")
    kb.adjust(1)

    await message_target.answer("\n".join(text_lines), reply_markup=kb.as_markup())


@dp.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.clear()
    await state.update_data(card_case_id=cid)
    await send_card_fill_menu(call.message, uid, cid)
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("case:card_edit:"))
async def case_card_edit(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":", maxsplit=3)
    cid = int(cid_str)

    if field not in CASE_CARD_FIELD_META:
        await call.answer()
        return

    row = get_case(uid, cid)
    if not row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    await state.clear()
    await state.update_data(card_cid=cid, card_field=field)
    await state.set_state(CaseCardFill.waiting_value)

    prompt = CASE_CARD_FIELD_META[field]["prompt"]
    await call.message.answer(prompt)
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("card:fill:"))
async def card_fill_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str = call.data.split(":", maxsplit=2)
    cid = int(cid_str)

    await state.clear()

    # Берём текущую карточку и находим первое незаполненное поле
    card = get_case_card(uid, cid) or {}
    next_field = None
    for key, _meta in CASE_CARD_FIELDS:
        val = card.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            next_field = key
            break

    # Если всё заполнено — просто покажем меню карточки
    if not next_field:
        await state.update_data(card_case_id=cid)
        await send_card_fill_menu(call.message, uid, cid)
        await call.answer()
        return

    # Иначе — сразу стартуем ввод первого незаполненного поля
    await state.update_data(card_case_id=cid, card_field_key=next_field)
    await state.set_state(CaseCardFill.waiting_value)

    filled, total = _card_completion_status(card)
    prompt = CASE_CARD_FIELD_META[next_field]["prompt"] + "\nОтправь '-' чтобы оставить пустым."
    await call.message.answer(
        f"✍️ Заполняем карточку дела #{cid}. Заполнено {filled}/{total}.\n"
        f"Сейчас: {CASE_CARD_FIELD_META[next_field]['title']}.\n"
        f"{prompt}"
    )
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("case:cardfield:"))
async def card_field_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":", maxsplit=3)
    cid = int(cid_str)

    if field not in CASE_CARD_FIELD_META:
        await call.answer()
        return

    await state.clear()
    await state.update_data(card_case_id=cid, card_field_key=field)
    await state.set_state(CaseCardFill.waiting_value)

    prompt = CASE_CARD_FIELD_META[field]["prompt"] + "\nОтправь '-' чтобы оставить пустым."
    await call.message.answer(prompt)
    await call.answer()


def _normalize_card_input(field: str, text: str) -> tuple[bool, str | int | None, str | None]:
    cleaned = text.strip()
    if not cleaned:
        return False, None, "Пусто. Повтори ввод."

    if field == "debtor_gender":
        gender = cleaned.lower()
        if gender in ("м", "male", "m"):
            return True, "male", None
        if gender in ("ж", "female", "f", "жен", "женщина"):
            return True, "female", None
        return False, None, "Укажи пол как м/ж или male/female."

    if field == "passport_date":
        try:
            datetime.strptime(cleaned, "%d.%m.%Y")
        except ValueError:
            return False, None, "Формат даты: ДД.ММ.ГГГГ. Попробуй ещё раз."
        return True, cleaned, None

    if field == "total_debt_rubles":
        try:
            val = int(cleaned)
        except ValueError:
            return False, None, "Нужно целое число в рублях."
        if val < 0:
            return False, None, "Значение не может быть отрицательным."
        return True, val, None

    if field == "total_debt_kopeks":
        try:
            val = int(cleaned)
        except ValueError:
            return False, None, "Нужно целое число (0-99)."
        if val < 0 or val > 99:
            return False, None, "Копейки должны быть от 0 до 99."
        return True, val, None

    return True, cleaned, None


@dp.message(CaseCardFill.waiting_value)
async def case_card_value_set(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    data = await state.get_data()
    cid = data.get("card_cid") or data.get("card_case_id")
    field = data.get("card_field") or data.get("card_field_key")

    if not cid or not field:
        await state.clear()
        await message.answer("Что-то пошло не так. Открой карточку заново через дело.")
        return

    card = get_case_card(uid, int(cid))
    raw_text = message.text or ""
    if raw_text.strip() == "-":
        ok, value, error_msg = True, None, None
    else:
        ok, value, error_msg = _normalize_card_input(field, raw_text)
        if not ok:
            await message.answer(error_msg)
            return

    card[field] = value
    if field in {"debtor_last_name", "debtor_first_name", "debtor_middle_name"}:
        composed = _compose_debtor_full_name(card)
        if composed:
            card["debtor_full_name"] = composed

    upsert_case_card(uid, int(cid), card)
    next_field = None
    for key, _meta in CASE_CARD_FIELDS:
        val = card.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            next_field = key
            break

    if next_field:
        await state.update_data(card_case_id=int(cid), card_field_key=next_field)
        await state.set_state(CaseCardFill.waiting_value)
        prompt = CASE_CARD_FIELD_META[next_field]["prompt"]
        filled, total = _card_completion_status(card)
        await message.answer(
            f"✅ Сохранено. Заполнено {filled}/{total}.\n"
            f"Далее: {CASE_CARD_FIELD_META[next_field]['title']}.\n"
            f"{prompt}\nОтправь '-' чтобы оставить пустым."
        )
        return

    await state.clear()
    filled, total = _card_completion_status(card)
    await message.answer(
        f"✅ Сохранено. Заполнено {filled}/{total}.",
        reply_markup=case_card_ikb(int(cid)),
    )

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
