import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from dotenv import load_dotenv
load_dotenv()

from bankrot_bot.logging_setup import setup_logging
#from bankrot_bot.services.gigachat import gigachat_chat

logger = logging.getLogger(__name__)


from bankrot_bot.services.blocks import (
    build_creditors_header_block,
    build_creditors_block,
    sum_creditors_total,
    build_vehicle_block,
    build_attachments_list,
)
from bankrot_bot.services.public_docs import (
    get_categories,
    get_docs_in_category,
    get_document,
    CATEGORY_TITLES,
)
from bankrot_bot.services.case_financials import (
    get_case_parties,
    add_case_party,
    delete_case_party,
    calculate_parties_totals,
    format_parties_for_doc,
    get_case_assets,
    add_case_asset,
    delete_case_asset,
    calculate_assets_total,
    parse_amount_input,
    normalize_amount_to_string,
    string_to_decimal,
)
from bankrot_bot.services.docx_forms import (
    render_creditors_list,
    render_inventory,
)

import aiohttp
setup_logging()
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, BufferedInputFile, Message, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from docx import Document
from bankrot_bot.config import load_settings

# Database and handlers
from bankrot_bot.database import init_db as init_pg_db
from bankrot_bot.handlers import cases as cases_handlers
#from handlers import probability as probability_handlers
from handlers import newcase_fsm

