from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ---------- Reply keyboard (нижние кнопки) ----------

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="📄 Документы")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел…",
    )


# ---------- Inline keyboards (новое меню) ----------

def start_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="▶️ Старт", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def home_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Мой профиль", callback_data="menu:profile")
    kb.button(text="📄 Документы", callback_data="menu:docs")
    kb.button(text="❓ Помощь", callback_data="menu:help")
    kb.adjust(2, 1)
    return kb.as_markup()


def profile_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📂 Дела", callback_data="profile:cases")
    kb.button(text="✏️ Редактировать мой профиль", callback_data="profile:edit")
    kb.button(text="🔙 Назад", callback_data="menu:home")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def cases_list_ikb(cases: list[tuple]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in cases:
        cid = row[0]
        title = row[1] or f"Дело #{cid}"
        kb.button(text=title, callback_data=f"case:open:{cid}")
    kb.button(text="🔙 Назад", callback_data="menu:profile")
    kb.adjust(1)
    return kb.as_markup()


def case_card_ikb(case_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📎 Документы по делу", callback_data=f"case:docs:{case_id}")
    kb.button(text="✏️ Редактирование карточки", callback_data=f"case:edit:{case_id}")
    kb.button(text="💬 Помощь по делу (ИИ)", callback_data=f"case:help:{case_id}")
    kb.button(text="⚖️ Судебные акты по делу", callback_data=f"case:rulings:{case_id}")
    kb.button(text="🔙 Назад", callback_data="profile:cases")
    kb.adjust(1)
    return kb.as_markup()


def docs_home_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def help_ikb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


# ---------- Документы (чтобы не сломать текущие хэндлеры в bot.py) ----------

def docs_menu_ikb(case_id: int) -> InlineKeyboardMarkup:
    """
    Меню документов ДЛЯ выбранного дела.
    Оставлено совместимым с текущими хэндлерами в bot.py:
    - docs:gen:online_hearing
    - docs:petition:bankruptcy_petition
    - docs:choose_case
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Ходатайство о ВКС", callback_data="docs:gen:online_hearing")
    kb.button(text="📄 Заявление о банкротстве", callback_data="docs:petition:bankruptcy_petition")
    kb.button(text="🔁 Выбрать другое дело", callback_data="docs:choose_case")
    kb.button(text="🔙 Назад к делу", callback_data=f"case:open:{case_id}")
    kb.adjust(1)
    return kb.as_markup()

def _pretty_doc_label(filename: str) -> str:
    """
    bankruptcy_petition_case_3_20251222_110956.docx
    hodatajstvo_online_case_3_20251219_235309.docx
    """
    base = filename.replace(".docx", "")

    # Тип документа
    if base.startswith("bankruptcy_petition_"):
        doc_title = "Заявление о банкротстве"
    elif base.startswith("hodatajstvo_online_"):
        doc_title = "Ходатайство о ВКС"
    elif base.startswith("petition_"):
        doc_title = "Петиция/заявление"
    else:
        doc_title = "Документ"

    # Дата/время в конце: _YYYYMMDD_HHMMSS
    parts = base.split("_")
    dt = ""
    if len(parts) >= 2:
        ymd = parts[-2]
        hms = parts[-1]
        if len(ymd) == 8 and len(hms) == 6 and ymd.isdigit() and hms.isdigit():
            dt = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]} {hms[0:2]}:{hms[2:4]}"

    return f"{doc_title} — {dt}" if dt else doc_title


def case_files_ikb(case_id: int, filenames: list[str]) -> InlineKeyboardMarkup:
    """
    Кнопки с короткими названиями, но callback хранит реальное имя файла.
    callback: case:file:<case_id>:<filename>
    """
    kb = InlineKeyboardBuilder()
    for name in filenames:
        label = _pretty_doc_label(name)
        kb.button(text=f"📄 {label}", callback_data=f"case:file:{case_id}:{name}")
    kb.button(text="🔙 Назад", callback_data=f"case:open:{case_id}")
    kb.adjust(1)
    return kb.as_markup()

def case_archive_ikb(case_id: int, filenames: list[str], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    """Архив документов по делу с пагинацией."""
    kb = InlineKeyboardBuilder()
    for name in filenames:
        label = _pretty_doc_label(name)
        kb.button(text=f"📄 {label}", callback_data=f"case:file:{case_id}:{name}")

    # навигация страниц
    if has_prev:
        kb.button(text="⬅️ Назад", callback_data=f"case:archive:{case_id}:{page-1}")
    if has_next:
        kb.button(text="➡️ Далее", callback_data=f"case:archive:{case_id}:{page+1}")

    kb.button(text="🔙 Назад", callback_data=f"case:docs:{case_id}")
    kb.adjust(1)
    return kb.as_markup()

