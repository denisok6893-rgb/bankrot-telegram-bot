"""Case management handlers for bankruptcy bot."""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bankrot_bot.database import get_session
from bankrot_bot.models.case import Case, CaseStage

logger = logging.getLogger(__name__)

router = Router()


class NewCaseStates(StatesGroup):
    """FSM states for creating a new case."""
    debtor_name = State()
    debtor_inn = State()
    case_number = State()
    court = State()
    stage = State()
    manager_name = State()


class EditCaseStates(StatesGroup):
    """FSM states for editing a case."""
    field = State()
    value = State()


# Helper functions
async def get_case_by_id(session: AsyncSession, case_id: int, user_id: int) -> Optional[Case]:
    """Get case by ID and user ID."""
    result = await session.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_active_case_id(state: FSMContext) -> Optional[int]:
    """Get active case ID from FSM state."""
    data = await state.get_data()
    return data.get("active_case_id")


async def set_active_case_id(state: FSMContext, case_id: Optional[int]) -> None:
    """Set active case ID in FSM state."""
    await state.update_data(active_case_id=case_id)


# Command handlers
@router.message(Command("newcase"))
async def cmd_newcase(message: Message, state: FSMContext) -> None:
    """Start creating a new case."""
    try:
        await message.answer(
            "Создание нового дела о банкротстве.\n\n"
            "Введите имя должника (ФИО или название организации):"
        )
        await state.set_state(NewCaseStates.debtor_name)
        logger.info(f"User {message.from_user.id} started creating a new case")
    except Exception as e:
        logger.error(f"Error starting new case creation: {e}", exc_info=True)
        await message.answer("Ошибка при создании дела. Попробуйте позже.")


@router.message(NewCaseStates.debtor_name)
async def process_debtor_name(message: Message, state: FSMContext) -> None:
    """Process debtor name input."""
    try:
        debtor_name = message.text.strip()
        if not debtor_name:
            await message.answer("Имя должника не может быть пустым. Введите имя:")
            return

        await state.update_data(debtor_name=debtor_name)
        await message.answer(
            "Введите ИНН должника (или отправьте '-' для пропуска):"
        )
        await state.set_state(NewCaseStates.debtor_inn)
    except Exception as e:
        logger.error(f"Error processing debtor name: {e}", exc_info=True)
        await message.answer("Ошибка обработки данных. Попробуйте еще раз.")


@router.message(NewCaseStates.debtor_inn)
async def process_debtor_inn(message: Message, state: FSMContext) -> None:
    """Process debtor INN input."""
    try:
        inn = message.text.strip()
        debtor_inn = None if inn == "-" else inn

        await state.update_data(debtor_inn=debtor_inn)
        await message.answer(
            "Введите номер дела (формат: А00-00000/0000) или '-' для пропуска:"
        )
        await state.set_state(NewCaseStates.case_number)
    except Exception as e:
        logger.error(f"Error processing debtor INN: {e}", exc_info=True)
        await message.answer("Ошибка обработки данных. Попробуйте еще раз.")


@router.message(NewCaseStates.case_number)
async def process_case_number(message: Message, state: FSMContext) -> None:
    """Process case number input."""
    try:
        case_num = message.text.strip()
        case_number = None if case_num == "-" else case_num

        await state.update_data(case_number=case_number)
        await message.answer(
            "Введите наименование суда или '-' для пропуска:"
        )
        await state.set_state(NewCaseStates.court)
    except Exception as e:
        logger.error(f"Error processing case number: {e}", exc_info=True)
        await message.answer("Ошибка обработки данных. Попробуйте еще раз.")


@router.message(NewCaseStates.court)
async def process_court(message: Message, state: FSMContext) -> None:
    """Process court input."""
    try:
        court_name = message.text.strip()
        court = None if court_name == "-" else court_name

        await state.update_data(court=court)
        await message.answer(
            "Выберите стадию банкротства:\n"
            "1. Наблюдение\n"
            "2. Реструктуризация\n"
            "3. Реализация\n"
            "4. Завершено\n\n"
            "Введите номер или '-' для пропуска:"
        )
        await state.set_state(NewCaseStates.stage)
    except Exception as e:
        logger.error(f"Error processing court: {e}", exc_info=True)
        await message.answer("Ошибка обработки данных. Попробуйте еще раз.")


