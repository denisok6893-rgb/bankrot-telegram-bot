from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📂 Дела"), KeyboardButton(text="🧑‍⚖️ Клиенты")],
            [KeyboardButton(text="📝 Документы"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True
    )


def cases_menu_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать дело", callback_data="case:new")
    kb.button(text="📄 Список дел", callback_data="case:list")
    kb.button(text="🔙 Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def docs_menu_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📂 Выбрать дело", callback_data="docs:choose_case")
    kb.button(text="🧾 Ходатайство онлайн (последнее дело)", callback_data="docs:online:last")
    kb.button(text="🔙 Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()
