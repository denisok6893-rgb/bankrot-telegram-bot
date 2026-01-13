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
    """Новое главное меню (MVP): Мои дела, Документы, Помощь."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📂 Мои дела", callback_data="menu:my_cases")
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
    kb.button(text="➕ Создать дело", callback_data="case:new")
    for row in cases:
        cid = row[0]
        title = row[1] or f"Дело #{cid}"
        kb.button(text=title, callback_data=f"case:open:{cid}")
    kb.button(text="🔙 Назад", callback_data="menu:profile")
    kb.adjust(1)
    return kb.as_markup()


def case_card_ikb(case_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Кредиторы/должники", callback_data=f"case:parties:{case_id}")
    kb.button(text="🏠 Опись имущества", callback_data=f"case:assets:{case_id}")
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
    """Подменю раздела Помощь с несколькими пунктами."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📖 Как пользоваться ботом", callback_data="help:howto")
    kb.button(text="📋 Что такое карточки дел", callback_data="help:cases")
    kb.button(text="📄 О документах", callback_data="help:docs")
    kb.button(text="✉️ Контакты / Обратная связь", callback_data="help:contacts")
    kb.button(text="ℹ️ О боте", callback_data="help:about")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def help_item_ikb() -> InlineKeyboardMarkup:
    """Навигация для отдельных пунктов помощи."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад в помощь", callback_data="menu:help")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


# ---------- Раздел «Мои дела» ----------

def my_cases_ikb(cases: list[tuple], active_case_id: int = None) -> InlineKeyboardMarkup:
    """
    Раздел «Мои дела».
    Показывает список дел + кнопку создания дела + заглушку ИИ.

    cases: список кортежей (id, title/code_name, ...)
    active_case_id: ID активного дела (если установлено)
    """
    kb = InlineKeyboardBuilder()

    # Кнопка создания нового дела всегда сверху
    kb.button(text="➕ Создать дело", callback_data="case:new")

    # Список дел пользователя
    if cases:
        for row in cases:
            cid = row[0]
            title = row[1] or f"Дело #{cid}"
            # Отметим активное дело
            if active_case_id and cid == active_case_id:
                title = f"✓ {title}"
            kb.button(text=title, callback_data=f"case:open:{cid}")

    # ИИ-помощник (заглушка)
    kb.button(text="🤖 ИИ-помощник (скоро)", callback_data="ai:placeholder")

    # Кнопка возврата
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


# ---------- Публичный каталог документов ----------

def docs_catalog_ikb() -> InlineKeyboardMarkup:
    """Главное меню публичного каталога документов."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заявления", callback_data="docs_cat:zayavleniya")
    kb.button(text="📝 Ходатайства", callback_data="docs_cat:khodataystva")
    kb.button(text="📄 Прочие документы", callback_data="docs_cat:prochie")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def docs_category_ikb(category: str, docs: list[tuple]) -> InlineKeyboardMarkup:
    """
    Список документов в категории.
    docs: список (doc_id, title)
    """
    kb = InlineKeyboardBuilder()
    for doc_id, title in docs:
        kb.button(text=title, callback_data=f"docs_item:{category}:{doc_id}")
    kb.button(text="🔙 Назад к категориям", callback_data="menu:docs")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def docs_item_ikb(category: str) -> InlineKeyboardMarkup:
    """Навигация для карточки документа."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад к списку", callback_data=f"docs_cat:{category}")
    kb.button(text="🏠 Главное меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


# ---------- Документы (чтобы не сломать текущие хэндлеры в bot.py) ----------

def docs_menu_ikb(case_id: int) -> InlineKeyboardMarkup:
    """
    Меню документов ДЛЯ выбранного дела.
    Оставлено совместимым с текущими хэндлерами в bot.py:
    - docs:petition:bankruptcy_petition
    - docs:choose_case
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Заявление о банкротстве", callback_data="docs:petition:bankruptcy_petition")
    kb.button(text="🔁 Выбрать другое дело", callback_data="docs:choose_case")
    kb.button(text="🔙 Назад к делу", callback_data=f"case:open:{case_id}")
    kb.adjust(1)
    return kb.as_markup()