from bankrot_bot.keyboards.menus import (
    main_menu_kb,
    start_ikb,
    home_ikb,
    profile_ikb,
    cases_list_ikb,
    case_card_ikb,
    docs_home_ikb,
    help_ikb,
    help_item_ikb,
    docs_menu_ikb,
    case_files_ikb,
    case_archive_ikb,
    cases_menu_ikb,
    my_cases_ikb,
    docs_catalog_ikb,
    docs_category_ikb,
    docs_item_ikb,
    case_parties_ikb,
    party_view_ikb,
    case_assets_ikb,
    asset_view_ikb,
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
class CreditorsFill(StatesGroup):
    name = State()
    inn = State()
    ogrn = State()
    address = State()
    debt_rubles = State()
    debt_kopeks = State()
    note = State()
    creditors_text = State()  # For bulk creditor text input

class AddParty(StatesGroup):
    """FSM для добавления кредитора/должника."""
    name = State()
    amount = State()
    basis = State()

class AddAsset(StatesGroup):
    """FSM для добавления имущества."""
    kind = State()
    description = State()
    value = State()

# =========================
# env
# =========================


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


def _old_build_creditors_block(creditors: list[dict] | None) -> str:
    """
    Поддерживает 2 формата кредиторов:

    1) Новый (опросник):
       {
         "name": "...",
         "inn": "...", "ogrn": "...",
         "debt_rubles": "...", "debt_kopeks": "...",
         "note": "ОКБ/договор/и т.п."
       }

    2) Старый:
       {
         "name": "...",
         "obligations": [{"amount_rubles":123,"amount_kopeks":45,"source":"ОКБ"}]
       }
    """
    if not isinstance(creditors, list) or not creditors:
        return ""

    def _digits(s: str) -> str:
        return "".join(ch for ch in str(s) if ch.isdigit())

    lines: list[str] = []

    for i, c in enumerate(creditors, start=1):
        if not isinstance(c, dict):
            continue

        name = str((c.get("name") or "Кредитор")).strip()

        # --- идентификаторы (для нового формата) ---
        inn = str(c.get("inn") or "").strip()
        ogrn = str(c.get("ogrn") or "").strip()
        ids = []
        if inn:
            ids.append(f"ИНН {inn}")
        if ogrn:
            ids.append(f"ОГРН {ogrn}")
        name_with_ids = name + (f" ({', '.join(ids)})" if ids else "")

        # --- новый формат суммы ---
        debt_r = c.get("debt_rubles")
        debt_k = c.get("debt_kopeks")
        note = str(c.get("note") or "").strip()

        money_new = ""
        if debt_r not in (None, "", "-"):
            dr = _digits(debt_r)
            if dr != "":
                money_new = f"{int(dr)} руб."
        if debt_k not in (None, "", "-"):
            dk = _digits(debt_k)
            if dk != "":
                money_new = (money_new + " " if money_new else "") + f"{int(dk):02d} коп."

        if money_new and note:
            line_new = f"{i}) {name_with_ids} — {money_new} ({note})"
        elif money_new:
            line_new = f"{i}) {name_with_ids} — {money_new}"
        elif note:
            line_new = f"{i}) {name_with_ids} — ({note})"
        else:
            line_new = f"{i}) {name_with_ids}"

        # --- старый формат obligations имеет приоритет, если он реально заполнен ---
        obs = c.get("obligations")
        if isinstance(obs, list) and any(isinstance(x, dict) for x in obs):
            obs_txt: list[str] = []
            for ob in obs:
                if not isinstance(ob, dict):
                    continue
                r = ob.get("amount_rubles")
                k = ob.get("amount_kopeks")
                src = (ob.get("source") or "").strip()

                money_parts: list[str] = []
                if r is not None and str(r).strip() != "":
                    money_parts.append(f"{int(r)} руб.")
                if k is not None and str(k).strip() != "":
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
        else:
            lines.append(line_new)

    return "\n".join(lines)

def _old_sum_creditors_total(creditors: list[dict] | None) -> tuple[int, int]:
    """
    Возвращает (rubles, kopeks) как сумму по всем кредиторам.
    Поддерживает оба формата:
      - obligations: [{amount_rubles, amount_kopeks, ...}]
      - debt_rubles / debt_kopeks
    """
    if not isinstance(creditors, list) or not creditors:
        return (0, 0)

    def _to_int(x) -> int:
        if x is None:
            return 0
        s = "".join(ch for ch in str(x) if ch.isdigit())
        return int(s) if s else 0

    total_k = 0

    for c in creditors:
        if not isinstance(c, dict):
            continue

        obs = c.get("obligations")
        if isinstance(obs, list) and any(isinstance(o, dict) for o in obs):
            for ob in obs:
                if not isinstance(ob, dict):
                    continue
                r = _to_int(ob.get("amount_rubles"))
                k = _to_int(ob.get("amount_kopeks"))
                total_k += r * 100 + k
            continue

        # новый формат
        r = _to_int(c.get("debt_rubles"))
        k = _to_int(c.get("debt_kopeks"))
        total_k += r * 100 + k

    return (total_k // 100, total_k % 100)

def _old_build_vehicle_block(card: dict) -> str:
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
        return "Транспортные средства отсутствуют."

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


def _old_build_attachments_list(card: dict) -> str:
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

def _old_build_online_hearing_docx(case_row: Tuple) -> Path:
    """
    Генерация ходатайства о ВКС (онлайн-заседание).
    Делает простой DOCX без шаблона, чтобы гарантированно не падать.
    """
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

    doc = Document()

    # Шапка: кому и от кого
    doc.add_paragraph("В Арбитражный суд")
    doc.add_paragraph(court or "не указано")
    doc.add_paragraph("")

    prof = get_profile(owner_user_id)
    if prof:
        _, full_name, role, address, phone, email, *_ = prof
        doc.add_paragraph("От: " + (full_name or "не указано"))
        if role:
            doc.add_paragraph("Статус: " + role)
        if address:
            doc.add_paragraph("Адрес: " + address)
        if phone:
            doc.add_paragraph("Телефон: " + phone)
        if email:
            doc.add_paragraph("Email: " + email)
    else:
        doc.add_paragraph("От: не указано")

    doc.add_paragraph("")
    doc.add_paragraph("ХОДАТАЙСТВО")
    doc.add_paragraph("о проведении судебного заседания с использованием ВКС")
    doc.add_paragraph("")

    if case_number:
        doc.add_paragraph(f"Дело № {case_number}")
    if judge:
        doc.add_paragraph(f"Судья: {judge}")
    if fin_manager:
        doc.add_paragraph(f"Финансовый управляющий: {fin_manager}")

    doc.add_paragraph("")
    doc.add_paragraph("Прошу обеспечить участие в судебном заседании с использованием системы видеоконференц-связи.")
    doc.add_paragraph("")
    doc.add_paragraph("Дата: " + datetime.now().strftime("%d.%m.%Y"))
    doc.add_paragraph("")
    doc.add_paragraph("Подпись: ____________")

    fname = f"online_hearing_case_{cid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    case_dir = GENERATED_DIR / "cases" / str(cid)
    case_dir.mkdir(parents=True, exist_ok=True)
    out_path = case_dir / fname
    doc.save(out_path)
    return out_path


async def build_bankruptcy_petition_doc(case_row: Tuple, card: dict) -> Path:
    """
    Генерация заявления о банкротстве по шаблону.
    Подстановка строго по 23 плейсхолдерам шаблона + дефолты для пустых данных.

    НОВОЕ: приоритетно используем данные из case_parties (если есть).
    """
    cid = case_row[0]

    template_path = Path("templates/petitions/bankruptcy_petition.docx")
    doc = Document(template_path)

    # Попытка загрузить кредиторов из новых таблиц
    creditors_from_db = []
    try:
        from bankrot_bot.database import get_session

        async with get_session() as session:
            parties = await get_case_parties(session, cid, role="creditor")
            if parties:
                creditors_from_db = format_parties_for_doc(parties, role="creditor")
    except Exception as e:
        logger.warning(f"Failed to load creditors from DB for case {cid}: {e}")

    # --- дефолты ---
    def _txt(v: Any) -> str:
        v = "" if v is None else str(v).strip()
        return v if v else "не указано"

    def _money_rubles(v: Any) -> str:
        v = "" if v is None else str(v).strip()
        return v if v else "0"

    def _money_kopeks(v: Any) -> str:
        if v is None or str(v).strip() == "":
            return "00"
        try:
            return f"{int(str(v).strip()):02d}"
        except (ValueError, TypeError):
            s = str(v).strip()
            digits = "".join(ch for ch in s if ch.isdigit())
            if digits == "":
                return "00"
            try:
                return f"{int(digits):02d}"
            except (ValueError, TypeError):
                return "00"

    # --- исходные данные ---
    court_name = _txt(card.get("court_name") or (case_row[4] if len(case_row) > 4 else None))
    court_address = _txt(card.get("court_address"))

    financial_manager_info = _txt(
        card.get("financial_manager_info") or (case_row[6] if len(case_row) > 6 else None)
    )

    debtor_full_name = _txt(card.get("debtor_full_name"))
    debtor_address = _txt(card.get("debtor_address"))
    debtor_birth_date = _txt(card.get("debtor_birth_date"))
    debtor_inn = _txt(card.get("debtor_inn"))
    debtor_snils = _txt(card.get("debtor_snils"))
    debtor_phone = _txt(card.get("debtor_phone"))

    passport_series = (card.get("passport_series") or "").strip()
    passport_number = (card.get("passport_number") or "").strip()
    debtor_passport = _txt(f"{passport_series} {passport_number}".strip())

    debtor_passport_issued_by = _txt(card.get("passport_issued_by"))
    debtor_passport_date = _txt(card.get("passport_date"))
    debtor_passport_code = _txt(card.get("passport_code"))

    raw_marital = card.get("marital_status")
    raw_marital = ("" if raw_marital is None else str(raw_marital)).strip().lower()

    debtor_address = (debtor_address or "").strip()
    while ",," in debtor_address:
        debtor_address = debtor_address.replace(",,", ",")
    debtor_address = debtor_address.rstrip(" ,")

    marital_map = {
        "married": "Состоит в зарегистрированном браке.",
        "single": "В браке не состоит.",
        "divorced": "Брак расторгнут.",
        "widowed": "Вдовец/вдова.",
    }

    # Если уже введён нормальный русский текст — оставляем как есть
    if raw_marital in marital_map:
        marital_status = marital_map[raw_marital]
    else:
        # если строка пустая -> дефолт "не указано"
        # если строка не пустая (в т.ч. русский текст) -> используем как есть
        marital_status = _txt(raw_marital)

    certificate_number = card.get("certificate_number") or card.get("marriage_certificate_number")
    certificate_date = card.get("certificate_date") or card.get("marriage_certificate_date")
    certificate_number = _txt(certificate_number)
    certificate_date = _txt(certificate_date)

    # НОВАЯ ЛОГИКА: приоритет - creditors_from_db, потом card creditors
    if creditors_from_db:
        creditors = creditors_from_db
    else:
        creditors = card.get("creditors") if isinstance(card.get("creditors"), list) else []

    auto_r, auto_k = sum_creditors_total(creditors)
    if auto_r or auto_k:
        total_debt_rubles = str(auto_r)
        total_debt_kopeks = f"{auto_k:02d}"
    else:
        total_debt_rubles = _money_rubles(card.get("total_debt_rubles"))
        total_debt_kopeks = _money_kopeks(card.get("total_debt_kopeks"))

    deposit_deferral_request = card.get("deposit_deferral_request") or ""
    # attachments_list по утверждённым дефолтам должен быть пустым, если нет данных
    attachments_list = ""
    try:
        built_attachments = build_attachments_list(card)
        if built_attachments and str(built_attachments).strip():
            attachments_list = str(built_attachments)
    except (KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Failed to build attachments list: {e}")
        attachments_list = ""

    # creditors_block: creditors_text приоритетно, иначе список, иначе нейтральный текст
    creditors_text = card.get("creditors_text")
    creditors_text = str(creditors_text).strip() if creditors_text is not None else ""
    creditors = card.get("creditors") if isinstance(card.get("creditors"), list) else []

    if creditors_text:
        creditors_block = creditors_text
    elif creditors:
        creditors_block = build_creditors_block(creditors)
    else:
        creditors_block = "Сведения о кредиторах не представлены."

    # creditors_header_block: короткий список для шапки (из того же источника, что и creditors_block)
    if creditors:
        creditors_header_block = build_creditors_header_block(creditors)
    else:
        creditors_header_block = "Сведения о кредиторах не представлены."

    # vehicle_block: дефолт при отсутствии
    vehicle_block = ""
    try:
        vehicle_block = build_vehicle_block(card) or ""
    except (KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Failed to build vehicle block: {e}")
        vehicle_block = ""
    if not str(vehicle_block).strip():
        vehicle_block = "Транспортные средства: отсутствуют."

    # --- статус ИП (умная логика: справка или ЕГРИП) ---
    ip_cert_number = (card.get("ip_certificate_number") or "").strip()
    ip_cert_date = (card.get("ip_certificate_date") or "").strip()

    if ip_cert_number and ip_cert_date:
        ip_status_text = (
            "не зарегистрирован в качестве индивидуального предпринимателя, "
            f"что подтверждается справкой № {ip_cert_number} от {ip_cert_date}."
        )
    else:
        ip_status_text = (
            "не зарегистрирован в качестве индивидуального предпринимателя, "
            "что подтверждается сведениями из ЕГРИП"
        )

    # нормализация, чтобы не было 'ЕГРИП..'
    ip_status_text = (ip_status_text or "").strip()
    while ".." in ip_status_text:
        ip_status_text = ip_status_text.replace("..", ".")

    mapping = {
        "attachments_list": attachments_list,
        "certificate_date": certificate_date,
        "certificate_number": certificate_number,
        "court_address": court_address,
        "court_name": court_name,

        # Кредиторы: шапка + основной блок
        "creditors_block": creditors_block,
        "creditors_header_block": creditors_header_block,

        "date": datetime.now().strftime("%d.%m.%Y"),

        "debtor_address": debtor_address,
        "debtor_birth_date": debtor_birth_date,
        "debtor_full_name": debtor_full_name,

        # В шаблоне есть и обычные, и *_or_absent
        "debtor_inn": debtor_inn if debtor_inn != "не указано" else "",
        "debtor_inn_or_absent": debtor_inn if debtor_inn != "не указано" else "отсутствует",

        "debtor_snils": debtor_snils if debtor_snils != "не указано" else "",
        "debtor_snils_or_absent": debtor_snils if debtor_snils != "не указано" else "отсутствует",

        "debtor_phone_or_absent": debtor_phone if debtor_phone != "не указано" else "отсутствует",

        # Паспорт: ключи должны совпадать с плейсхолдерами шаблона
        "passport_series": passport_series or "",
        "passport_number": passport_number or "",
        "passport_issued_by": debtor_passport_issued_by if debtor_passport_issued_by != "не указано" else "",
        "passport_date": debtor_passport_date if debtor_passport_date != "не указано" else "",
        "passport_code": debtor_passport_code if debtor_passport_code != "не указано" else "",

        # Эти плейсхолдеры есть в шаблоне (ты их показывал в списке)
        "debtor_last_name_initials": build_debtor_last_name_initials(card),

        "financial_manager_info": financial_manager_info,
        "family_status_block": build_family_status_block(card),
        "ip_status_text": ip_status_text,

        "marital_status": marital_status,

        "total_debt_kopeks": total_debt_kopeks,
        "total_debt_rubles": total_debt_rubles,

        "vehicle_block": vehicle_block,

        "deposit_deferral_request": deposit_deferral_request,
    }

    # гендерные формы (debtor_having_word, debtor_registered_word, debtor_living_word,
    # debtor_not_registered_word, debtor_insolvent_word)
    try:
        gender_forms = build_gender_forms(card.get("debtor_gender"))
        if isinstance(gender_forms, dict):
            mapping.update(gender_forms)
    except (KeyError, TypeError, AttributeError) as e:
        # если пол не заполнен или функция упала — ставим нейтральные значения
        logger.warning(f"Failed to build gender forms: {e}")
        mapping.update(
            {
                "debtor_having_word": "имеющий(ая)",
                "debtor_registered_word": "зарегистрированный(ая)",
                "debtor_living_word": "проживающий(ая)",
                "debtor_not_registered_word": "не зарегистрирован(а)",
                "debtor_insolvent_word": "неплатёжеспособный(ая)",
            }
        )


    _replace_placeholders_strong(doc, mapping)
    # второй проход — добиваем плейсхолдеры, разорванные Word по runs
    for p in doc.paragraphs:
        for run in p.runs:
            if "{{" in run.text:
                for k, v in mapping.items():
                    run.text = run.text.replace(f"{{{{{k}}}}}", "" if v is None else str(v))

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        if "{{" in run.text:
                            for k, v in mapping.items():
                                run.text = run.text.replace(f"{{{{{k}}}}}", "" if v is None else str(v))


    # Контроль: не должно остаться {{...}}
    def _has_unreplaced_placeholders(d: Document) -> bool:
        for p in d.paragraphs:
            if "{{" in (p.text or ""):
                return True
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        if "{{" in (p.text or ""):
                            return True
        return False

    if _has_unreplaced_placeholders(doc):
        import re

        # диагностируем, что именно осталось в документе
        left = set()

        def _scan_paragraph_for_left(p):
            txt = p.text or ""
            for m in re.findall(r"\{\{[^}]+\}\}", txt):
                left.add(m)

        for p in doc.paragraphs:
            _scan_paragraph_for_left(p)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        _scan_paragraph_for_left(p)
                    for nested in cell.tables:
                        for nrow in nested.rows:
                            for ncell in nrow.cells:
                                for p in ncell.paragraphs:
                                    _scan_paragraph_for_left(p)

        import logging
        logging.exception("UNREPLACED_PLACEHOLDERS: %s", sorted(left))

        raise ValueError("В документе остались не заменённые плейсхолдеры вида {{...}}")

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

settings = load_settings()

BOT_TOKEN = settings["BOT_TOKEN"]
AUTH_KEY = settings["GIGACHAT_AUTH_KEY"]
SCOPE = settings["GIGACHAT_SCOPE"]
MODEL = settings["GIGACHAT_MODEL"]

RAW_ALLOWED = settings["RAW_ALLOWED"]
RAW_ADMINS = settings["RAW_ADMINS"]
GENERATED_DIR = settings["GENERATED_DIR"]

DB_PATH = settings["DB_PATH"]

# Initialize cases_db module with database path
from bankrot_bot.services.cases_db import (
    init_cases_db,
    list_cases,
    get_case,
    create_case,
    update_case_fields,
    update_case_meta,
    get_case_card,
    validate_case_card,
    get_profile,
    upsert_profile,
    migrate_case_cards_table,
    CASE_CARD_REQUIRED_FIELDS,
    CASE_CARDS_ALLOWED_COLUMNS,
)
init_cases_db(DB_PATH)

def _parse_ids(s: str) -> set[int]:
    out = set()
    for x in (s.split(",") if s else []):
        x = x.strip()
        if x.isdigit():
            out.add(int(x))
    return out


ALLOWED_USERS = _parse_ids(RAW_ALLOWED)
ADMIN_USERS = _parse_ids(RAW_ADMINS)

# Import authorization functions from shared module to break circular imports
from bankrot_bot.shared import is_allowed, is_admin, init_allowed_users


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
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse existing case card JSON for case_id={case_id}: {e}")
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
# bot logic
# =========================
from aiogram.fsm.storage.redis import RedisStorage

# Configure Redis storage for FSM
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
storage = RedisStorage.from_url(redis_url)
dp = Dispatcher(storage=storage)

# =========================
# ROUTER REGISTRATION - PRIORITY ORDER MATTERS!
# =========================
# Router order determines handler priority (first registered = highest priority).
# This prevents message routing conflicts and ensures predictable behavior.
#
# PRIORITY ORDER (highest to lowest):
# 1. COMMANDS - cases_handlers.router (Command handlers with explicit StateFilter)
#    - /newcase, /mycases, /case, /setactive, /editcase, /cancel
#    - These must run FIRST to catch commands before FSM or text handlers
#
# 2. FSM STATES - newcase_fsm.router (FSM handlers with explicit StateFilter)
#    - F.text == "➕ Новое дело" with StateFilter(None) - only when NOT in FSM
#    - NewCase FSM states with StateFilter - only when IN specific FSM state
#    - StateFilter prevents conflicts with commands and other handlers
#
# 3. DIRECT DP HANDLERS - Callbacks and other handlers registered directly on dp
#    - @dp.callback_query() - Callback query handlers
#    - @dp.message(StateFilter(...)) - FSM handlers (AddParty, AddAsset, etc.)
#    - These run LAST as fallback/catch-all handlers
#
# CRITICAL RULES:
# ✅ ALL FSM state handlers MUST use StateFilter to prevent catching commands
# ✅ Command handlers run first (registered routers before direct dp handlers)
# ✅ Text filters (F.text) MUST have StateFilter or be very specific
# ✅ Callback handlers can be registered anywhere (F.data is specific enough)
#
# DO NOT change router order without understanding priority implications!
# =========================

# 1. Commands (highest priority)
dp.include_router(cases_handlers.router)

# 2. FSM states with StateFilter
# Register probability router (Phase 9)
# dp.include_router(probability_handlers.router)
# Register new case FSM router (Phase 12 fix)
dp.include_router(newcase_fsm.router)

# 3. Callback handlers will be registered later after helper functions are defined

# 4. Direct dp handlers (callbacks, FSM, etc.) registered below have lowest priority

USER_FLOW: Dict[int, Dict[str, Any]] = {}
LAST_RESULT: Dict[int, str] = {}


def cancel_flow(uid: int) -> None:
    USER_FLOW.pop(uid, None)


# main_keyboard() definition removed - see line 4336 for active implementation


def export_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура экспорта документа."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Экспорт (показать текст)", callback_data="export:word")
    kb.adjust(1)
    return kb.as_markup()


def court_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа суда."""
    kb = InlineKeyboardBuilder()
    kb.button(text="Арбитражный суд", callback_data="motion:court:arbitr")
    kb.button(text="Суд общей юрисдикции", callback_data="motion:court:general")
    kb.adjust(1)
    return kb.as_markup()


def motion_actions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура действий для ходатайства."""
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="flow:cancel")
    kb.adjust(1)
    return kb.as_markup()


def settlement_actions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура действий для мирового соглашения."""
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
async def cmd_start(message: Message) -> None:
    """
    Handle /start command.

    Shows welcome message with main menu (both reply keyboard and inline keyboard).
    Reply keyboard provides persistent bottom navigation buttons.

    Args:
        message: Incoming /start command message
    """
    uid = message.from_user.id
    if not is_allowed(uid):
        logger.warning(f"Unauthorized /start attempt by user {uid}")
        return
    cancel_flow(uid)

    # Import refactored main menu (inline) and reply keyboard
    from keyboards import main_menu

    text = (
        "🏠 Добро пожаловать!\n\n"
        "Бот-помощник по банкротству физических лиц.\n\n"
        "Выберите раздел для работы:"
    )

    # Send with reply keyboard (bottom buttons) for persistent navigation
    await message.answer(text, reply_markup=main_menu_kb())

    # Optionally send inline keyboard for additional options
    # await message.answer("Или выберите из меню:", reply_markup=main_menu())


# =========================
# Reply Keyboard Handlers
# =========================

@dp.message(StateFilter(None), F.text == "➕ Новое дело")
async def reply_new_case(message: Message) -> None:
    """
    Handle '➕ Новое дело' reply keyboard button.

    Shows cases menu with options to create new case or view existing cases.
    StateFilter(None) ensures this only fires when user is NOT in FSM.

    Args:
        message: Message with reply keyboard button text
    """
    uid = message.from_user.id
    if not is_allowed(uid):
        logger.warning(f"Unauthorized new case access attempt by user {uid}")
        return

    await message.answer(
        "📋 Мои дела о банкротстве:",
        reply_markup=cases_menu_ikb()
    )


@dp.message(StateFilter(None), F.text == "👤 Мой профиль")
async def reply_my_profile(message: Message) -> None:
    """
    Handle '👤 Мой профиль' reply keyboard button.

    Shows user profile with inline keyboard options.
    StateFilter(None) ensures this only fires when user is NOT in FSM.

    Args:
        message: Message with reply keyboard button text
    """
    uid = message.from_user.id
    if not is_allowed(uid):
        logger.warning(f"Unauthorized profile access attempt by user {uid}")
        return

    await message.answer("👤 Мой профиль:", reply_markup=profile_ikb())


@dp.message(StateFilter(None), F.text == "📄 Документы")
async def reply_documents(message: Message) -> None:
    """
    Handle '📄 Документы' reply keyboard button.

    Shows public documents catalog with inline keyboard options.
    StateFilter(None) ensures this only fires when user is NOT in FSM.

    Args:
        message: Message with reply keyboard button text
    """
    uid = message.from_user.id
    if not is_allowed(uid):
        logger.warning(f"Unauthorized documents access attempt by user {uid}")
        return

    await message.answer(
        "📄 Публичный каталог документов\n\n"
        "Выберите категорию:",
        reply_markup=docs_catalog_ikb()
    )


@dp.message(StateFilter(None), F.text == "❓ Помощь")
async def reply_help(message: Message) -> None:
    """
    Handle '❓ Помощь' reply keyboard button.

    Shows help menu with inline keyboard options.
    StateFilter(None) ensures this only fires when user is NOT in FSM.

    Args:
        message: Message with reply keyboard button text
    """
    uid = message.from_user.id
    if not is_allowed(uid):
        logger.warning(f"Unauthorized help access attempt by user {uid}")
        return

    await message.answer(
        "❓ Помощь\n\n"
        "Выберите тему:",
        reply_markup=help_ikb()
    )


@dp.callback_query(F.data == "menu:home")
async def menu_home(call: CallbackQuery) -> None:
    """
    Navigate to home/main menu.

    Args:
        call: Callback query from menu navigation
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("Главное меню:", reply_markup=home_ikb())
    await call.answer()


@dp.callback_query(F.data == "menu:profile")
async def menu_profile(call: CallbackQuery) -> None:
    """
    Navigate to user profile menu.

    Args:
        call: Callback query from menu navigation
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("👤 Мой профиль:", reply_markup=profile_ikb())
    await call.answer()


@dp.callback_query(F.data == "menu:docs")
async def menu_docs(call: CallbackQuery) -> None:
    """
    Navigate to public documents catalog.

    Публичный каталог документов - доступен всем авторизованным пользователям.

    Args:
        call: Callback query from menu navigation
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer(
        "📄 Публичный каталог документов\n\n"
        "Здесь вы найдете шаблоны и образцы документов для банкротства.\n"
        "Выберите категорию:",
        reply_markup=docs_catalog_ikb()
    )
    await call.answer()


@dp.callback_query(F.data == "menu:help")
async def menu_help(call: CallbackQuery) -> None:
    """
    Navigate to help section.

    Подменю раздела Помощь.

    Args:
        call: Callback query from menu navigation
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer(
        "❓ Раздел помощи\n\n"
        "Выберите интересующую тему:",
        reply_markup=help_ikb(),
    )
    await call.answer()


# ========== Новые хэндлеры главного меню ==========

@dp.callback_query(F.data == "menu:my_cases")
async def menu_my_cases(call: CallbackQuery, state: FSMContext):
    """Раздел «Мои дела» - интеграция с модулем cases."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    rows = list_cases(uid)

    # Получить активное дело из state (если есть)
    data = await state.get_data()
    active_case_id = data.get("active_case_id")

    text = "📂 Мои дела\n\n"
    if rows:
        text += f"У вас {len(rows)} дел(а/о).\n"
        if active_case_id:
            text += f"Активное дело: #{active_case_id}\n"
        text += "Выберите дело для работы или создайте новое."
    else:
        text += "У вас пока нет дел. Создайте первое дело для работы."

    await call.message.answer(text, reply_markup=my_cases_ikb(rows, active_case_id))
    await call.answer()


@dp.callback_query(F.data == "ai:placeholder")
async def ai_placeholder(call: CallbackQuery):
    """Заглушка для ИИ-помощника."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await call.answer("🤖 ИИ-помощник в разработке. Скоро будет доступен!", show_alert=True)


# ========== Хэндлеры раздела «Помощь» ==========

@dp.callback_query(F.data == "help:howto")
async def help_howto(call: CallbackQuery):
    """Как пользоваться ботом."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    text = (
        "📖 Как пользоваться ботом\n\n"
        "1️⃣ Главное меню\n"
        "В главном меню три раздела:\n"
        "• Мои дела - управление делами о банкротстве\n"
        "• Документы - публичный каталог образцов\n"
        "• Помощь - справочная информация\n\n"
        "2️⃣ Работа с делами\n"
        "• Создайте карточку дела\n"
        "• Заполните данные должника и кредиторов\n"
        "• Генерируйте документы по делу\n\n"
        "3️⃣ Навигация\n"
        "Используйте кнопки для перемещения между разделами.\n"
        "Кнопка 🏠 всегда возвращает в главное меню."
    )

    await call.message.answer(text, reply_markup=help_item_ikb())
    await call.answer()


@dp.callback_query(F.data == "help:cases")
async def help_cases(call: CallbackQuery):
    """Что такое карточки дел."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    text = (
        "📋 Карточки дел\n\n"
        "Карточка дела - это структурированное хранилище информации "
        "по конкретному делу о банкротстве.\n\n"
        "Что хранится:\n"
        "• Данные должника (ФИО, адрес, паспорт)\n"
        "• Информация о кредиторах\n"
        "• Сумма задолженности\n"
        "• Документы по делу\n"
        "• История изменений\n\n"
        "Карточка привязана к вашему Telegram-аккаунту и доступна только вам.\n\n"
        "На основе данных карточки бот может генерировать юридические документы."
    )

    await call.message.answer(text, reply_markup=help_item_ikb())
    await call.answer()


@dp.callback_query(F.data == "help:docs")
async def help_docs(call: CallbackQuery):
    """О документах."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    text = (
        "📄 О документах\n\n"
        "Бот работает с двумя типами документов:\n\n"
        "1️⃣ Публичный каталог\n"
        "Образцы и шаблоны документов, доступные всем пользователям:\n"
        "• Заявления\n"
        "• Ходатайства\n"
        "• Прочие документы\n\n"
        "2️⃣ Документы по делу\n"
        "Генерируются автоматически на основе данных вашей карточки дела.\n"
        "Привязаны к конкретному делу и хранятся в вашем архиве.\n\n"
        "Все документы формируются в формате DOCX и готовы к использованию."
    )

    await call.message.answer(text, reply_markup=help_item_ikb())
    await call.answer()


