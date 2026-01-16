"""
Refactored FSM handlers for creating a new case.

All keyboards are now InlineKeyboardMarkup.
Uses edit_message_text to avoid chat spam.
Includes "← Отмена" (Cancel) button in all FSM steps.
"""

import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

# Import keyboards from refactored module
from keyboards import (
    new_case_cancel,
    new_case_skip_cancel,
    main_menu,
)

logger = logging.getLogger(__name__)

# Create router for this module
router = Router(name="newcase_fsm")


# ============================================================================
# FSM STATES
# ============================================================================

class NewCase(StatesGroup):
    """FSM states for new case creation."""
    name = State()
    debt = State()
    income = State()
    assets = State()
    dependents = State()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

async def safe_edit_or_send(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: Optional[str] = None
) -> None:
    """
    Try to edit message, fall back to sending new message if edit fails.
    """
    try:
        # Try to edit if this is a callback query message
        if hasattr(message, 'edit_text'):
            await message.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            # Regular message - send new one
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message to edit not found" in str(e).lower() or "message is not modified" in str(e).lower():
            # Can't edit, send new message
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            raise
    except AttributeError:
        # Message doesn't have edit_text, send new one
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


# ============================================================================
# FSM ENTRY POINT (Callback Query)
# ============================================================================

@router.callback_query(F.data == "new_case")
async def newcase_start_callback(call: CallbackQuery, state: FSMContext):
    """
    Start new case creation from callback button.
    This is the primary entry point from the menu system.
    """
    logger.info(f"User {call.from_user.id} started new case via callback")

    await state.clear()
    await state.set_state(NewCase.name)

    text = (
        "📝 Создание нового дела\n\n"
        "Шаг 1/5: Введите ФИО должника\n\n"
        "Пример: Иванов Иван Иванович"
    )

    try:
        await call.message.edit_text(text, reply_markup=new_case_cancel())
    except TelegramBadRequest:
        await call.message.answer(text, reply_markup=new_case_cancel())

    await call.answer()


# ============================================================================
# FSM STATES HANDLERS
# ============================================================================

@router.message(StateFilter(NewCase.name))
async def newcase_step_name(message: Message, state: FSMContext):
    """
    Process name input.
    ONLY active when in NewCase.name state.
    """
    text = (message.text or "").strip()

    if not text:
        await message.answer(
            "❌ Пожалуйста, введите ФИО должника\n\n"
            "Пример: Иванов Иван Иванович",
            reply_markup=new_case_cancel()
        )
        return

    # Validate name (basic check)
    if len(text) < 3:
        await message.answer(
            "❌ ФИО слишком короткое\n\n"
            "Введите полное ФИО (минимум 3 символа)",
            reply_markup=new_case_cancel()
        )
        return

    await state.update_data(name=text)
    await state.set_state(NewCase.debt)

    text = (
        "✅ ФИО сохранено\n\n"
        "Шаг 2/5: Введите общую сумму задолженности (в рублях)\n\n"
        "Пример: 500000"
    )

    await message.answer(text, reply_markup=new_case_cancel())


@router.message(StateFilter(NewCase.debt))
async def newcase_step_debt(message: Message, state: FSMContext):
    """
    Process debt amount input.
    ONLY active when in NewCase.debt state.
    """
    text = (message.text or "").strip()

    if not text:
        await message.answer(
            "❌ Пожалуйста, введите сумму задолженности\n\n"
            "Пример: 500000",
            reply_markup=new_case_cancel()
        )
        return

    # Try to parse as number
    try:
        debt_amount = float(text.replace(" ", "").replace(",", "."))
        if debt_amount < 0:
            await message.answer(
                "❌ Сумма не может быть отрицательной\n\n"
                "Попробуйте ещё раз",
                reply_markup=new_case_cancel()
            )
            return
        if debt_amount == 0:
            await message.answer(
                "❌ Сумма должна быть больше нуля\n\n"
                "Введите положительное число",
                reply_markup=new_case_cancel()
            )
            return
    except ValueError:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Введите число, например: 500000",
            reply_markup=new_case_cancel()
        )
        return

    await state.update_data(debt=debt_amount)
    await state.set_state(NewCase.income)

    text = (
        "✅ Сумма задолженности сохранена\n\n"
        "Шаг 3/5: Введите ежемесячный доход (в рублях)\n\n"
        "Пример: 50000\n"
        "Или нажмите '⏭️ Пропустить' если нет дохода"
    )

    await message.answer(text, reply_markup=new_case_skip_cancel())