@router.message(NewCaseStates.stage)
async def process_stage(message: Message, state: FSMContext) -> None:
    """Process stage input."""
    try:
        stage_input = message.text.strip()
        stage = None

        if stage_input != "-":
            stage_map = {
                "1": CaseStage.OBSERVATION,
                "2": CaseStage.RESTRUCTURING,
                "3": CaseStage.REALIZATION,
                "4": CaseStage.COMPLETED,
            }
            stage = stage_map.get(stage_input)

            if stage is None:
                await message.answer(
                    "Неверный выбор. Введите номер от 1 до 4 или '-' для пропуска:"
                )
                return

        await state.update_data(stage=stage)
        await message.answer(
            "Введите ФИО арбитражного управляющего или '-' для пропуска:"
        )
        await state.set_state(NewCaseStates.manager_name)
    except Exception as e:
        logger.error(f"Error processing stage: {e}", exc_info=True)
        await message.answer("Ошибка обработки данных. Попробуйте еще раз.")


@router.message(NewCaseStates.manager_name)
async def process_manager_name(message: Message, state: FSMContext) -> None:
    """Process manager name and create case."""
    try:
        manager = message.text.strip()
        manager_name = None if manager == "-" else manager

        # Get all collected data
        data = await state.get_data()

        # Create case in database
        async with get_session() as session:
            new_case = Case(
                user_id=message.from_user.id,
                debtor_name=data["debtor_name"],
                debtor_inn=data.get("debtor_inn"),
                case_number=data.get("case_number"),
                court=data.get("court"),
                stage=data.get("stage"),
                manager_name=manager_name,
            )
            session.add(new_case)
            await session.flush()

            case_id = new_case.id

            # Set as active case
            await set_active_case_id(state, case_id)

            logger.info(f"User {message.from_user.id} created case #{case_id}")

            await message.answer(
                f"✅ Дело #{case_id} успешно создано!\n\n"
                f"{new_case.format_card()}\n\n"
                f"Дело автоматически установлено как активное."
            )

        await state.clear()
    except Exception as e:
        logger.error(f"Error creating case: {e}", exc_info=True)
        await message.answer("Ошибка при создании дела. Попробуйте позже.")
        await state.clear()


@router.message(Command("mycases"))
async def cmd_mycases(message: Message) -> None:
    """List all user's cases."""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(Case)
                .where(Case.user_id == message.from_user.id)
                .order_by(Case.updated_at.desc())
                .limit(50)
            )
            cases = result.scalars().all()

            if not cases:
                await message.answer(
                    "У вас пока нет дел.\n\n"
                    "Создайте новое дело командой /newcase"
                )
                return

            lines = ["📋 Ваши дела:\n"]
            for case in cases:
                stage_text = case.stage.value if case.stage else "—"
                lines.append(
                    f"#{case.id} | {case.debtor_name} | "
                    f"№{case.case_number or '—'} | {stage_text}"
                )

            lines.append(
                f"\n\nВсего дел: {len(cases)}\n"
                f"Для просмотра дела: /case <id>"
            )

            await message.answer("\n".join(lines))
            logger.info(f"User {message.from_user.id} viewed their cases")

    except Exception as e:
        logger.error(f"Error listing cases: {e}", exc_info=True)
        await message.answer("Ошибка при получении списка дел.")


@router.message(Command("case"))
async def cmd_case(message: Message) -> None:
    """View case details."""
    try:
        # Parse case ID from command
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer(
                "Использование: /case <id>\n"
                "Пример: /case 1"
            )
            return

        case_id = int(parts[1])

        async with get_session() as session:
            case = await get_case_by_id(session, case_id, message.from_user.id)

            if not case:
                await message.answer("Дело не найдено или вам не принадлежит.")
                return

            await message.answer(case.format_card())
            logger.info(f"User {message.from_user.id} viewed case #{case_id}")

    except Exception as e:
        logger.error(f"Error viewing case: {e}", exc_info=True)
        await message.answer("Ошибка при получении дела.")


@router.message(Command("setactive"))
async def cmd_setactive(message: Message, state: FSMContext) -> None:
    """Set active case."""
    try:
        # Parse case ID from command
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer(
                "Использование: /setactive <id>\n"
                "Пример: /setactive 1"
            )
            return

        case_id = int(parts[1])

        async with get_session() as session:
            case = await get_case_by_id(session, case_id, message.from_user.id)

            if not case:
                await message.answer("Дело не найдено или вам не принадлежит.")
                return

            await set_active_case_id(state, case_id)
            await message.answer(
                f"✅ Дело #{case_id} установлено как активное.\n\n"
                f"Должник: {case.debtor_name}\n"
                f"Номер дела: {case.case_number or '—'}"
            )
            logger.info(f"User {message.from_user.id} set active case to #{case_id}")

    except Exception as e:
        logger.error(f"Error setting active case: {e}", exc_info=True)
        await message.answer("Ошибка при установке активного дела.")


