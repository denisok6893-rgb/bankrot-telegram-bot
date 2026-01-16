"""
Refactored Callback Query Handlers

This module contains all callback query handlers for the bankrot-telegram-bot.
All handlers use edit_message_text to avoid chat spam.
All keyboards use InlineKeyboardMarkup with consistent "← Back" navigation.

Callback Structure:
- main: Main menu
- profile: Profile menu
- profile_data, profile_edit, profile_stats: Profile actions
- my_cases: My cases list
- new_case: Start new case FSM
- case_open:<id>: Open case card
- case_parties:<id>, case_assets:<id>, case_docs:<id>: Case sections
- help, help_*: Help menu items
- docs_catalog, docs_cat:*, docs_item:*: Documents catalog
"""

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

# Import keyboards from the new refactored module
from keyboards import (
    main_menu,
    profile_menu,
    my_cases_menu,
    case_card_menu,
    case_parties_menu,
    case_assets_menu,
    case_docs_menu,
    docs_catalog_menu,
    docs_category_menu,
    docs_item_menu,
    help_menu,
    help_item_menu,
    back_to_main,
)

# Import helper functions
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bankrot_bot.shared import is_allowed
from bankrot_bot.services.cases_db import list_cases, get_case

logger = logging.getLogger(__name__)

# Create router with priority
callback_router = Router(name="callbacks")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

async def safe_edit_message(
    call: CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode: Optional[str] = None
) -> bool:
    """
    Safely edit message text, handling exceptions.

    Returns:
        True if edit was successful, False otherwise
    """
    try:
        await call.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except TelegramBadRequest as e:
        # Message is not modified (same content)
        if "message is not modified" in str(e).lower():
            logger.debug(f"Message not modified for user {call.from_user.id}")
            return True
        # Message to edit not found
        elif "message to edit not found" in str(e).lower():
            logger.warning(f"Message not found for user {call.from_user.id}")
            await call.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        else:
            logger.error(f"Failed to edit message: {e}")
            return False
    except Exception as e:
        logger.error(f"Unexpected error editing message: {e}")
        return False


# ============================================================================
# MAIN MENU CALLBACK
# ============================================================================

@callback_router.callback_query(F.data == "main")
async def handle_main_menu(call: CallbackQuery):
    """
    Navigate to main menu.
    This is the central hub for all "← Back" buttons.
    """
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "🏠 Главное меню\n\n"
        "Выберите раздел для работы:"
    )

    await safe_edit_message(call, text, reply_markup=main_menu())
    await call.answer()


# ============================================================================
# PROFILE CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data == "profile")
async def handle_profile(call: CallbackQuery):
    """Show profile menu."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "👤 Мой профиль\n\n"
        "Управление вашим профилем и персональными данными."
    )

    await safe_edit_message(call, text, reply_markup=profile_menu())
    await call.answer()


@callback_router.callback_query(F.data == "profile_data")
async def handle_profile_data(call: CallbackQuery):
    """Show profile data."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    # TODO: Fetch real profile data from database
    text = (
        "📋 Данные профиля\n\n"
        f"Telegram ID: {uid}\n"
        f"Имя: {call.from_user.full_name}\n"
        f"Username: @{call.from_user.username or 'не указан'}\n\n"
        "Для изменения данных используйте кнопку 'Редактировать'."
    )

    await safe_edit_message(call, text, reply_markup=profile_menu())
    await call.answer()


@callback_router.callback_query(F.data == "profile_edit")
async def handle_profile_edit(call: CallbackQuery):
    """Edit profile (placeholder)."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "✏️ Редактирование профиля\n\n"
        "Эта функция находится в разработке.\n"
        "Скоро вы сможете редактировать свои данные."
    )

    await safe_edit_message(call, text, reply_markup=profile_menu())
    await call.answer()


@callback_router.callback_query(F.data == "profile_stats")
async def handle_profile_stats(call: CallbackQuery):
    """Show profile statistics."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    # TODO: Calculate real statistics
    cases = list_cases(uid)
    cases_count = len(cases)

    text = (
        "📊 Статистика\n\n"
        f"Всего дел: {cases_count}\n"
        f"Активных дел: {cases_count}\n"
        f"Завершенных дел: 0\n\n"
        "Подробная статистика появится в следующей версии."
    )

    await safe_edit_message(call, text, reply_markup=profile_menu())
    await call.answer()


