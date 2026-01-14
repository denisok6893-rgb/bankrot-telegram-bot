from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

router = Router()

async def gigachat_chat_mock(prompt):
    return "Вероятность успеха: 78%\
✅ Долг < 1млн руб\
✅ >3 мес просрочка\
⚠️ Проверьте реестр ЕФРСБ\
Рекомендация: Подать в Мосбанкрот"

@router.callback_query(F.data.startswith("bankruptcy_probability:"))
async def bankruptcy_probability(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split(":")[-1])
    uid = callback.from_user.id
    
    try:
        from bot import get_case
        case = get_case(uid, case_id)
        if not case:
            await callback.message.answer("❌ Дело не найдено.")
            return
        
        await callback.message.edit_text("🤖 Анализирую дело...")
        response = gigachat_chat_mock("test")
        text = "Анализ банкротства:

" + response
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.message.answer("❌ Ошибка анализа")
        await callback.answer()
