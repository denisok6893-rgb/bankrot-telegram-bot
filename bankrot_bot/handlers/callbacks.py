"""Callback query handlers for bankruptcy bot."""
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bankrot_bot.services.public_docs import (
    get_docs_in_category,
    get_document,
    CATEGORY_TITLES,
)
from bankrot_bot.keyboards.menus import (
    docs_category_ikb,
    docs_item_ikb,
    case_card_ikb,
)
from bankrot_bot.shared import is_allowed  # ✓ Uses shared module (breaks circular import)

logger = logging.getLogger(__name__)

router = Router()


def get_generated_dir() -> Path:
    """Get GENERATED_DIR from bot.py."""
    from bot import GENERATED_DIR
    return GENERATED_DIR


# ========== DOCS section ==========

@router.callback_query(F.data.startswith("docs_cat:"))
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


@router.callback_query(F.data.startswith("docs_item:"))
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


# ========== CASE section ==========

@router.callback_query(F.data.startswith("case:open:"))
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

@router.callback_query(F.data.startswith("case:docs:"))
async def case_docs(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    # сохраним выбранное дело (на будущее)
    await state.update_data(docs_case_id=case_id)

    # показываем уже созданные файлы по делу (ТОЛЬКО новая структура)
    GENERATED_DIR = get_generated_dir()
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

@router.callback_query(F.data.startswith("case:lastdoc:"))
async def case_lastdoc_send(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])
    GENERATED_DIR = get_generated_dir()
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


@router.callback_query(F.data.startswith("case:archive:"))
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

    GENERATED_DIR = get_generated_dir()
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


@router.callback_query(F.data.startswith("case:fileidx:"))
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

    GENERATED_DIR = get_generated_dir()
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


@router.callback_query(F.data.startswith("case:file:"))
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

    GENERATED_DIR = get_generated_dir()
    case_dir = GENERATED_DIR / "cases" / str(case_id)
    path = case_dir / filename

    if not path.exists():
        await call.message.answer("Файл не найден (возможно, удалён).")
        await call.answer()
        return

    await call.message.answer_document(
        FSInputFile(path),
        caption=f"📄 Документ по делу #{case_id}",
    )
    await call.answer()

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("case:gen:"))
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

    # Import helper functions from bot.py
    from bot import get_case, get_case_card, validate_case_card, build_bankruptcy_petition_doc, _humanize_missing

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

@router.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 2)
async def case_edit_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    await state.clear()




    # --- EDIT MENU SHELL (no docs, no CaseCardFill) ---

    from bot import get_case
    import logging
    logger = logging.getLogger(__name__)

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


@router.callback_query(lambda c: c.data == "back:cases")
async def back_to_cases(call: CallbackQuery):
    from bankrot_bot.keyboards.menus import cases_menu_ikb
    await call.message.answer(
        "Раздел «Дела». Выбери действие:",
        reply_markup=cases_menu_ikb()
    )
    await call.answer()


@router.callback_query(lambda c: c.data == "case:new")
async def case_new(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    from bot import CaseCreate
    await state.clear()
    await state.set_state(CaseCreate.code_name)
    await call.message.answer("Введи кодовое название дела (например: ИВАНОВ_2025).")
    await call.answer()


@router.callback_query(lambda c: c.data == "case:list")
async def case_list(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    from bot import list_cases
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


@router.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_open(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    from bot import get_case_card
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


@router.callback_query(lambda c: c.data.startswith("case:card_edit:"))
async def case_card_edit(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    from bot import get_case, CASE_CARD_FIELD_META, CaseCardFill, send_creditors_menu

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


@router.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 3)
async def case_edit_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    from bot import get_case, CaseEdit

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
