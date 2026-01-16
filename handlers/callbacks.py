"""
Callback Handlers - Phase 8, 9, 10, 11, 12, 13, 14, 15, 16
Migrated from bot.py to modular handlers.

Phase 8-9: CASE callbacks (9 handlers) ✅
Phase 10: PROFILE & AI/MISC callbacks (5 handlers) ✅
Phase 11: NAVIGATION & DOCS callbacks (5 handlers) ✅
Phase 12: DOCS/FSM callbacks (6 handlers) ✅
Phase 13: CREDITORS/FSM + MENU callbacks (6 handlers) ✅
Phase 14: PARTY/ASSET callbacks (6 handlers) ✅
Phase 15: ASSET/DOC/ARCHIVE callbacks (5 handlers) ✅
Phase 16: HELP callbacks (5 handlers) ✅

Total: 47 callbacks migrated (81% of ~58 total) 🎉 80% MILESTONE!

Type Hints: Added comprehensive type hints to all 47 handlers for IDE support and mypy validation.
"""

import logging
from typing import Any
from pathlib import Path

# Aiogram imports
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, FSInputFile, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

# FSM States - import from bot.py where they are defined
from bot import (
    CaseEdit,
    AddParty,
    AddAsset,
    CaseCardFill,
    ProfileFill,
    CreditorsFill,
    CaseCreate,
    # Helper functions
    build_bankruptcy_petition_doc,
    _selected_case_id,
    _card_completion_status,
    _format_creditor_line,
    send_card_fill_menu,
    send_creditors_menu,
    # Constants
    CASE_CARD_FIELD_META,
    CASE_CARD_FIELDS,
    GENERATED_DIR,
)

# Authorization
from bankrot_bot.shared import is_allowed

# Database functions
from bankrot_bot.services.cases_db import (
    list_cases,
    get_case,
    get_profile,
    get_case_card,
    update_case_fields,
    update_case_meta,
    upsert_case_card,
    validate_case_card,
)

# Service functions for parties and assets
from bankrot_bot.services.case_financials import (
    get_case_parties,
    delete_case_party,
    get_case_assets,
    calculate_assets_total,
)

# Document generation
from bankrot_bot.services.docx_forms import (
    render_creditors_list,
    render_inventory,
)

# Keyboard functions
from bankrot_bot.keyboards.menus import (
    main_menu_kb,
    home_ikb,
    profile_ikb,
    docs_menu_ikb,
    cases_menu_ikb,
    docs_catalog_ikb,
    help_ikb,
    help_item_ikb,
    party_view_ikb,
    case_assets_ikb,
    asset_view_ikb,
)

logger = logging.getLogger(__name__)

# Create router for callback handlers
callback_router = Router(name="callbacks")

# ============================================================================
# CASE CALLBACKS - COMPLETE (9 callbacks total)
# Phase 8-9
# ============================================================================