@dp.callback_query(F.data == "help:contacts")
async def help_contacts(call: CallbackQuery):
    """Контакты и обратная связь."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    text = (
        "✉️ Контакты и обратная связь\n\n"
        "По всем вопросам работы бота:\n"
        "• Сообщите об ошибке\n"
        "• Предложите улучшение\n"
        "• Задайте вопрос\n\n"
        "📧 Email: support@example.com\n"
        "💬 Telegram: @support_username\n\n"
        "Мы постоянно работаем над улучшением сервиса. "
        "Ваши отзывы помогают делать бота лучше!"
    )

    await call.message.answer(text, reply_markup=help_item_ikb())
    await call.answer()


@dp.callback_query(F.data == "help:about")
async def help_about(call: CallbackQuery):
    """О боте."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    text = (
        "ℹ️ О боте\n\n"
        "Telegram-бот помощник по банкротству физических лиц.\n\n"
        "Возможности:\n"
        "• Управление карточками дел\n"
        "• Генерация юридических документов\n"
        "• Каталог образцов документов\n"
        "• Справочная информация\n\n"
        "Версия: 1.0.0\n"
        "Статус: MVP (минимальный рабочий продукт)\n\n"
        "Бот находится в активной разработке. "
        "Следите за обновлениями!"
    )

    await call.message.answer(text, reply_markup=help_item_ikb())
    await call.answer()


