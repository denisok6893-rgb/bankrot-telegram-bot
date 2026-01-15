"""
Callback Query Handlers

This module contains all callback query handlers extracted from bot.py
Organized by functional categories for better maintainability.

Total handlers to extract: ~58 from bot.py
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Import keyboard builders from bot.py's keyboards module
from bankrot_bot.keyboards.menus import (
    home_ikb,
    profile_ikb,
    docs_catalog_ikb,
    help_ikb,
    help_item_ikb,
    my_cases_ikb,
)

# Import helper functions from bot.py
# NOTE: These should eventually be moved to utils module
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot import is_allowed, list_cases


# Create router for callback handlers
callback_router = Router(name="callbacks")


# ============================================================================
# MENU CALLBACKS (menu:*)
# ============================================================================

@callback_router.callback_query(F.data == "menu:home")
async def menu_home(call: CallbackQuery):
    """Navigate to home/main menu"""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("Главное меню:", reply_markup=home_ikb())
    await call.answer()


@callback_router.callback_query(F.data == "menu:profile")
async def menu_profile(call: CallbackQuery):
    """Show user profile"""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return
    await call.message.answer("👤 Мой профиль:", reply_markup=profile_ikb())
    await call.answer()


@callback_router.callback_query(F.data == "menu:docs")
async def menu_docs(call: CallbackQuery):
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


@callback_router.callback_query(F.data == "menu:help")
async def menu_help(call: CallbackQuery):
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


@callback_router.callback_query(F.data == "menu:my_cases")
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


# ============================================================================
# HELP CALLBACKS (help:*)
# ============================================================================

@callback_router.callback_query(F.data == "help:howto")
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


@callback_router.callback_query(F.data == "help:cases")
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


@callback_router.callback_query(F.data == "help:docs")
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


@callback_router.callback_query(F.data == "help:contacts")
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


@callback_router.callback_query(F.data == "help:about")
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


# ============================================================================
# DOCUMENTS CALLBACKS (docs_cat:*, docs_item:*)
# ============================================================================

@callback_router.callback_query(F.data.startswith("docs_cat:"))
async def docs_category(call: CallbackQuery):
    """Handle document category selection"""
    # TODO: Extract from bot.py:1698
    category = call.data.split(":")[-1]
    await call.answer()
    # Show documents in category


@callback_router.callback_query(F.data.startswith("docs_item:"))
async def docs_item(call: CallbackQuery):
    """Handle document item selection"""
    # TODO: Extract from bot.py:1720
    parts = call.data.split(":")
    await call.answer()
    # Handle document selection


# ============================================================================
# PROFILE CALLBACKS (profile:*)
# ============================================================================

@callback_router.callback_query(F.data == "profile:cases")
async def profile_cases(call: CallbackQuery):
    """Show cases in profile"""
    # TODO: Extract from bot.py:1749
    await call.answer()


# ============================================================================
# CASE MANAGEMENT CALLBACKS (case:*)
# ============================================================================

@callback_router.callback_query(F.data.startswith("case:open:"))
async def case_open(call: CallbackQuery):
    """Open and display a specific case"""
    # TODO: Extract from bot.py:1766
    case_id = int(call.data.split(":")[-1])
    await call.answer()
    # Load and display case


@callback_router.callback_query(F.data.startswith("case:docs:"))
async def case_docs(call: CallbackQuery, state: FSMContext):
    """Show documents for a case"""
    # TODO: Extract from bot.py:1780
    case_id = int(call.data.split(":")[-1])
    await call.answer()


@callback_router.callback_query(F.data.startswith("case:lastdoc:"))
async def case_lastdoc_send(call: CallbackQuery):
    """Send the last generated document for a case"""
    # TODO: Extract from bot.py:1828
    case_id = int(call.data.split(":")[-1])
    await call.answer()


@callback_router.callback_query(F.data.startswith("case:archive:"))
async def case_archive(call: CallbackQuery):
    """Archive/unarchive a case"""
    # TODO: Extract from bot.py:1861
    parts = call.data.split(":")
    await call.answer()


@callback_router.callback_query(F.data.startswith("case:fileidx:"))
async def case_file_send_by_index(call: CallbackQuery):
    """Send a file from case by index"""
    # TODO: Extract from bot.py:1922
    parts = call.data.split(":")
    await call.answer()


@callback_router.callback_query(F.data.startswith("case:file:"))
async def case_file_send(call: CallbackQuery):
    """Send a specific case file"""
    # TODO: Extract from bot.py:1965
    parts = call.data.split(":", 3)
    await call.answer()


@callback_router.callback_query(F.data.startswith("case:gen:"))
async def case_generate_document(call: CallbackQuery):
    """Generate a document for a case"""
    # TODO: Extract from bot.py:2004+
    await call.answer()


# ============================================================================
# AI & MISC CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data == "ai:placeholder")
async def ai_placeholder(call: CallbackQuery):
    """AI feature placeholder"""
    # TODO: Extract from bot.py:1553
    await call.answer("Эта функция появится в следующей версии!", show_alert=True)


@callback_router.callback_query(F.data == "noop")
async def noop_callback(call: CallbackQuery):
    """No-operation callback (for disabled buttons)"""
    # TODO: Extract from bot.py:2000
    await call.answer()


# ============================================================================
# ADDITIONAL HANDLERS TO EXTRACT
# ============================================================================
# - case:status:* handlers
# - case:edit:* handlers
# - case:delete:* handlers
# - case:party:* handlers (AddParty FSM)
# - case:asset:* handlers (AddAsset FSM)
# - case:debt:* handlers (AddDebt FSM)
# - doc:generate:* handlers
# - And ~28 more handlers from bot.py


def register_callbacks(dp):
    """
    Register all callback handlers with the dispatcher

    Usage in bot.py:
        from handlers.callbacks import register_callbacks
        register_callbacks(dp)

    NOTE: Router registration removed to prevent "Router is already attached" error.
    Routers are now registered directly in bot.py.
    """
    pass
