"""FSM handlers for creating a new case via message input."""
import logging
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

logger = logging.getLogger(__name__)

# Create router for this module
router = Router()


class NewCase(StatesGroup):
    """FSM states for new case creation."""
    name = State()
    debt = State()
    income = State()
    assets = State()
    dependents = State()


def examples_kb() -> ReplyKeyboardMarkup:
    """Keyboard with example buttons."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пример")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def skip_kb() -> ReplyKeyboardMarkup:
    """Keyboard with skip button."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


@router.message(StateFilter(None), F.text == "➕ Новое дело")
async def newcase_start_message(message: Message, state: FSMContext):
    """Start new case creation from message (not callback).

    CRITICAL: StateFilter(None) ensures this ONLY fires when user is NOT in FSM.
    This prevents conflict with command handlers and other FSM states.
    """
    logger.info(f"User {message.from_user.id} started new case via message")

    await state.clear()
    await state.set_state(NewCase.name)
    await message.answer(
        "📝 Создание нового дела\n\n"
        "Шаг 1/5: Введите ФИО должника",
        reply_markup=examples_kb()
    )


@router.message(StateFilter(NewCase.name))
async def newcase_step_name(message: Message, state: FSMContext):
    """Process name input. ONLY active when in NewCase.name state."""
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пожалуйста, введите ФИО должника")
        return

    await state.update_data(name=text)
    await state.set_state(NewCase.debt)
    await message.answer(
        "Шаг 2/5: Введите общую сумму задолженности (в рублях)\n\n"
        "Например: 500000",
        reply_markup=examples_kb()
    )


@router.message(StateFilter(NewCase.debt))
async def newcase_step_debt(message: Message, state: FSMContext):
    """Process debt amount input. ONLY active when in NewCase.debt state."""
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пожалуйста, введите сумму задолженности")
        return

    # Try to parse as number
    try:
        debt_amount = float(text.replace(" ", "").replace(",", "."))
        if debt_amount < 0:
            await message.answer("Сумма не может быть отрицательной. Попробуйте ещё раз")
            return
    except ValueError:
        await message.answer("Неверный формат. Введите число, например: 500000")
        return

    await state.update_data(debt=debt_amount)
    await state.set_state(NewCase.income)
    await message.answer(
        "Шаг 3/5: Введите ежемесячный доход (в рублях)\n\n"
        "Например: 50000\n"
        "Или 'Пропустить' если нет дохода",
        reply_markup=skip_kb()
    )


@router.message(StateFilter(NewCase.income))
async def newcase_step_income(message: Message, state: FSMContext):
    """Process income input. ONLY active when in NewCase.income state."""
    text = (message.text or "").strip()

    if text.lower() in ["пропустить", "skip", "-"]:
        await state.update_data(income=0)
    else:
        try:
            income_amount = float(text.replace(" ", "").replace(",", "."))
            if income_amount < 0:
                await message.answer("Сумма не может быть отрицательной. Попробуйте ещё раз")
                return
            await state.update_data(income=income_amount)
        except ValueError:
            await message.answer("Неверный формат. Введите число или 'Пропустить'")
            return

    await state.set_state(NewCase.assets)
    await message.answer(
        "Шаг 4/5: Введите примерную стоимость имущества (в рублях)\n\n"
        "Например: 1000000\n"
        "Или 'Пропустить' если нет имущества",
        reply_markup=skip_kb()
    )


@router.message(StateFilter(NewCase.assets))
async def newcase_step_assets(message: Message, state: FSMContext):
    """Process assets value input. ONLY active when in NewCase.assets state."""
    text = (message.text or "").strip()

    if text.lower() in ["пропустить", "skip", "-"]:
        await state.update_data(assets=0)
    else:
        try:
            assets_amount = float(text.replace(" ", "").replace(",", "."))
            if assets_amount < 0:
                await message.answer("Сумма не может быть отрицательной. Попробуйте ещё раз")
                return
            await state.update_data(assets=assets_amount)
        except ValueError:
            await message.answer("Неверный формат. Введите число или 'Пропустить'")
            return

    await state.set_state(NewCase.dependents)
    await message.answer(
        "Шаг 5/5: Введите количество иждивенцев\n\n"
        "Например: 2\n"
        "Или 'Пропустить' если нет иждивенцев",
        reply_markup=skip_kb()
    )


@router.message(StateFilter(NewCase.dependents))
async def newcase_step_dependents(message: Message, state: FSMContext):
    """Process dependents count and finalize case creation. ONLY active when in NewCase.dependents state."""
    text = (message.text or "").strip()

    if text.lower() in ["пропустить", "skip", "-"]:
        await state.update_data(dependents=0)
    else:
        try:
            dependents_count = int(text)
            if dependents_count < 0:
                await message.answer("Количество не может быть отрицательным. Попробуйте ещё раз")
                return
            await state.update_data(dependents=dependents_count)
        except ValueError:
            await message.answer("Неверный формат. Введите целое число или 'Пропустить'")
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

    await state.clear()

    # Remove custom keyboard
    from aiogram.types import ReplyKeyboardRemove

    await message.answer(
        f"✅ Дело создано!\n\n"
        f"ФИО: {name}\n"
        f"Задолженность: {debt:,.2f} ₽\n"
        f"Доход: {income:,.2f} ₽\n"
        f"Имущество: {assets:,.2f} ₽\n"
        f"Иждивенцы: {dependents}\n\n"
        f"Используйте команду /mycases для просмотра своих дел.",
        reply_markup=ReplyKeyboardRemove()
    )

    logger.info(f"User {message.from_user.id} completed new case creation: {name}")