# ========== Хэндлеры публичного каталога документов ==========

@dp.callback_query(F.data.startswith("docs_cat:"))
async def docs_category(call: CallbackQuery):
    """Показать документы в категории."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    category = call.data.split(":")[-1]
    docs = get_docs_in_category(category)

    if not docs:
        await call.answer("Документы в этой категории пока отсутствуют.", show_alert=True)
        return

    category_title = CATEGORY_TITLES.get(category, "Документы")
    text = f"{category_title}\n\nВыберите документ для просмотра:"

    await call.message.answer(text, reply_markup=docs_category_ikb(category, docs))
    await call.answer()


@dp.callback_query(F.data.startswith("docs_item:"))
async def docs_item(call: CallbackQuery):
    """Показать карточку документа."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Ошибка в данных.", show_alert=True)
        return

    category = parts[1]
    doc_id = parts[2]

    doc = get_document(category, doc_id)
    if not doc:
        await call.answer("Документ не найден.", show_alert=True)
        return

    text = f"📄 {doc['title']}\n\n{doc['description']}"

    await call.message.answer(text, reply_markup=docs_item_ikb(category))
    await call.answer()


# ========== Старые хэндлеры (для совместимости) ==========

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


# case_open() DUPLICATE REMOVED - see line ~2700 for active implementation

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

    # клавиатура: генерация + последний документ + архив
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Сформировать заявление о банкротстве (новое)", callback_data=f"case:gen:{case_id}:petition")
    if files:
        latest = files[0]
        kb.button(text="📎 Последний документ", callback_data=f"case:lastdoc:{case_id}")
        kb.button(text="📚 Архив документов", callback_data=f"case:archive:{case_id}:1")
    kb.button(text="🔙 Назад к делу", callback_data=f"case:open:{case_id}")
    kb.adjust(1)

    if not files:
        await call.message.answer(
            f"📎 Документы по делу #{case_id} пока отсутствуют.\n"
            "Нажми кнопку ниже, чтобы сформировать новый документ (он сохранится в архив).",
            reply_markup=kb.as_markup(),
        )
        if hasattr(call, "answer"):
            await call.answer()
        return

    await call.message.answer(
        f"📎 Документы по делу #{case_id} (последние сверху):",
        reply_markup=kb.as_markup(),
    )
    if hasattr(call, "answer"):
        await call.answer()

@dp.callback_query(F.data.startswith("case:lastdoc:"))
async def case_lastdoc_send(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])
    case_dir = GENERATED_DIR / "cases" / str(case_id)
    if not case_dir.is_dir():
        await call.message.answer("Документы не найдены.")
        await call.answer()
        return

    files = sorted(
        [p.name for p in case_dir.iterdir() if p.is_file() and p.suffix.lower() == ".docx"],
        reverse=True,
    )
    if not files:
        await call.message.answer("Документы не найдены.")
        await call.answer()
        return

    path = case_dir / files[0]
    if not path.is_file():
        await call.message.answer("Файл не найден (возможно, удалён).")
        await call.answer()
        return

    await call.message.answer_document(FSInputFile(path), caption=f"Последний документ по делу #{case_id}")
    await call.answer()


