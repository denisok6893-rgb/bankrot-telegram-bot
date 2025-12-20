from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📂 Дела"), KeyboardButton(text="🧑‍⚖️ Клиенты")],
            [KeyboardButton(text="📝 Документы"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def cases_menu_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать дело", callback_data="case:new")
    kb.button(text="📄 Список дел", callback_data="case:list")
    kb.button(text="🔙 Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()


def docs_menu_ikb(cid: int | None = None) -> InlineKeyboardMarkup:
    petition_callback = f"docs:petition:{cid}" if cid is not None else "docs:petition:select"

    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Мой профиль", callback_data="profile:menu")
    kb.button(text="📂 Выбрать дело", callback_data="docs:choose_case")
    kb.button(text="🧾 Ходатайство о ВКС", callback_data="docs:gen:online_hearing")
    kb.button(text="🧾 Заявление о банкротстве", callback_data=petition_callback)
    kb.button(text="🔙 Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()
