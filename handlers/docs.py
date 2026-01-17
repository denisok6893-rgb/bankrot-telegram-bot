from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from docxtpl import DocxTemplate
from aiogram.types import FSInputFile
from bankrot_bot.services.docx_jinja import generate_petition_jinja
import os

router = Router()

@router.callback_query(F.data.startswith("generate_petition"))
async def generate_petition(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split(":")[-1])