# ============================================================================
# MY CASES CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data == "my_cases")
async def handle_my_cases(call: CallbackQuery, state: FSMContext):
    """Show my cases list."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    # Fetch cases from database
    rows = list_cases(uid)

    # Get active case from state
    data = await state.get_data()
    active_case_id = data.get("active_case_id")

    # Format cases for keyboard
    cases = [(row[0], row[1] or f"Дело #{row[0]}") for row in rows]

    text = "📋 Мои дела\n\n"
    if cases:
        text += f"У вас {len(cases)} дел(а/о).\n"
        if active_case_id:
            text += f"Активное дело: #{active_case_id}\n\n"
        text += "Выберите дело для работы или создайте новое."
    else:
        text += "У вас пока нет дел.\nНажмите '➕ Новое дело' для создания первого дела."

    await safe_edit_message(call, text, reply_markup=my_cases_menu(cases, active_case_id))
    await call.answer()


@callback_router.callback_query(F.data.startswith("case_open:"))
async def handle_case_open(call: CallbackQuery, state: FSMContext):
    """Open case card."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    try:
        case_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка: неверный ID дела", show_alert=True)
        return

    # Fetch case from database
    case = get_case(case_id)
    if not case or case.get("user_id") != uid:
        await call.answer("Дело не найдено", show_alert=True)
        return

    # Set as active case
    await state.update_data(active_case_id=case_id)

    # Format case info
    case_title = case.get("code_name") or f"Дело #{case_id}"
    case_number = case.get("case_number") or "не указан"
    court = case.get("court") or "не указан"

    text = (
        f"📁 {case_title}\n\n"
        f"Номер дела: {case_number}\n"
        f"Суд: {court}\n\n"
        "Выберите действие:"
    )

    await safe_edit_message(call, text, reply_markup=case_card_menu(case_id))
    await call.answer()


# ============================================================================
# CASE SECTIONS CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data.startswith("case_parties:"))
async def handle_case_parties(call: CallbackQuery):
    """Show case parties (creditors/debtors)."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    try:
        case_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка: неверный ID дела", show_alert=True)
        return

    # TODO: Fetch parties from database
    text = (
        f"💰 Кредиторы/должники\n\n"
        f"Дело #{case_id}\n\n"
        "Здесь будет список кредиторов и должников.\n"
        "Функция в разработке."
    )

    await safe_edit_message(call, text, reply_markup=case_parties_menu(case_id, [], 0, 0))
    await call.answer()


@callback_router.callback_query(F.data.startswith("case_assets:"))
async def handle_case_assets(call: CallbackQuery):
    """Show case assets (inventory)."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    try:
        case_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка: неверный ID дела", show_alert=True)
        return

    # TODO: Fetch assets from database
    text = (
        f"🏠 Опись имущества\n\n"
        f"Дело #{case_id}\n\n"
        "Здесь будет список имущества.\n"
        "Функция в разработке."
    )

    await safe_edit_message(call, text, reply_markup=case_assets_menu(case_id, [], 0.0))
    await call.answer()


@callback_router.callback_query(F.data.startswith("case_docs:"))
async def handle_case_docs(call: CallbackQuery):
    """Show case documents."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    try:
        case_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка: неверный ID дела", show_alert=True)
        return

    text = (
        f"📎 Документы по делу\n\n"
        f"Дело #{case_id}\n\n"
        "Генерация и управление документами."
    )

    await safe_edit_message(call, text, reply_markup=case_docs_menu(case_id))
    await call.answer()


@callback_router.callback_query(F.data.startswith("case_edit:"))
async def handle_case_edit(call: CallbackQuery):
    """Edit case (placeholder)."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    await call.answer("Редактирование дела - функция в разработке", show_alert=True)


@callback_router.callback_query(F.data.startswith("case_help:"))
async def handle_case_help(call: CallbackQuery):
    """Case AI help (placeholder)."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    await call.answer("ИИ-помощник - функция в разработке", show_alert=True)


# ============================================================================
# HELP MENU CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data == "help")
async def handle_help(call: CallbackQuery):
    """Show help menu."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "❓ Раздел помощи\n\n"
        "Выберите интересующую тему:"
    )

    await safe_edit_message(call, text, reply_markup=help_menu())
    await call.answer()


@callback_router.callback_query(F.data == "help_howto")
async def handle_help_howto(call: CallbackQuery):
    """How to use the bot."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "📖 Как пользоваться ботом\n\n"
        "1️⃣ Главное меню\n"
        "• Мой профиль - управление данными\n"
        "• Новое дело - создать дело о банкротстве\n"
        "• Мои дела - список ваших дел\n\n"
        "2️⃣ Работа с делами\n"
        "• Создайте карточку дела\n"
        "• Заполните данные кредиторов\n"
        "• Генерируйте документы\n\n"
        "3️⃣ Навигация\n"
        "Кнопка '← Назад' всегда возвращает в главное меню."
    )

    await safe_edit_message(call, text, reply_markup=help_item_menu())
    await call.answer()


@callback_router.callback_query(F.data == "help_cases")
async def handle_help_cases(call: CallbackQuery):
    """What are case cards."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "📋 Карточки дел\n\n"
        "Карточка дела - структурированное хранилище информации "
        "по конкретному делу о банкротстве.\n\n"
        "Что хранится:\n"
        "• Данные должника (ФИО, адрес)\n"
        "• Информация о кредиторах\n"
        "• Сумма задолженности\n"
        "• Документы по делу\n\n"
        "На основе карточки бот генерирует юридические документы."
    )

    await safe_edit_message(call, text, reply_markup=help_item_menu())
    await call.answer()


