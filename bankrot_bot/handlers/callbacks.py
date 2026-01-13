"""Callback query handlers for bankruptcy bot."""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bankrot_bot.services.public_docs import (
    get_docs_in_category,
    get_document,
    CATEGORY_TITLES,
)
from bankrot_bot.keyboards.menus import (
    docs_category_ikb,
    docs_item_ikb,
)

logger = logging.getLogger(__name__)

router = Router()


# Import is_allowed from bot.py for now
# TODO: Refactor to use proper auth middleware
def is_allowed(uid: int) -> bool:
    """Check if user is allowed to use the bot."""
    # This is a temporary import from bot.py
    # Will be refactored to use proper auth middleware
    from bot import is_allowed as bot_is_allowed
    return bot_is_allowed(uid)


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