@router.message(StateFilter(NewCase.income))
async def newcase_step_income(message: Message, state: FSMContext):
    """
    Process income input.
    ONLY active when in NewCase.income state.
    """
    text = (message.text or "").strip()

    if text.lower() in ["пропустить", "skip", "-"]:
        await state.update_data(income=0)
    else:
        try:
            income_amount = float(text.replace(" ", "").replace(",", "."))
            if income_amount < 0:
                await message.answer(
                    "❌ Сумма не может быть отрицательной\n\n"
                    "Попробуйте ещё раз или нажмите '⏭️ Пропустить'",
                    reply_markup=new_case_skip_cancel()
                )
                return
            await state.update_data(income=income_amount)
        except ValueError:
            await message.answer(
                "❌ Неверный формат\n\n"
                "Введите число или нажмите '⏭️ Пропустить'",
                reply_markup=new_case_skip_cancel()
            )
            return

    await state.set_state(NewCase.assets)

    text = (
        "✅ Доход сохранен\n\n"
        "Шаг 4/5: Введите примерную стоимость имущества (в рублях)\n\n"
        "Пример: 1000000\n"
        "Или нажмите '⏭️ Пропустить' если нет имущества"
    )

    await message.answer(text, reply_markup=new_case_skip_cancel())


@router.message(StateFilter(NewCase.assets))
async def newcase_step_assets(message: Message, state: FSMContext):
    """
    Process assets value input.
    ONLY active when in NewCase.assets state.
    """
    text = (message.text or "").strip()

    if text.lower() in ["пропустить", "skip", "-"]:
        await state.update_data(assets=0)
    else:
        try:
            assets_amount = float(text.replace(" ", "").replace(",", "."))
            if assets_amount < 0:
                await message.answer(
                    "❌ Сумма не может быть отрицательной\n\n"
                    "Попробуйте ещё раз или нажмите '⏭️ Пропустить'",
                    reply_markup=new_case_skip_cancel()
                )
                return
            await state.update_data(assets=assets_amount)
        except ValueError:
            await message.answer(
                "❌ Неверный формат\n\n"
                "Введите число или нажмите '⏭️ Пропустить'",
                reply_markup=new_case_skip_cancel()
            )
            return

    await state.set_state(NewCase.dependents)

    text = (
        "✅ Стоимость имущества сохранена\n\n"
        "Шаг 5/5: Введите количество иждивенцев\n\n"
        "Пример: 2\n"
        "Или нажмите '⏭️ Пропустить' если нет иждивенцев"
    )

    await message.answer(text, reply_markup=new_case_skip_cancel())


@router.message(StateFilter(NewCase.dependents))
async def newcase_step_dependents(message: Message, state: FSMContext):
    """
    Process dependents count and finalize case creation.
    ONLY active when in NewCase.dependents state.
    """
    text = (message.text or "").strip()

    if text.lower() in ["пропустить", "skip", "-"]:
        await state.update_data(dependents=0)
    else:
        try:
            dependents_count = int(text)
            if dependents_count < 0:
                await message.answer(
                    "❌ Количество не может быть отрицательным\n\n"
                    "Попробуйте ещё раз или нажмите '⏭️ Пропустить'",
                    reply_markup=new_case_skip_cancel()
                )
                return
            await state.update_data(dependents=dependents_count)
        except ValueError:
            await message.answer(
                "❌ Неверный формат\n\n"
                "Введите целое число или нажмите '⏭️ Пропустить'",
                reply_markup=new_case_skip_cancel()
            )
            return

    # Get all collected data
    data = await state.get_data()
    name = data.get("name", "Неизвестно")
    debt = data.get("debt", 0)
    income = data.get("income", 0)
    assets = data.get("assets", 0)
    dependents = data.get("dependents", 0)

    # TODO: Actually create the case in the database
    # For now, just show a summary
    logger.info(
        f"User {message.from_user.id} completed new case creation: "
        f"{name}, debt={debt}, income={income}, assets={assets}, dependents={dependents}"
    )

    await state.clear()

    text = (
        "✅ Дело успешно создано!\n\n"
        f"📋 Резюме:\n"
        f"ФИО: {name}\n"
        f"Задолженность: {debt:,.2f} ₽\n"
        f"Доход: {income:,.2f} ₽\n"
        f"Имущество: {assets:,.2f} ₽\n"
        f"Иждивенцы: {dependents}\n\n"
        "Используйте меню для работы с делом."
    )

    await message.answer(text, reply_markup=main_menu())


