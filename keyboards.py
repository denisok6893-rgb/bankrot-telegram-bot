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
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Мой профиль", callback_data="profile:menu")
    kb.button(text="📂 Выбрать дело", callback_data="docs:choose_case")

    # Документы по выбранному делу
    kb.button(text="🧾 Ходатайство о ВКС", callback_data="docs:gen:online_hearing")

    # Заявление о банкротстве: если дело не выбрано — попросим выбрать
    if cid is None:
        kb.button(text="📄 Заявление о банкротстве", callback_data="docs:petition:select")
    else:
        kb.button(text="📄 Заявление о банкротстве", callback_data=f"docs:petition:{cid}")

    kb.button(text="🔙 Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()