@callback_router.callback_query(F.data == "help_docs")
async def handle_help_docs(call: CallbackQuery):
    """About documents."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "📄 О документах\n\n"
        "Бот работает с документами:\n\n"
        "1️⃣ Публичный каталог\n"
        "Образцы документов для всех пользователей\n\n"
        "2️⃣ Документы по делу\n"
        "Генерируются на основе данных вашей карточки\n\n"
        "Все документы формируются в формате DOCX."
    )

    await safe_edit_message(call, text, reply_markup=help_item_menu())
    await call.answer()


@callback_router.callback_query(F.data == "help_contacts")
async def handle_help_contacts(call: CallbackQuery):
    """Contacts and feedback."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "✉️ Контакты и обратная связь\n\n"
        "По всем вопросам работы бота:\n"
        "• Сообщите об ошибке\n"
        "• Предложите улучшение\n"
        "• Задайте вопрос\n\n"
        "📧 Email: support@example.com\n"
        "💬 Telegram: @support_username"
    )

    await safe_edit_message(call, text, reply_markup=help_item_menu())
    await call.answer()


@callback_router.callback_query(F.data == "help_about")
async def handle_help_about(call: CallbackQuery):
    """About the bot."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "ℹ️ О боте\n\n"
        "Telegram-бот помощник по банкротству физических лиц.\n\n"
        "Возможности:\n"
        "• Управление карточками дел\n"
        "• Генерация юридических документов\n"
        "• Каталог образцов документов\n"
        "• Справочная информация\n\n"
        "Версия: 2.0.0 (Refactored)\n"
        "Статус: В разработке"
    )

    await safe_edit_message(call, text, reply_markup=help_item_menu())
    await call.answer()


# ============================================================================
# DOCUMENTS CATALOG CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data == "docs_catalog")
async def handle_docs_catalog(call: CallbackQuery):
    """Show public documents catalog."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    text = (
        "📄 Публичный каталог документов\n\n"
        "Здесь вы найдете шаблоны и образцы документов для банкротства.\n"
        "Выберите категорию:"
    )

    await safe_edit_message(call, text, reply_markup=docs_catalog_menu())
    await call.answer()


@callback_router.callback_query(F.data.startswith("docs_cat:"))
async def handle_docs_category(call: CallbackQuery):
    """Show documents in category."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    category = call.data.split(":")[1]

    # TODO: Fetch documents from database
    text = (
        f"📋 Категория: {category}\n\n"
        "Документы в этой категории.\n"
        "Функция в разработке."
    )

    await safe_edit_message(call, text, reply_markup=docs_category_menu(category, []))
    await call.answer()


@callback_router.callback_query(F.data.startswith("docs_item:"))
async def handle_docs_item(call: CallbackQuery):
    """Show document item."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    parts = call.data.split(":")
    category = parts[1]
    doc_id = parts[2] if len(parts) > 2 else "unknown"

    text = (
        f"📄 Документ: {doc_id}\n\n"
        "Содержимое документа.\n"
        "Функция в разработке."
    )

    await safe_edit_message(call, text, reply_markup=docs_item_menu(category))
    await call.answer()


# ============================================================================
# FSM CONTROL CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data == "cancel_fsm")
async def handle_cancel_fsm(call: CallbackQuery, state: FSMContext):
    """Cancel any active FSM state."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer("Доступ запрещен", show_alert=True)
        return

    # Clear FSM state
    await state.clear()

    text = (
        "❌ Операция отменена\n\n"
        "Вы вернулись в главное меню."
    )

    await safe_edit_message(call, text, reply_markup=main_menu())
    await call.answer("Отменено")


@callback_router.callback_query(F.data == "skip_step")
async def handle_skip_step(call: CallbackQuery):
    """
    Skip optional FSM step.
    This is handled by the FSM handlers themselves.
    """
    await call.answer("Шаг пропущен")


# ============================================================================
# UTILITY CALLBACKS
# ============================================================================

@callback_router.callback_query(F.data == "noop")
async def handle_noop(call: CallbackQuery):
    """No-operation callback (for disabled buttons)."""
    await call.answer()


# ============================================================================
# REGISTRATION FUNCTION
# ============================================================================

def register_callbacks(dp):
    """
    Register callback router with dispatcher.

    Note: This function is kept for backward compatibility.
    Router can be included directly in bot.py:
        from handlers.callbacks import callback_router
        dp.include_router(callback_router)
    """
    dp.include_router(callback_router)