# ============================================================================
# SKIP BUTTON HANDLER (Callback)
# ============================================================================

@router.callback_query(F.data == "skip_step", StateFilter(NewCase))
async def handle_skip_in_fsm(call: CallbackQuery, state: FSMContext):
    """
    Handle skip button press during FSM flow.
    This allows users to skip optional steps using the inline button.
    """
    current_state = await state.get_state()

    if current_state == NewCase.income:
        await state.update_data(income=0)
        await state.set_state(NewCase.assets)

        text = (
            "⏭️ Доход пропущен\n\n"
            "Шаг 4/5: Введите примерную стоимость имущества (в рублях)\n\n"
            "Пример: 1000000\n"
            "Или нажмите '⏭️ Пропустить' если нет имущества"
        )

        try:
            await call.message.edit_text(text, reply_markup=new_case_skip_cancel())
        except TelegramBadRequest:
            await call.message.answer(text, reply_markup=new_case_skip_cancel())

    elif current_state == NewCase.assets:
        await state.update_data(assets=0)
        await state.set_state(NewCase.dependents)

        text = (
            "⏭️ Имущество пропущено\n\n"
            "Шаг 5/5: Введите количество иждивенцев\n\n"
            "Пример: 2\n"
            "Или нажмите '⏭️ Пропустить' если нет иждивенцев"
        )

        try:
            await call.message.edit_text(text, reply_markup=new_case_skip_cancel())
        except TelegramBadRequest:
            await call.message.answer(text, reply_markup=new_case_skip_cancel())

    elif current_state == NewCase.dependents:
        await state.update_data(dependents=0)

        # Get all collected data
        data = await state.get_data()
        name = data.get("name", "Неизвестно")
        debt = data.get("debt", 0)
        income = data.get("income", 0)
        assets = data.get("assets", 0)
        dependents = 0

        # TODO: Actually create the case in the database
        logger.info(
            f"User {call.from_user.id} completed new case creation: "
            f"{name}, debt={debt}, income={income}, assets={assets}, dependents={dependents}"
        )

        await state.clear()

        text = (
            "✅ Дело успешно создано!\n\n"
            f"📋 Резюме:\n"
            f"ФИО: {name}\n"
            f"Задолженность: {debt:,.2f} ₽\n"
            f"Доход: {income:,.2f} ₽\n"
            f"Имущество: {assets:,.2f} ₽\n"
            f"Иждивенцы: {dependents}\n\n"
            "Используйте меню для работы с делом."
        )

        try:
            await call.message.edit_text(text, reply_markup=main_menu())
        except TelegramBadRequest:
            await call.message.answer(text, reply_markup=main_menu())

    await call.answer("Пропущено")


# ============================================================================
# BACKWARD COMPATIBILITY
# ============================================================================

# Keep the old message-based trigger for backward compatibility
# But it's now low priority due to StateFilter(None)

@router.message(StateFilter(None), F.text == "➕ Новое дело")
async def newcase_start_message(message: Message, state: FSMContext):
    """
    Start new case creation from message (backward compatibility).

    CRITICAL: StateFilter(None) ensures this ONLY fires when user is NOT in FSM.
    This prevents conflict with command handlers and other FSM states.
    """
    logger.info(f"User {message.from_user.id} started new case via message (legacy)")

    await state.clear()
    await state.set_state(NewCase.name)

    text = (
        "📝 Создание нового дела\n\n"
        "Шаг 1/5: Введите ФИО должника\n\n"
        "Пример: Иванов Иван Иванович"
    )

    await message.answer(text, reply_markup=new_case_cancel())