def _pretty_doc_label(filename: str) -> str:
    """
    bankruptcy_petition_case_3_20251222_110956.docx
    """
    base = filename.replace(".docx", "")

    # Тип документа
    if base.startswith("bankruptcy_petition_"):
        doc_title = "Заявление о банкротстве"
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


def cases_menu_ikb() -> InlineKeyboardMarkup:
    """Меню раздела «Дела»."""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать дело", callback_data="case:new")
    kb.button(text="📋 Список дел", callback_data="case:list")
    kb.button(text="🔙 Назад", callback_data="menu:profile")
    kb.adjust(1)
    return kb.as_markup()


# ---------- Кредиторы/Должники ----------

def case_parties_ikb(case_id: int, parties: list, creditors_count: int, debtors_count: int) -> InlineKeyboardMarkup:
    """Список кредиторов и должников по делу."""
    kb = InlineKeyboardBuilder()

    # Кнопки добавления
    kb.button(text=f"➕ Добавить кредитора (всего: {creditors_count})", callback_data=f"party:add_creditor:{case_id}")
    kb.button(text=f"➕ Добавить должника (всего: {debtors_count})", callback_data=f"party:add_debtor:{case_id}")

    # Кнопка генерации документа
    if parties:
        kb.button(text="📄 Сгенерировать список (DOCX)", callback_data=f"party:generate_doc:{case_id}")

    # Список записей (первые 10)
    for p in parties[:10]:
        party_id = p.id
        role_emoji = "💳" if p.role == "creditor" else "📤"
        amount = f"{float(p.amount):.2f}" if p.amount else "0.00"
        text = f"{role_emoji} {p.name}: {amount} ₽"
        kb.button(text=text, callback_data=f"party:view:{party_id}")

    # Навигация
    kb.button(text="🔙 Назад к делу", callback_data=f"case:open:{case_id}")
    kb.adjust(1)
    return kb.as_markup()


def party_view_ikb(party_id: int, case_id: int) -> InlineKeyboardMarkup:
    """Просмотр отдельной записи кредитора/должника."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"party:delete:{party_id}:{case_id}")
    kb.button(text="🔙 Назад к списку", callback_data=f"case:parties:{case_id}")
    kb.adjust(1)
    return kb.as_markup()


# ---------- Опись имущества ----------

def case_assets_ikb(case_id: int, assets: list, total_value: float) -> InlineKeyboardMarkup:
    """Список имущества по делу."""
    kb = InlineKeyboardBuilder()

    # Кнопка добавления
    total_text = f"{total_value:.2f}" if total_value else "0.00"
    kb.button(text=f"➕ Добавить имущество (всего: {total_text} ₽)", callback_data=f"asset:add:{case_id}")

    # Кнопка генерации документа
    if assets:
        kb.button(text="📄 Сгенерировать опись (DOCX)", callback_data=f"asset:generate_doc:{case_id}")

    # Список записей (первые 10)
    for a in assets[:10]:
        asset_id = a.id
        value = f"{float(a.value):.2f}" if a.value else "—"
        text = f"🏠 {a.kind}: {value} ₽"
        kb.button(text=text, callback_data=f"asset:view:{asset_id}")

    # Навигация
    kb.button(text="🔙 Назад к делу", callback_data=f"case:open:{case_id}")
    kb.adjust(1)
    return kb.as_markup()


def asset_view_ikb(asset_id: int, case_id: int) -> InlineKeyboardMarkup:
    """Просмотр отдельной записи имущества."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"asset:delete:{asset_id}:{case_id}")
    kb.button(text="🔙 Назад к списку", callback_data=f"case:assets:{case_id}")
    kb.adjust(1)
    return kb.as_markup()

