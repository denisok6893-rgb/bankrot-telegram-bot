from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from docxtpl import DocxTemplate
from aiogram.types import FSInputFile
import os

router = Router()

@router.callback_query(F.data.startswith('generate_petition'))
async def generate_petition(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split(':')[-1])
    
    # Данные для теста (заменишь потом на БД)
    context = {
        'debtor': {
            'fio': 'Серенко Ю.А.',
            'birthdate': '21.01.1975',
            'passport': '45 12 345678',
            'address': 'г. Краснодар, ул. Ленина, д. 10',
            'inn': '7723456789',
            'phone': '+7(999)123-45-67'
        },
        'court_name': 'Арбитражный суд Краснодарского края',
        'total_debt': '842 000',
        'date': '14 января 2026 г.',
        'creditors': [
            {'name': 'ООО "Ромашка"', 'debt': '500 000'},
            {'name': 'ИП Иванов И.И.', 'debt': '342 000'}
        ]
    }
    
    try:
        tpl = DocxTemplate('templates/real_petition.docx')
        tpl.render(context)
        filename = f"petition_{case_id}.docx"
        tpl.save(filename)
        
        await callback.message.answer_document(
            FSInputFile(filename),
            caption=f"✅ Заявление о банкротстве №{case_id}"
        )
        os.remove(filename)
        await callback.answer("Готово!")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}")