@router.message(Command("editcase"))
async def cmd_editcase(message: Message, state: FSMContext) -> None:
    """Start editing active case."""
    try:
        active_case_id = await get_active_case_id(state)

        if not active_case_id:
            await message.answer(
                "Нет активного дела.\n\n"
                "Выберите дело командой /setactive <id>"
            )
            return

        async with get_session() as session:
            case = await get_case_by_id(session, active_case_id, message.from_user.id)

            if not case:
                await set_active_case_id(state, None)
                await message.answer("Активное дело не найдено.")
                return

            await message.answer(
                f"Редактирование дела #{case.id}\n\n"
                f"{case.format_card()}\n\n"
                "Выберите поле для редактирования:\n"
                "1. Имя должника\n"
                "2. ИНН\n"
                "3. Номер дела\n"
                "4. Суд\n"
                "5. Стадия\n"
                "6. Арбитражный управляющий\n\n"
                "Введите номер поля или /cancel для отмены:"
            )
            await state.set_state(EditCaseStates.field)

    except Exception as e:
        logger.error(f"Error starting case edit: {e}", exc_info=True)
        await message.answer("Ошибка при редактировании дела.")


@router.message(EditCaseStates.field)
async def process_edit_field(message: Message, state: FSMContext) -> None:
    """Process field selection for editing."""
    try:
        field_input = message.text.strip()

        field_map = {
            "1": ("debtor_name", "Введите новое имя должника:"),
            "2": ("debtor_inn", "Введите новый ИНН или '-' для очистки:"),
            "3": ("case_number", "Введите новый номер дела или '-' для очистки:"),
            "4": ("court", "Введите новое наименование суда или '-' для очистки:"),
            "5": ("stage", "Выберите стадию:\n1. Наблюдение\n2. Реструктуризация\n3. Реализация\n4. Завершено\n\nВведите номер или '-' для очистки:"),
            "6": ("manager_name", "Введите ФИО нового АУ или '-' для очистки:"),
        }

        if field_input not in field_map:
            await message.answer("Неверный выбор. Введите номер от 1 до 6:")
            return

        field_name, prompt = field_map[field_input]
        await state.update_data(edit_field=field_name)
        await message.answer(prompt)
        await state.set_state(EditCaseStates.value)

    except Exception as e:
        logger.error(f"Error processing edit field: {e}", exc_info=True)
        await message.answer("Ошибка обработки данных.")
        await state.clear()


@router.message(EditCaseStates.value)
async def process_edit_value(message: Message, state: FSMContext) -> None:
    """Process new value and update case."""
    try:
        data = await state.get_data()
        field_name = data["edit_field"]
        value = message.text.strip()

        active_case_id = await get_active_case_id(state)

        async with get_session() as session:
            case = await get_case_by_id(session, active_case_id, message.from_user.id)

            if not case:
                await message.answer("Активное дело не найдено.")
                await state.clear()
                return

            # Process value based on field
            if field_name == "stage":
                if value == "-":
                    setattr(case, field_name, None)
                else:
                    stage_map = {
                        "1": CaseStage.OBSERVATION,
                        "2": CaseStage.RESTRUCTURING,
                        "3": CaseStage.REALIZATION,
                        "4": CaseStage.COMPLETED,
                    }
                    stage = stage_map.get(value)
                    if stage is None:
                        await message.answer("Неверный выбор. Попробуйте еще раз.")
                        return
                    setattr(case, field_name, stage)
            else:
                # For other fields
                new_value = None if value == "-" else value
                setattr(case, field_name, new_value)

            await session.flush()

            await message.answer(
                f"✅ Дело #{case.id} обновлено!\n\n"
                f"{case.format_card()}"
            )
            logger.info(f"User {message.from_user.id} updated case #{case.id} field {field_name}")

        await state.set_state(None)
        # Keep active_case_id in state
        await state.update_data(active_case_id=active_case_id)

    except Exception as e:
        logger.error(f"Error updating case: {e}", exc_info=True)
        await message.answer("Ошибка при обновлении дела.")
        await state.clear()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Cancel current operation."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активной операции для отмены.")
        return

    # Preserve active_case_id
    data = await state.get_data()
    active_case_id = data.get("active_case_id")

    await state.clear()

    if active_case_id:
        await state.update_data(active_case_id=active_case_id)

    await message.answer("Операция отменена.")
