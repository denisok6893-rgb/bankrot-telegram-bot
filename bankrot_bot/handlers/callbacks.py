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

logger = logging.getLogger(__name__)

router = Router()


# Import is_allowed and GENERATED_DIR from bot.py for now
# TODO: Refactor to use proper auth middleware
def is_allowed(uid: int) -> bool:
    """Check if user is allowed to use the bot."""
    # This is a temporary import from bot.py
    # Will be refactored to use proper auth middleware
    from bot import is_allowed as bot_is_allowed
    return bot_is_allowed(uid)


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
