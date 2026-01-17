from docxtpl import DocxTemplate
import io
from sqlalchemy.ext.asyncio import AsyncSession

async def generate_petition_jinja(session: AsyncSession, case_id: int):
    # Заглушка данных дела
    context = {
        'court_name': 'Арбитражный суд города Москвы №5',
        'court_address': '',
        'debtor_full_name': 'Иванов Иван Иванович',
        'debtor_phone_or_absent': 'не указан',
        'debtor_inn_or_absent': 'не указан',
        'debtor_snils_or_absent': 'не указан',
        'debtor_address': 'г. Москва, ул. Ленина, д.1',
        'debtor_last_name_initials': 'Иванов И.И.',
        'debtor_birth_date': '01.01.1980',
        'passport_series': '45 12',
        'passport_number': '123456',
        'passport_issued_by': 'ОВД России',
        'passport_date': '01.01.2000',
        'passport_code': '123-456',
        'debtor_inn': '1234567890',
        'debtor_snils': '123-456-789 01',
        'ip_status_text': 'ИП не зарегистрирован',
        'date': '17.01.2026'
    }
    
    tpl = DocxTemplate('templates/petitions/bankruptcy_petition.docx')
    tpl.render(context)
    
    output = io.BytesIO()
    tpl.save(output)
    output.seek(0)
    return output.getvalue(), 'заявление.docx'