@dp.callback_query(F.data.startswith("case:archive:"))
async def case_archive(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    if len(parts) < 4:
        await call.answer()
        return

    case_id = int(parts[2])
    try:
        page = int(parts[3])
    except ValueError:
        page = 1
    if page < 1:
        page = 1

    case_dir = GENERATED_DIR / "cases" / str(case_id)
    files_all = []
    if case_dir.is_dir():
        files_all = sorted(
            [p.name for p in case_dir.iterdir() if p.is_file() and p.suffix.lower() == ".docx"],
            reverse=True,
        )

    archive_files = files_all[1:] if len(files_all) > 1 else []
    per_page = 10
    total = len(archive_files)
    max_page = max(1, (total + per_page - 1) // per_page)
    if page > max_page:
        page = max_page

    start = (page - 1) * per_page
    end = min(start + per_page, total)
    chunk = archive_files[start:end]

    kb = InlineKeyboardBuilder()
    if not chunk:
        kb.button(text="(архив пуст)", callback_data="noop")
    else:
        for i, name in enumerate(chunk, start=start):
            kb.button(text=f"📎 {name}", callback_data=f"case:fileidx:{case_id}:{i}")

    if page > 1:
        kb.button(text="⬅️ Назад", callback_data=f"case:archive:{case_id}:{page-1}")
    if page < max_page:
        kb.button(text="➡️ Далее", callback_data=f"case:archive:{case_id}:{page+1}")

    kb.button(text="🔙 Назад к документам", callback_data=f"case:docs:{case_id}")
    kb.adjust(1)

    await call.message.answer(
        f"📚 Архив документов по делу #{case_id} (стр. {page}/{max_page})",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("case:fileidx:"))
async def case_file_send_by_index(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    if len(parts) < 4:
        await call.answer()
        return

    case_id = int(parts[2])
    try:
        idx = int(parts[3])
    except ValueError:
        await call.answer()
        return

    case_dir = GENERATED_DIR / "cases" / str(case_id)
    files_all = []
    if case_dir.is_dir():
        files_all = sorted(
            [p.name for p in case_dir.iterdir() if p.is_file() and p.suffix.lower() == ".docx"],
            reverse=True,
        )

    archive_files = files_all[1:] if len(files_all) > 1 else []
    if idx < 0 or idx >= len(archive_files):
        await call.message.answer("Файл не найден (возможно, архив изменился). Открой архив заново.")
        await call.answer()
        return

    filename = archive_files[idx]
    path = case_dir / filename
    if not path.is_file():
        await call.message.answer("Файл не найден (возможно, удалён).")
        await call.answer()
        return

    await call.message.answer_document(FSInputFile(path))
    await call.answer()

# case_file_send() DUPLICATE REMOVED - see line ~2350 for active implementation

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

        path = await build_bankruptcy_petition_doc(case_row, card)
        await call.message.answer_document(
            FSInputFile(path),
            caption=f"Готово ✅ Заявление о банкротстве (дело #{case_id})",
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

@dp.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 2)
async def case_edit_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    await state.clear()


    

    # --- EDIT MENU SHELL (no docs, no CaseCardFill) ---

    row = get_case(uid, case_id)

    if not row:

        await call.message.answer("Дело не найдено.")

        await call.answer()

        return

    

    try:

        case_number = row[2] if len(row) > 2 else ""

        stage = row[3] if len(row) > 3 else ""

        court = row[5] if len(row) > 5 else ""

        judge = row[6] if len(row) > 6 else ""

        fin_manager = row[7] if len(row) > 7 else ""

        notes = row[8] if len(row) > 8 else ""

    except (IndexError, TypeError) as e:
        logger.warning(f"Failed to parse case row: {e}")
        case_number = stage = court = judge = fin_manager = notes = ""

    

    text = (

        f"✏️ Редактирование карточки дела #{case_id}\n\n"

        f"Номер дела: {case_number or '—'}\n"

        f"Суд: {court or '—'}\n"

        f"Судья: {judge or '—'}\n"

        f"ФУ: {fin_manager or '—'}\n"

        f"Стадия: {stage or '—'}\n"

        f"Заметки: {notes or '—'}"

    )

    

    kb = InlineKeyboardBuilder()

    kb.button(text="📋 Показать карточку дела", callback_data=f"case:card:{case_id}")

    kb.button(text="✏️ Номер дела", callback_data=f"case:edit:{case_id}:case_number")

    kb.button(text="✏️ Суд", callback_data=f"case:edit:{case_id}:court")

    kb.button(text="✏️ Судья", callback_data=f"case:edit:{case_id}:judge")

    kb.button(text="✏️ ФУ", callback_data=f"case:edit:{case_id}:fin_manager")

    kb.button(text="✏️ Стадия", callback_data=f"case:edit:{case_id}:stage")

    kb.button(text="🗒 Заметки", callback_data=f"case:edit:{case_id}:notes")

    kb.button(text="🔙 Назад к делу", callback_data=f"case:open:{case_id}")

    kb.adjust(1, 2, 2, 2, 1)

    

    await call.message.answer(text, reply_markup=kb.as_markup())

    await call.answer()

    return

    # --- /EDIT MENU SHELL ---

    
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


@dp.callback_query(lambda c: c.data == "docs:choose_case")
async def docs_choose_case(call: CallbackQuery):
    """Показывает список дел для выбора дела для документов."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    rows = list_cases(uid)
    if not rows:
        await call.message.answer("Пока нет дел. Создай дело через «📂 Дела».")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    lines = ["📄 Выбери дело для генерации документов:"]
    for (cid, code_name, case_number, stage, updated_at) in rows:
        num = case_number or "-"
        lines.append(f"#{cid} | {code_name} | № {num}")
        kb.button(text=f"Дело #{cid}: {code_name}", callback_data=f"docs:case:{cid}")

    kb.button(text="🔙 Назад", callback_data="docs:back_menu")
    kb.adjust(1)

    await call.message.answer("\n".join(lines), reply_markup=kb.as_markup())
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

    validation = validate_case_card(card)
    missing = validation.get("missing", [])
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

    path = await build_bankruptcy_petition_doc(case_row, card)
    await call.message.answer_document(
        FSInputFile(path),
        caption=f"Готово ✅ Заявление о банкротстве для дела #{cid}",
    )
    await call.answer()

@dp.callback_query(F.data.startswith("case:file:"))
async def case_file_send(call: CallbackQuery) -> None:
    """
    Send a document file from case directory to user.

    Callback format: case:file:<case_id>:<filename>

    Args:
        call: Telegram callback query with file request

    Security: Validates filename to prevent directory traversal attacks
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":", maxsplit=3)
    if len(parts) < 4:
        logger.warning(f"Invalid case:file callback format: {call.data}")
        await call.answer("Некорректный формат команды")
        return

    cid_str, filename = parts[2], parts[3]

    # Security: Prevent directory traversal attacks
    if any(bad in filename for bad in ("/", "\\", "..")):
        logger.warning(f"Directory traversal attempt by user {uid}: {filename}")
        await call.message.answer("Некорректное имя файла")
        await call.answer()
        return

    path = GENERATED_DIR / "cases" / cid_str / filename
    if not path.is_file():
        logger.info(f"File not found: {path}")
        await call.message.answer("Файл не найден")
        await call.answer()
        return

    try:
        await call.message.answer_document(FSInputFile(path))
        await call.answer()
    except Exception as e:
        logger.error(f"Failed to send file {path}: {e}")
        await call.message.answer("Ошибка при отправке файла")
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

    validation = validate_case_card(data)
    missing = validation.get("missing", [])
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

@dp.message(StateFilter(CaseCreate.code_name))
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

@dp.message(StateFilter(CaseCreate.case_number))
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

@dp.message(StateFilter(ProfileFill.full_name))
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

@dp.message(StateFilter(ProfileFill.role))
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

@dp.message(StateFilter(ProfileFill.address))
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

@dp.message(StateFilter(ProfileFill.phone))
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
@dp.message(StateFilter(ProfileFill.email))
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

@dp.message(StateFilter(CaseCreate.court))
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


@dp.message(StateFilter(CaseCreate.judge))
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


@dp.message(StateFilter(CaseCreate.fin_manager))
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

@dp.callback_query(F.data.startswith("case:open:"))
async def case_open(call: CallbackQuery) -> None:
    """
    Display full case card with all details and editing options.

    Callback format: case:open:<case_id>
    Shows: code_name, case_number, court, judge, manager, stage, notes, timestamps

    Args:
        call: Callback query from cases list
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    try:
        cid = int(call.data.split(":")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid callback data format: {call.data}, error: {e}")
        await call.answer("Ошибка формата данных")
        return

    row = get_case(uid, cid)
    if not row:
        logger.info(f"Case {cid} not found or access denied for user {uid}")
        await call.message.answer("Дело не найдено или у вас нет доступа.")
        await call.answer()
        return

    (cid, _owner_user_id, code_name, case_number, court, judge,
     fin_manager, stage, notes, created_at, updated_at) = row

    text = (
        f"📌 Дело #{cid}\n"
        f"📋 Код: {code_name}\n"
        f"📄 Номер: {case_number or '—'}\n"
        f"🏛 Суд: {court or '—'}\n"
        f"⚖️ Судья: {judge or '—'}\n"
        f"👤 Фин. управляющий: {fin_manager or '—'}\n"
        f"📊 Стадия: {stage or '—'}\n"
        f"📝 Заметки: {notes or '—'}\n"
        f"📅 Создано: {created_at}\n"
        f"🔄 Обновлено: {updated_at}"
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
        "debtor_middle_name",
        {
            "title": "Отчество должника",
            "prompt": "Укажи отчество должника или '-' если нет.",
        },
    ),
    (
        "debtor_gender",
        {
            "title": "Пол должника",
            "prompt": "Укажи пол должника: м/ж.",
        },
    ),
    (
        "debtor_birth_date",
        {
            "title": "Дата рождения",
            "prompt": "Укажи дату рождения: ДД.ММ.ГГГГ.",
        },
    ),
    (
        "debtor_address",
        {
            "title": "Адрес должника",
            "prompt": "Укажи адрес должника.",
        },
    ),
    (
        "debtor_phone",
        {
            "title": "Телефон должника",
            "prompt": "Укажи телефон должника (можно в формате +7...) или '-' если отсутствует.",
        },
    ),
    (
        "debtor_inn",
        {
            "title": "ИНН должника",
            "prompt": "Укажи ИНН или '-' если отсутствует.",
        },
    ),
    (
        "debtor_snils",
        {
            "title": "СНИЛС должника",
            "prompt": "Укажи СНИЛС или '-' если отсутствует.",
        },
    ),
    (
        "passport_series",
        {
            "title": "Паспорт серия",
            "prompt": "Укажи серию паспорта (4 цифры) или '-' если отсутствует.",
        },
    ),
    (
        "passport_number",
        {
            "title": "Паспорт номер",
            "prompt": "Укажи номер паспорта (6 цифр) или '-' если отсутствует.",
        },
    ),
    (
        "passport_issued_by",
        {
            "title": "Кем выдан паспорт",
            "prompt": "Укажи кем выдан паспорт или '-' если отсутствует.",
        },
    ),
    (
        "passport_date",
        {
            "title": "Дата выдачи паспорта",
            "prompt": "Укажи дату выдачи: ДД.ММ.ГГГГ или '-' если отсутствует.",
        },
    ),
    (
        "passport_code",
        {
            "title": "Код подразделения",
            "prompt": "Укажи код подразделения (XXX-XXX) или '-' если отсутствует.",
        },
    ),
    (
        "marital_status",
        {
            "title": "Семейное положение",
            "prompt": "Укажи семейное положение (женат/замужем/не состоит и т.п.) или '-' если неизвестно.",
        },
    ),
    (
        "certificate_number",
        {
            "title": "Свидетельство (номер)",
            "prompt": "Укажи номер свидетельства (о браке/разводе) или '-' если не применимо.",
        },
    ),
    (
        "certificate_date",
        {
            "title": "Свидетельство (дата)",
            "prompt": "Укажи дату свидетельства: ДД.ММ.ГГГГ или '-' если не применимо.",
        },
    ),
    (
        "total_debt_rubles",
        {
            "title": "Сумма долга (рубли)",
            "prompt": "Укажи сумму долга в рублях (целое число).",
        },
    ),
    (
        "total_debt_kopeks",
        {
            "title": "Сумма долга (копейки)",
            "prompt": "Укажи копейки (0-99).",
        },
    ),

    # ВАЖНО: это не обычное поле ввода, а отдельное меню кредиторов.
    # Мы будем перехватывать этот key в обработчике клика по полю.
    (
        "creditors",
        {
            "title": "🏦 Кредиторы (список)",
            "prompt": "Открываю меню кредиторов…",
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

    # отдельный раздел кредиторов
    creditors_count = 0
    try:
        creditors_val = card.get("creditors")
        if isinstance(creditors_val, list):
            creditors_count = len(creditors_val)
    except (TypeError, AttributeError):
        creditors_count = 0

    kb.button(text=f"👥 Кредиторы ({creditors_count})", callback_data=f"case:creditors:{cid}")
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

    # ✅ ВАЖНО: creditors — это НЕ текстовое поле, а отдельное меню
    if field == "creditors":
        await state.clear()
        await state.update_data(card_case_id=cid)
        await send_creditors_menu(call.message, uid, cid)
        await call.answer()
        return

    await state.clear()
    await state.update_data(card_cid=cid, card_field=field)
    await state.set_state(CaseCardFill.waiting_value)

    prompt = CASE_CARD_FIELD_META[field]["prompt"] + "\nОтправь '-' чтобы оставить пустым."
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

    # Кредиторы — отдельное меню, не обычный ввод текста
    if field == "creditors":
        await state.clear()
        await state.update_data(card_case_id=cid)
        await send_creditors_menu(call.message, uid, cid)
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


@dp.message(StateFilter(CaseCardFill.waiting_value))
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
    await message.answer(f"✅ Карточка заполнена. Заполнено {filled}/{total}.")

def _format_creditor_line(i: int, c: dict) -> str:
    name = (c.get("name") or "—").strip()
    inn = (c.get("inn") or "").strip()
    ogrn = (c.get("ogrn") or "").strip()
    debt_r = (c.get("debt_rubles") or "").strip()
    debt_k = (c.get("debt_kopeks") or "").strip()

    parts = [f"{i}) {name}"]
    ids = []
    if inn:
        ids.append(f"ИНН {inn}")
    if ogrn:
        ids.append(f"ОГРН {ogrn}")
    if ids:
        parts.append(" (" + ", ".join(ids) + ")")
    if debt_r or debt_k:
        dk = debt_k if debt_k else "00"
        dr = debt_r if debt_r else "0"
        parts.append(f" — {dr} руб. {dk} коп.")
    return "".join(parts)


def _safe_digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


async def send_creditors_menu(message_target, uid: int, cid: int) -> None:
    """Helper функция для отправки меню кредиторов."""
    card = get_case_card(uid, cid) or {}
    creditors = card.get("creditors")
    if not isinstance(creditors, list):
        creditors = []

    creditors_text = (card.get("creditors_text") or "").strip()

    lines = [f"👥 Кредиторы для дела #{cid}"]
    lines.append(f"Список: {len(creditors)}")
    if creditors_text:
        lines.append("Есть ручной текст creditors_text: ✅ (он имеет приоритет при генерации)")
    else:
        lines.append("Ручной текст creditors_text: —")

    if creditors:
        lines.append("")
        lines.append("Текущий список:")
        for i, c in enumerate(creditors, 1):
            lines.append(_format_creditor_line(i, c))

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить кредитора", callback_data=f"creditors:add:{cid}")
    kb.button(text="🗑 Удалить кредитора", callback_data=f"creditors:del:{cid}")
    kb.button(text="🧾 Ввести одним текстом", callback_data=f"creditors:text:{cid}")
    kb.button(text="🧹 Очистить creditors_text", callback_data=f"creditors:text_clear:{cid}")
    kb.button(text="🔙 Назад в карточку", callback_data=f"case:card:{cid}")
    kb.adjust(1)

    await message_target.answer("\n".join(lines), reply_markup=kb.as_markup())


# ============================================================================
# REGISTER CALLBACK ROUTER (handlers/callbacks.py)
# Must be done AFTER all helper functions are defined for circular import
# ============================================================================
from handlers.callbacks import callback_router
dp.include_router(callback_router)


@dp.callback_query(lambda c: c.data.startswith("case:creditors:"))
async def creditors_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.clear()
    await state.update_data(card_case_id=cid)

    await send_creditors_menu(call.message, uid, cid)
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("creditors:add:"))
async def creditors_add_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    cid = int(call.data.split(":")[2])

    await state.clear()
    await state.update_data(card_case_id=cid, creditor_tmp={})
    await state.set_state(CreditorsFill.name)
    await call.message.answer("Введи название кредитора (обязательно).")
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("creditors:del:"))
async def creditors_delete_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    cid = int(call.data.split(":")[2])

    card = get_case_card(uid, cid) or {}
    creditors = card.get("creditors")
    if not isinstance(creditors, list) or not creditors:
        await call.message.answer("Список кредиторов пуст.")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    lines = [f"🗑 Удаление кредитора (дело #{cid})", "Выбери номер:"]
    for i, c in enumerate(creditors, 1):
        lines.append(_format_creditor_line(i, c))
        kb.button(text=f"Удалить #{i}", callback_data=f"creditors:delone:{cid}:{i}")
    kb.button(text="🔙 Назад", callback_data=f"case:creditors:{cid}")
    kb.adjust(1)

    await call.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith("creditors:delone:"))
async def creditors_delete_one(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, idx_str = call.data.split(":")
    cid = int(cid_str)
    idx = int(idx_str)

    card = get_case_card(uid, cid) or {}
    creditors = card.get("creditors")
    if not isinstance(creditors, list):
        creditors = []
    if idx < 1 or idx > len(creditors):
        await call.message.answer("Некорректный номер.")
        await call.answer()
        return

    removed = creditors.pop(idx - 1)
    card["creditors"] = creditors
    upsert_case_card(uid, cid, card)

    name = (removed.get("name") or "—").strip()
    await call.message.answer(f"✅ Удалено: {name}")
    # вернём меню кредиторов
    await creditors_menu(call, state)


@dp.callback_query(lambda c: c.data.startswith("creditors:text_clear:"))
async def creditors_text_clear(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    cid = int(call.data.split(":")[2])

    card = get_case_card(uid, cid) or {}
    card["creditors_text"] = None
    upsert_case_card(uid, cid, card)

    await call.message.answer("✅ creditors_text очищен.")
    await creditors_menu(call, state)


@dp.callback_query(lambda c: c.data.startswith("creditors:text:"))
async def creditors_text_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    cid = int(call.data.split(":")[2])

    await state.clear()
    await state.update_data(card_case_id=cid)
    await state.set_state(CreditorsFill.creditors_text)

    await call.message.answer(
        "Вставь текст кредиторов одним блоком.\n"
        "Он будет иметь приоритет над списком creditors при генерации.\n"
        "Отправь '-' чтобы очистить."
    )
    await call.answer()


@dp.message(StateFilter(CreditorsFill.creditors_text))
async def creditors_text_set(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    data = await state.get_data()
    cid = int(data.get("card_case_id"))

    text = (message.text or "").strip()
    card = get_case_card(uid, cid) or {}

    if text == "-":
        card["creditors_text"] = None
        upsert_case_card(uid, cid, card)
        await state.clear()
        await message.answer("✅ creditors_text очищен.")
        # показать меню кредиторов
        await send_creditors_menu(message, uid, cid)
        return

    card["creditors_text"] = text
    upsert_case_card(uid, cid, card)

    await state.clear()
    await message.answer("✅ Сохранено creditors_text.")
    await send_creditors_menu(message, uid, cid)


@dp.message(StateFilter(CreditorsFill.name))
async def creditors_step_name(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt or txt == "-":
        await message.answer("Название кредитора обязательно. Введи ещё раз.")
        return

    data = await state.get_data()
    tmp = data.get("creditor_tmp") or {}
    tmp["name"] = txt
    await state.update_data(creditor_tmp=tmp)
    await state.set_state(CreditorsFill.inn)
    await message.answer("ИНН (можно '-' чтобы пропустить).")


@dp.message(StateFilter(CreditorsFill.inn))
async def creditors_step_inn(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    tmp = data.get("creditor_tmp") or {}

    if txt != "-" and txt:
        tmp["inn"] = _safe_digits(txt)
    await state.update_data(creditor_tmp=tmp)
    await state.set_state(CreditorsFill.ogrn)
    await message.answer("ОГРН (можно '-' чтобы пропустить).")


@dp.message(StateFilter(CreditorsFill.ogrn))
async def creditors_step_ogrn(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    tmp = data.get("creditor_tmp") or {}

    if txt != "-" and txt:
        tmp["ogrn"] = _safe_digits(txt)
    await state.update_data(creditor_tmp=tmp)
    await state.set_state(CreditorsFill.address)
    await message.answer("Адрес кредитора (можно '-' чтобы пропустить).")


@dp.message(StateFilter(CreditorsFill.address))
async def creditors_step_address(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    tmp = data.get("creditor_tmp") or {}

    if txt != "-" and txt:
        tmp["address"] = txt
    await state.update_data(creditor_tmp=tmp)
    await state.set_state(CreditorsFill.debt_rubles)
    await message.answer("Сумма долга (рубли) (можно '-' чтобы пропустить).")


@dp.message(StateFilter(CreditorsFill.debt_rubles))
async def creditors_step_debt_rubles(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    tmp = data.get("creditor_tmp") or {}

    if txt != "-" and txt:
        digits = _safe_digits(txt)
        if digits == "":
            await message.answer("Нужно число (или '-' чтобы пропустить).")
            return
        tmp["debt_rubles"] = digits
    await state.update_data(creditor_tmp=tmp)
    await state.set_state(CreditorsFill.debt_kopeks)
    await message.answer("Сумма долга (копейки 0-99) (можно '-' чтобы пропустить).")


@dp.message(StateFilter(CreditorsFill.debt_kopeks))
async def creditors_step_debt_kopeks(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    tmp = data.get("creditor_tmp") or {}

    if txt != "-" and txt:
        digits = _safe_digits(txt)
        if digits == "":
            await message.answer("Нужно число 0-99 (или '-' чтобы пропустить).")
            return
        try:
            val = int(digits)
        except ValueError:
            await message.answer("Нужно число 0-99.")
            return
        if val < 0 or val > 99:
            await message.answer("Копейки должны быть 0-99.")
            return
        tmp["debt_kopeks"] = f"{val:02d}"
    await state.update_data(creditor_tmp=tmp)
    await state.set_state(CreditorsFill.note)
    await message.answer("Основание/комментарий (например: выписка ОКБ) (можно '-' чтобы пропустить).")


@dp.message(StateFilter(CreditorsFill.note))
async def creditors_step_note(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    cid = int(data.get("card_case_id"))
    tmp = data.get("creditor_tmp") or {}

    if txt != "-" and txt:
        tmp["note"] = txt

    # сохранить в карточку
    card = get_case_card(message.from_user.id, cid) or {}
    creditors = card.get("creditors")
    if not isinstance(creditors, list):
        creditors = []
    creditors.append(tmp)
    card["creditors"] = creditors
    upsert_case_card(message.from_user.id, cid, card)

    await state.clear()

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить ещё", callback_data=f"creditors:add:{cid}")
    kb.button(text="✅ Готово", callback_data=f"case:creditors:{cid}")
    kb.adjust(1)

    await message.answer(
        f"✅ Кредитор добавлен. Сейчас в списке: {len(creditors)}",
        reply_markup=kb.as_markup(),
    )

@dp.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 3)
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

    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data=f"case:edit:{cid}")
    kb.adjust(1)

    await call.message.answer(
        f"Введи новое значение для «{title}».\nЕсли нужно очистить поле — отправь `-`.",
        reply_markup=kb.as_markup(),
    )

    await call.answer()
@dp.message(StateFilter(CaseEdit.value))
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

    # после сохранения — вернуть в меню редактирования карточки
    fake = type("X", (), {})()
    fake.from_user = message.from_user
    fake.data = f"case:edit:{cid}"
    fake.message = message
    await case_edit_menu(fake, state)

# =========================
# ROUTER CONFLICT FIX: Duplicate commands removed
# =========================
# These command handlers are now handled by bankrot_bot/handlers/cases.py
# which uses the newer PostgreSQL implementation instead of SQLite.
# Commands available in handlers/cases.py:
#   - /newcase (was /case_new here)
#   - /mycases (was /cases here)
#   - /case <id> (same)
#   - /setactive <id>
#   - /editcase
#   - /cancel
# =========================
# @dp.message(Command("case_new"))  # REMOVED - use /newcase from handlers/cases.py
# @dp.message(Command("cases"))     # REMOVED - use /mycases from handlers/cases.py
# @dp.message(Command("case"))      # REMOVED - use /case from handlers/cases.py


# =========================
# FSM handlers for AddParty and AddAsset (must be BEFORE catch-all!)
# =========================

@dp.message(StateFilter(AddParty.name))
async def process_party_name(message: Message, state: FSMContext):
    """Обработать ввод имени кредитора/должника. ONLY active in AddParty.name state."""
    logger.info(f"User {message.from_user.id} entered party name in AddParty FSM")
    await state.update_data(name=message.text.strip())
    await message.answer("Введите сумму (например: 100000 или 100 000.50):")
    await state.set_state(AddParty.amount)


@dp.message(StateFilter(AddParty.amount))
async def process_party_amount(message: Message, state: FSMContext):
    """Обработать ввод суммы. ONLY active in AddParty.amount state."""
    logger.info(f"User {message.from_user.id} entered party amount in AddParty FSM")
    # Normalize to JSON-safe string for Redis FSM storage
    amount_str = normalize_amount_to_string(message.text)
    if amount_str is None:
        await message.answer(
            "❌ Неверный формат суммы. Введите число (например: 100000 или 100 000.50):"
        )
        return
    await state.update_data(amount=amount_str)
    await message.answer("Введите основание требования/долга (или '-' для пропуска):")
    await state.set_state(AddParty.basis)


@dp.message(StateFilter(AddParty.basis))
async def process_party_basis(message: Message, state: FSMContext):
    """Завершить добавление кредитора/должника. ONLY active in AddParty.basis state."""
    logger.info(f"User {message.from_user.id} completing AddParty FSM")
    basis = message.text.strip() if message.text.strip() != "-" else None

    data = await state.get_data()
    case_id = data["case_id"]
    role = data["role"]
    name = data["name"]
    amount_str = data["amount"]

    # Convert JSON-safe string back to Decimal for DB insertion
    amount = string_to_decimal(amount_str)

    from bankrot_bot.database import get_session
    async with get_session() as session:
        await add_case_party(session, case_id, role, name, amount, basis=basis)
        await session.commit()
        logger.info(f"User {message.from_user.id} added party to case {case_id}: {name}, {amount}")

    role_text = "Кредитор" if role == "creditor" else "Должник"
    await message.answer(f"✅ {role_text} добавлен: {name}, сумма: {amount:.2f} ₽")
    await state.clear()


@dp.message(StateFilter(AddAsset.kind))
async def process_asset_kind(message: Message, state: FSMContext):
    """Обработать ввод вида имущества. ONLY active in AddAsset.kind state."""
    logger.info(f"User {message.from_user.id} entered asset kind in AddAsset FSM")
    await state.update_data(kind=message.text.strip())
    await message.answer("Введите описание (адрес, марка, реквизиты и т.п.):")
    await state.set_state(AddAsset.description)


@dp.message(StateFilter(AddAsset.description))
async def process_asset_description(message: Message, state: FSMContext):
    """Обработать ввод описания. ONLY active in AddAsset.description state."""
    logger.info(f"User {message.from_user.id} entered asset description in AddAsset FSM")
    await state.update_data(description=message.text.strip())
    await message.answer("Введите стоимость (или '-' для пропуска):")
    await state.set_state(AddAsset.value)


@dp.message(StateFilter(AddAsset.value))
async def process_asset_value(message: Message, state: FSMContext):
    """Завершить добавление имущества. ONLY active in AddAsset.value state."""
    logger.info(f"User {message.from_user.id} completing AddAsset FSM")
    value_text = message.text.strip()

    # Parse value with validation
    value = None
    if value_text != "-":
        # Use normalize_amount_to_string for consistent validation
        normalized = normalize_amount_to_string(value_text)
        if normalized is None:
            await message.answer(
                "❌ Неверный формат стоимости. Введите число (например: 100000 или 100 000.50) или '-' для пропуска:"
            )
            return
        value = string_to_decimal(normalized)

    data = await state.get_data()
    case_id = data["case_id"]
    kind = data["kind"]
    description = data["description"]

    from bankrot_bot.database import get_session
    async with get_session() as session:
        await add_case_asset(session, case_id, kind, description, value=value)
        await session.commit()
        logger.info(f"User {message.from_user.id} added asset to case {case_id}: {kind}, {value}")

    value_str = f"{float(value):.2f} ₽" if value else "не указана"
    await message.answer(f"✅ Имущество добавлено:\n{kind}\nСтоимость: {value_str}")
    await state.clear()


# =========================
# Catch-all message handler (must be AFTER FSM handlers!)
# =========================
@dp.message()
async def main_text_router(message: Message, state: FSMContext):
    # Если идёт FSM (создание дела и т.п.) — не мешаем
    if await state.get_state() is not None:
        return
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    
    # ✅ Команды всегда разрешены
    if message.text and message.text.startswith("/"):
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
            result = await gigachat_chat(
                auth_key=AUTH_KEY,
                scope=SCOPE,
                model=MODEL,
                system_prompt=system_prompt_for_settlement(),
                user_text=user_text,
            )
            LAST_RESULT[uid] = result
            await message.answer(result)
            await message.answer("Экспорт 👇", reply_markup=export_keyboard())
        except Exception as e:
            await message.answer(f"Ошибка GigaChat:\n{e}")

        cancel_flow(uid)
        return


# ========== Хэндлеры для Кредиторов/Должников ==========

@dp.callback_query(F.data.startswith("case:parties:"))
async def show_case_parties(call: CallbackQuery):
    """Показать список кредиторов/должников по делу."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    from bankrot_bot.database import get_session
    async with get_session() as session:
        parties = await get_case_parties(session, case_id)
        totals = calculate_parties_totals(parties)

        text = f"💰 Кредиторы и должники по делу #{case_id}\n\n"
        text += f"Кредиторов: {totals['creditors_count']}, сумма: {totals['total_creditors']:.2f} ₽\n"
        text += f"Должников: {totals['debtors_count']}, сумма: {totals['total_debtors']:.2f} ₽"

        await call.message.answer(
            text,
            reply_markup=case_parties_ikb(case_id, parties, totals['creditors_count'], totals['debtors_count'])
        )
    await call.answer()


@dp.callback_query(F.data.startswith("party:add_creditor:") | F.data.startswith("party:add_debtor:"))
async def start_add_party(call: CallbackQuery, state: FSMContext):
    """Начать добавление кредитора/должника."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    role = "creditor" if "creditor" in call.data else "debtor"
    case_id = int(parts[-1])

    await state.update_data(case_id=case_id, role=role)
    await state.set_state(AddParty.name)

    role_text = "кредитора" if role == "creditor" else "должника"
    await call.message.answer(f"Добавление {role_text}\n\nВведите наименование/ФИО:")
    await call.answer()


@dp.callback_query(F.data.startswith("party:view:"))
async def view_party(call: CallbackQuery):
    """Просмотр кредитора/должника."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    party_id = int(call.data.split(":")[-1])

    from bankrot_bot.database import get_session
    from bankrot_bot.models.case_party import CaseParty
    from sqlalchemy import select

    async with get_session() as session:
        stmt = select(CaseParty).where(CaseParty.id == party_id)
        result = await session.execute(stmt)
        party = result.scalar_one_or_none()

        if not party:
            await call.answer("Запись не найдена", show_alert=True)
            return

        role_text = "Кредитор" if party.role == "creditor" else "Должник"
        text = f"{role_text}\n\n"
        text += f"Наименование: {party.name}\n"
        text += f"Сумма: {float(party.amount):.2f} {party.currency}\n"
        if party.basis:
            text += f"Основание: {party.basis}\n"
        if party.notes:
            text += f"Примечания: {party.notes}\n"

        await call.message.answer(text, reply_markup=party_view_ikb(party_id, party.case_id))
    await call.answer()


@dp.callback_query(F.data.startswith("party:delete:"))
async def delete_party(call: CallbackQuery):
    """Удалить кредитора/должника."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    party_id = int(parts[2])
    case_id = int(parts[3])

    from bankrot_bot.database import get_session
    async with get_session() as session:
        success = await delete_case_party(session, party_id, case_id)
        await session.commit()

        if success:
            await call.message.answer("✅ Запись удалена")
        else:
            await call.answer("Ошибка удаления", show_alert=True)
    await call.answer()


# ========== Хэндлеры для Описи имущества ==========

@dp.callback_query(F.data.startswith("case:assets:"))
async def show_case_assets(call: CallbackQuery):
    """Показать опись имущества по делу."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    from bankrot_bot.database import get_session
    async with get_session() as session:
        assets = await get_case_assets(session, case_id)
        total = calculate_assets_total(assets)

        text = f"🏠 Опись имущества по делу #{case_id}\n\n"
        text += f"Записей: {len(assets)}\n"
        text += f"Общая стоимость: {float(total):.2f} ₽"

        await call.message.answer(
            text,
            reply_markup=case_assets_ikb(case_id, assets, float(total))
        )
    await call.answer()


@dp.callback_query(F.data.startswith("asset:add:"))
async def start_add_asset(call: CallbackQuery, state: FSMContext):
    """Начать добавление имущества."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])
    await state.update_data(case_id=case_id)
    await state.set_state(AddAsset.kind)

    await call.message.answer("Добавление имущества\n\nВведите вид имущества (например: квартира, автомобиль, акции):")
    await call.answer()


@dp.callback_query(F.data.startswith("asset:view:"))
async def view_asset(call: CallbackQuery):
    """Просмотр имущества."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    asset_id = int(call.data.split(":")[-1])

    from bankrot_bot.database import get_session
    from bankrot_bot.models.case_asset import CaseAsset
    from sqlalchemy import select

    async with get_session() as session:
        stmt = select(CaseAsset).where(CaseAsset.id == asset_id)
        result = await session.execute(stmt)
        asset = result.scalar_one_or_none()

        if not asset:
            await call.answer("Запись не найдена", show_alert=True)
            return

        text = f"🏠 {asset.kind}\n\n"
        text += f"Описание: {asset.description}\n"
        if asset.qty_or_area:
            text += f"Количество/площадь: {asset.qty_or_area}\n"
        if asset.value:
            text += f"Стоимость: {float(asset.value):.2f} ₽\n"
        if asset.notes:
            text += f"Примечания: {asset.notes}\n"

        await call.message.answer(text, reply_markup=asset_view_ikb(asset_id, asset.case_id))
    await call.answer()


@dp.callback_query(F.data.startswith("asset:delete:"))
async def delete_asset(call: CallbackQuery):
    """Удалить имущество."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    asset_id = int(parts[2])
    case_id = int(parts[3])

    from bankrot_bot.database import get_session
    async with get_session() as session:
        success = await delete_case_asset(session, asset_id, case_id)
        await session.commit()

        if success:
            await call.message.answer("✅ Запись удалена")
        else:
            await call.answer("Ошибка удаления", show_alert=True)
    await call.answer()


# ========== DOCX Generation Handlers ==========

@dp.callback_query(F.data.startswith("party:generate_doc:"))
async def generate_creditors_doc(call: CallbackQuery):
    """Генерация списка кредиторов и должников в DOCX."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    case_id = int(parts[2])

    await call.answer("Генерирую документ...")

    try:
        # Генерация DOCX из шаблона
        doc_bytes = await render_creditors_list(case_id)

        # Создание файла для отправки
        filename = f"creditors_list_case_{case_id}.docx"
        input_file = BufferedInputFile(doc_bytes, filename=filename)

        # Отправка документа пользователю
        await call.message.answer_document(
            input_file,
            caption="📄 Список кредиторов и должников"
        )
    except Exception as e:
        logger.error(f"Error generating creditors list: {e}", exc_info=True)
        await call.message.answer("❌ Ошибка при генерации документа. Проверьте, что вы заполнили профиль должника.")


@dp.callback_query(F.data.startswith("asset:generate_doc:"))
async def generate_inventory_doc(call: CallbackQuery):
    """Генерация описи имущества в DOCX."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":")
    case_id = int(parts[2])

    await call.answer("Генерирую документ...")

    try:
        # Генерация DOCX из шаблона
        doc_bytes = await render_inventory(case_id)

        # Создание файла для отправки
        filename = f"inventory_case_{case_id}.docx"
        input_file = BufferedInputFile(doc_bytes, filename=filename)

        # Отправка документа пользователю
        await call.message.answer_document(
            input_file,
            caption="📄 Опись имущества гражданина"
        )
    except Exception as e:
        logger.error(f"Error generating inventory: {e}", exc_info=True)
        await call.message.answer("❌ Ошибка при генерации документа. Проверьте, что вы заполнили профиль должника.")


# =========================
# Catch-all callback handler (must be AFTER all specific handlers)
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


async def main():
    import logging
    logger = logging.getLogger(__name__)

    # Initialize authorization module FIRST (breaks circular imports)
    init_allowed_users(ALLOWED_USERS, ADMIN_USERS)
    logger.info(f"Authorization initialized: {len(ALLOWED_USERS)} allowed users, {len(ADMIN_USERS)} admins")

    # Initialize old SQLite database for existing functionality
    init_db()
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://bankrot:bankrot_password@localhost:5432/bankrot")
    # Если есть engine = ... → engine = create_async_engine(database_url)
 
    # Initialize new PostgreSQL database for cases module
    await init_pg_db()
    logger.info("PostgreSQL database initialized")

    bot = Bot(token=BOT_TOKEN)

    # Execution mode: polling (default) or webhook
    mode = os.getenv('TELEGRAM_MODE', 'polling').strip().lower()

    if mode == 'polling':
        # POLLING MODE: Clear any existing webhook and start polling
        logger.info("=" * 60)
        logger.info("Bot starting in POLLING mode")
        logger.info("=" * 60)

        try:
            # Robustly delete any existing webhook
            logger.info("Deleting any existing webhook...")
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logger.warning(f"Found active webhook: {webhook_info.url}")
                logger.info("Removing webhook to enable polling...")

            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted successfully. Starting polling...")

            await dp.start_polling(bot)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            if "conflict" in str(e).lower():
                logger.error("TelegramConflictError detected!")
                logger.error("This usually means another bot instance is running or webhook is still active.")
                logger.error("Solutions:")
                logger.error("  1. Stop any other running bot instances")
                logger.error("  2. Manually delete webhook via: curl https://api.telegram.org/bot<TOKEN>/deleteWebhook")
                logger.error("  3. Wait a few minutes and try again")
            raise
        return

    if mode == 'webhook':
        # WEBHOOK MODE: FastAPI (web.py) receives updates and calls dp.feed_update(...)
        logger.info("=" * 60)
        logger.info("Bot starting in WEBHOOK mode")
        logger.info("=" * 60)

        # Initialize web app with dependencies (breaks circular import)
        from web import init_web_app
        init_web_app(BOT_TOKEN, dp)
        logger.info("Web app dependencies initialized")

        logger.info("Webhook updates handled by web.py (FastAPI)")
        logger.info("Start FastAPI server separately: uvicorn web:app --host 0.0.0.0 --port 8000")

        # Keep process alive if someone runs bot.py directly by mistake
        while True:
            await asyncio.sleep(3600)

    raise RuntimeError(f'Unknown TELEGRAM_MODE={mode!r}. Use polling|webhook')

if __name__ == "__main__":
    asyncio.run(main())
# =========================
# HOTFIX: unify main menu
# =========================
try:
    from bankrot_bot.keyboards.menus import main_menu_kb
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Failed to import main_menu_kb: {e}")
    main_menu_kb = None

def main_keyboard() -> InlineKeyboardMarkup:
    """
    Override legacy main_keyboard().
    Always return new unified menu with '➕ Создать дело'.
    """
    if main_menu_kb:
        return main_menu_kb()
    raise RuntimeError("main_menu_kb not available")