# Lines 2072-2166 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 2)
async def case_edit_menu(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 2347-2373 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:file:"))
async def case_file_send(call: CallbackQuery) -> None:
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


# Lines 2694-2735 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:open:"))
async def case_open(call: CallbackQuery) -> None:
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


# Lines 2738-2773 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_open(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3037-3048 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_menu(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.clear()
    await state.update_data(card_case_id=cid)
    await send_card_fill_menu(call.message, uid, cid)
    await call.answer()


# Lines 3050-3085 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:card_edit:"))
async def case_card_edit(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3127-3155 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:cardfield:"))
async def card_field_start(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3312-3324 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:creditors:"))
async def creditors_menu(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.clear()
    await state.update_data(card_case_id=cid)

    await send_creditors_menu(call.message, uid, cid)
    await call.answer()


# Lines 3591-3631 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 3)
async def case_edit_start(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3632-3682 from bot.py (FSM handler for case_edit_start)
@callback_router.message(CaseEdit.value)
async def case_edit_apply(message: Message, state: FSMContext) -> None:
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


# ============================================================================
# PROFILE CALLBACKS (profile:*)
# Phase 10
# ============================================================================

# Lines 2198-2227 from bot.py
@callback_router.callback_query(lambda c: c.data == "profile:menu")
async def profile_menu(call: CallbackQuery) -> None:
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


# Lines 2228-2238 from bot.py
@callback_router.callback_query(lambda c: c.data == "profile:edit")
async def profile_edit_start(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await state.clear()
    await state.set_state(ProfileFill.full_name)
    await call.message.answer("Введи ФИО или название организации (как будет в документах).")
    await call.answer()


# ============================================================================
# AI & MISC CALLBACKS
# Phase 10
# ============================================================================

# Lines 1552-1560 from bot.py
@callback_router.callback_query(F.data == "ai:placeholder")
async def ai_placeholder(call: CallbackQuery) -> None:
    """Заглушка для ИИ-помощника."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await call.answer("🤖 ИИ-помощник в разработке. Скоро будет доступен!", show_alert=True)


# Lines 1999-2001 from bot.py
@callback_router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery) -> None:
    await call.answer()


# Lines 2385-2388 from bot.py
@callback_router.callback_query(lambda c: c.data == "back:main")
async def back_to_main(call: CallbackQuery) -> None:
    await call.message.answer("Главное меню 👇", reply_markup=main_menu_kb())
    await call.answer()


# ============================================================================
# NAVIGATION CALLBACKS (case:list, case:new, back:*)
# Phase 11
# ============================================================================

# Lines 2458-2468 from bot.py
@callback_router.callback_query(lambda c: c.data == "case:new")
async def case_new(call: CallbackQuery, state: FSMContext) -> None:
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await state.clear()
    await state.set_state(CaseCreate.code_name)
    await call.message.answer("Введи кодовое название дела (например: ИВАНОВ_2025).")
    await call.answer()


# Lines 2657-2684 from bot.py
@callback_router.callback_query(lambda c: c.data == "case:list")
async def case_list(call: CallbackQuery) -> None:
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


# Lines 2686-2692 from bot.py
@callback_router.callback_query(lambda c: c.data == "back:cases")
async def back_to_cases(call: CallbackQuery) -> None:
    await call.message.answer(
        "Раздел «Дела». Выбери действие:",
        reply_markup=cases_menu_ikb()
    )
    await call.answer()


# ============================================================================
# DOCS CALLBACKS (docs:back_menu, docs:choose_case)
# Phase 11
# ============================================================================

# Lines 2376-2380 from bot.py
@callback_router.callback_query(lambda c: c.data == "docs:back_menu")
async def docs_back_menu(call: CallbackQuery, state: FSMContext) -> None:
    cid = await _selected_case_id(state)
    await call.message.answer("Документы: выбери действие 👇", reply_markup=docs_menu_ikb(cid))
    await call.answer()


# Lines 2241-2266 from bot.py
@callback_router.callback_query(lambda c: c.data == "docs:choose_case")
async def docs_choose_case(call: CallbackQuery) -> None:
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


# ============================================================================
# DOCS/FSM CALLBACKS (docs:case:*, docs:petition:*, card:fill:*, creditors:*)
# Phase 12
# ============================================================================

# Lines 2269-2288 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("docs:case:"))
async def docs_case_selected(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 2290-2345 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("docs:petition:"))
async def docs_petition(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3086-3125 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("card:fill:"))
async def card_fill_start(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3327-3339 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("creditors:add:"))
async def creditors_add_start(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3342-3366 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("creditors:del:"))
async def creditors_delete_menu(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3369-3396 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("creditors:delone:"))
async def creditors_delete_one(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3399-3412 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("creditors:text_clear:"))
async def creditors_text_clear(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3415-3432 from bot.py
@callback_router.callback_query(lambda c: c.data.startswith("creditors:text:"))
async def creditors_text_start(call: CallbackQuery, state: FSMContext) -> None:
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


# ============================================================================
# MENU CALLBACKS (menu:home, menu:profile, menu:docs, menu:help)
# Phase 13
# ============================================================================

# Lines 1472-1479 from bot.py
@callback_router.callback_query(F.data == "menu:home")
async def menu_home(call: CallbackQuery) -> None:
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("Главное меню:", reply_markup=home_ikb())
    await call.answer()


# Lines 1482-1489 from bot.py
@callback_router.callback_query(F.data == "menu:profile")
async def menu_profile(call: CallbackQuery) -> None:
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("👤 Мой профиль:", reply_markup=profile_ikb())
    await call.answer()


# Lines 1492-1505 from bot.py
@callback_router.callback_query(F.data == "menu:docs")
async def menu_docs(call: CallbackQuery) -> None:
    """Публичный каталог документов - доступен всем."""
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


# Lines 1508-1520 from bot.py
@callback_router.callback_query(F.data == "menu:help")
async def menu_help(call: CallbackQuery) -> None:
    """Подменю раздела Помощь."""
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


# ============================================================================
# PARTY/ASSET CALLBACKS (party:*, asset:*, case:assets:*)
# Phase 14
# ============================================================================

# Lines 3935-3952 from bot.py
@callback_router.callback_query(F.data.startswith("party:add_creditor:") | F.data.startswith("party:add_debtor:"))
async def start_add_party(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 3955-3988 from bot.py
@callback_router.callback_query(F.data.startswith("party:view:"))
async def view_party(call: CallbackQuery) -> None:
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


# Lines 3991-4012 from bot.py
@callback_router.callback_query(F.data.startswith("party:delete:"))
async def delete_party(call: CallbackQuery) -> None:
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


# Lines 4017-4040 from bot.py
@callback_router.callback_query(F.data.startswith("case:assets:"))
async def show_case_assets(call: CallbackQuery) -> None:
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


# Lines 4043-4056 from bot.py
@callback_router.callback_query(F.data.startswith("asset:add:"))
async def start_add_asset(call: CallbackQuery, state: FSMContext) -> None:
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


# Lines 4059-4092 from bot.py
@callback_router.callback_query(F.data.startswith("asset:view:"))
async def view_asset(call: CallbackQuery) -> None:
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


# Lines 4095-4116 from bot.py
@callback_router.callback_query(F.data.startswith("asset:delete:"))
async def delete_asset(call: CallbackQuery) -> None:
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


# ============================================================================
# ASSET/DOC/ARCHIVE CALLBACKS (asset:delete, party/asset:generate_doc, case:archive, case:fileidx)
# Phase 15
# ============================================================================

# Lines 4121-4149 from bot.py
@callback_router.callback_query(F.data.startswith("party:generate_doc:"))
async def generate_creditors_doc(call: CallbackQuery) -> None:
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


# Lines 4152-4180 from bot.py
@callback_router.callback_query(F.data.startswith("asset:generate_doc:"))
async def generate_inventory_doc(call: CallbackQuery) -> None:
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


# Lines 1860-1918 from bot.py
@callback_router.callback_query(F.data.startswith("case:archive:"))
async def case_archive(call: CallbackQuery) -> None:
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


# Lines 1921-1962 from bot.py
@callback_router.callback_query(F.data.startswith("case:fileidx:"))
async def case_file_send_by_index(call: CallbackQuery) -> None:
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


# ============================================================================
# HELP CALLBACKS (help:howto, help:cases, help:docs, help:contacts, help:about)
# Phase 16
# ============================================================================

# Lines 1565-1590 from bot.py
@callback_router.callback_query(F.data == "help:howto")
async def help_howto(call: CallbackQuery) -> None:
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


# Lines 1593-1616 from bot.py
@callback_router.callback_query(F.data == "help:cases")
async def help_cases(call: CallbackQuery) -> None:
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


# Lines 1619-1642 from bot.py
@callback_router.callback_query(F.data == "help:docs")
async def help_docs(call: CallbackQuery) -> None:
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


# Lines 1645-1666 from bot.py
@callback_router.callback_query(F.data == "help:contacts")
async def help_contacts(call: CallbackQuery) -> None:
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


# Lines 1669-1692 from bot.py
@callback_router.callback_query(F.data == "help:about")
async def help_about(call: CallbackQuery) -> None:
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
