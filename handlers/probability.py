from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

router = Router()

@router.callback_query(F.data.startswith("bankruptcy_probability:"))
async def bankruptcy_probability(callback: CallbackQuery, state: FSMContext):
    """Analyze bankruptcy probability using GigaChat AI."""
    from bot import get_case, AUTH_KEY, SCOPE, MODEL
    from bankrot_bot.services.gigachat import gigachat_chat

    # Extract case_id from callback data
    case_id = int(callback.data.split(":")[-1])
    uid = callback.from_user.id

    # Get case data
    case = get_case(uid, case_id)
    if not case:
        await callback.message.answer("❌ Дело не найдено.")
        await callback.answer()
        return

    # Parse case data
    (cid, _owner_user_id, code_name, case_number, court, judge, fin_manager,
     stage, notes, created_at, updated_at) = case

    # Prepare case info for analysis
    case_info = {
        "id": cid,
        "code_name": code_name,
        "case_number": case_number or "не указан",
        "court": court or "не указан",
        "judge": judge or "не указан",
        "fin_manager": fin_manager or "не указан",
        "stage": stage or "не указана",
        "notes": notes or "нет заметок"
    }

    await callback.message.answer("🔄 Анализирую дело... Пожалуйста, подождите.")

    # Create prompt for GigaChat
    prompt = f"""Проанализируй дело о банкротстве: {case_info}.

Дай краткую оценку:
1. Вероятность успешного завершения процедуры банкротства (в процентах)
2. Ключевые риски
3. Рекомендации для должника

Ответ должен быть структурированным и понятным."""

    try:
        response = await gigachat_chat(
            auth_key=AUTH_KEY,
            scope=SCOPE,
            model=MODEL,
            system_prompt="Ты — юридический помощник, специализирующийся на делах о банкротстве физических лиц в России.",
            user_text=prompt
        )

        await callback.message.answer(
            f"🎲 <b>Анализ вероятности банкротства</b>\n"
            f"<b>Дело #{cid}</b>: {code_name}\n\n"
            f"{response}",
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка при анализе: {str(e)}\n"
            "Попробуйте позже."
        )

    await callback.answer()
