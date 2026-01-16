"""
Refactored Keyboard Module - InlineKeyboardMarkup Only

This module provides all keyboards for the bankrot-telegram-bot.
ALL keyboards are InlineKeyboardMarkup (no ReplyKeyboardMarkup).
ALL menus have "← Back" button with callback_data="main" (except main menu).

Menu Structure:
1. MAIN MENU: 👤 Profile | ➕ New Case | 📋 My Cases
2. PROFILE: 📋 Profile Data | ✏️ Edit | 📊 Stats | ← Back
3. MY CASES: Case list + ➕ New | ← Back
4. NEW CASE FSM: ➕ New Case → Name/Amount with ← Cancel button
"""

from typing import List, Tuple, Optional
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ============================================================================
# MAIN MENU
# ============================================================================

def main_menu() -> InlineKeyboardMarkup:
    """
    Main menu with three primary sections.
    No back button - this is the top level.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Мой профиль", callback_data="profile")
    kb.button(text="➕ Новое дело", callback_data="new_case")
    kb.button(text="📋 Мои дела", callback_data="my_cases")
    kb.adjust(2, 1)  # First row: 2 buttons, second row: 1 button
    return kb.as_markup()


# ============================================================================
# PROFILE MENU
# ============================================================================

def profile_menu() -> InlineKeyboardMarkup:
    """
    Profile submenu with profile data, edit, stats options.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Данные профиля", callback_data="profile_data")
    kb.button(text="✏️ Редактировать", callback_data="profile_edit")
    kb.button(text="📊 Статистика", callback_data="profile_stats")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# MY CASES MENU
# ============================================================================

def my_cases_menu(cases: List[Tuple[int, str]], active_case_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """
    My cases menu with case list + new case button.

    Args:
        cases: List of (case_id, case_title) tuples
        active_case_id: ID of currently active case (will be marked with ✓)
    """
    kb = InlineKeyboardBuilder()

    # New case button at the top
    kb.button(text="➕ Новое дело", callback_data="new_case")

    # List of cases
    for case_id, title in cases:
        display_title = f"✓ {title}" if case_id == active_case_id else title
        kb.button(text=display_title, callback_data=f"case_open:{case_id}")

    # Back button
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


def case_card_menu(case_id: int) -> InlineKeyboardMarkup:
    """
    Case card menu showing all case options.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Кредиторы/должники", callback_data=f"case_parties:{case_id}")
    kb.button(text="🏠 Опись имущества", callback_data=f"case_assets:{case_id}")
    kb.button(text="📎 Документы по делу", callback_data=f"case_docs:{case_id}")
    kb.button(text="✏️ Редактировать", callback_data=f"case_edit:{case_id}")
    kb.button(text="💬 Помощь по делу (ИИ)", callback_data=f"case_help:{case_id}")
    kb.button(text="🔙 К списку дел", callback_data="my_cases")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# NEW CASE FSM KEYBOARDS
# ============================================================================

def new_case_cancel() -> InlineKeyboardMarkup:
    """
    Cancel button for FSM states.
    Used during new case creation flow.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="← Отмена", callback_data="cancel_fsm")
    kb.adjust(1)
    return kb.as_markup()


def new_case_skip_cancel() -> InlineKeyboardMarkup:
    """
    Skip and Cancel buttons for optional FSM steps.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭️ Пропустить", callback_data="skip_step")
    kb.button(text="← Отмена", callback_data="cancel_fsm")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# CASE PARTIES (Creditors/Debtors)
# ============================================================================

def case_parties_menu(case_id: int, parties: List, creditors_count: int, debtors_count: int) -> InlineKeyboardMarkup:
    """
    List of creditors and debtors with add/generate options.
    """
    kb = InlineKeyboardBuilder()

    # Add buttons
    kb.button(text=f"➕ Добавить кредитора ({creditors_count})", callback_data=f"add_creditor:{case_id}")
    kb.button(text=f"➕ Добавить должника ({debtors_count})", callback_data=f"add_debtor:{case_id}")

    # Generate document button
    if parties:
        kb.button(text="📄 Сгенерировать список (DOCX)", callback_data=f"generate_parties_doc:{case_id}")

    # List of parties (first 10)
    for p in parties[:10]:
        party_id = p.id
        role_emoji = "💳" if p.role == "creditor" else "📤"
        amount = f"{float(p.amount):.2f}" if p.amount else "0.00"
        text = f"{role_emoji} {p.name}: {amount} ₽"
        kb.button(text=text, callback_data=f"party_view:{party_id}")

    # Back button
    kb.button(text="🔙 К карточке дела", callback_data=f"case_open:{case_id}")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


def party_view_menu(party_id: int, case_id: int) -> InlineKeyboardMarkup:
    """
    View individual party (creditor/debtor) with delete option.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"party_delete:{party_id}:{case_id}")
    kb.button(text="🔙 К списку", callback_data=f"case_parties:{case_id}")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# CASE ASSETS (Inventory)
# ============================================================================

def case_assets_menu(case_id: int, assets: List, total_value: float) -> InlineKeyboardMarkup:
    """
    List of assets with add/generate options.
    """
    kb = InlineKeyboardBuilder()

    # Add button
    total_text = f"{total_value:.2f}" if total_value else "0.00"
    kb.button(text=f"➕ Добавить имущество ({total_text} ₽)", callback_data=f"add_asset:{case_id}")

    # Generate document button
    if assets:
        kb.button(text="📄 Сгенерировать опись (DOCX)", callback_data=f"generate_assets_doc:{case_id}")

    # List of assets (first 10)
    for a in assets[:10]:
        asset_id = a.id
        value = f"{float(a.value):.2f}" if a.value else "—"
        text = f"🏠 {a.kind}: {value} ₽"
        kb.button(text=text, callback_data=f"asset_view:{asset_id}")

    # Back button
    kb.button(text="🔙 К карточке дела", callback_data=f"case_open:{case_id}")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


def asset_view_menu(asset_id: int, case_id: int) -> InlineKeyboardMarkup:
    """
    View individual asset with delete option.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data=f"asset_delete:{asset_id}:{case_id}")
    kb.button(text="🔙 К списку", callback_data=f"case_assets:{case_id}")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# CASE DOCUMENTS
# ============================================================================

def case_docs_menu(case_id: int) -> InlineKeyboardMarkup:
    """
    Case documents menu with generation options.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Заявление о банкротстве", callback_data=f"gen_bankruptcy_petition:{case_id}")
    kb.button(text="📋 Список кредиторов", callback_data=f"gen_creditors_list:{case_id}")
    kb.button(text="📦 Архив документов", callback_data=f"case_archive:{case_id}")
    kb.button(text="🔙 К карточке дела", callback_data=f"case_open:{case_id}")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


def case_archive_menu(case_id: int, filenames: List[str], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    """
    Case archive with file list and pagination.
    """
    kb = InlineKeyboardBuilder()

    for name in filenames:
        kb.button(text=f"📄 {name}", callback_data=f"case_file:{case_id}:{name}")

    # Pagination
    if has_prev:
        kb.button(text="⬅️ Назад", callback_data=f"case_archive:{case_id}:{page-1}")
    if has_next:
        kb.button(text="➡️ Далее", callback_data=f"case_archive:{case_id}:{page+1}")

    # Back button
    kb.button(text="🔙 К документам", callback_data=f"case_docs:{case_id}")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# DOCUMENTS CATALOG (Public)
# ============================================================================

def docs_catalog_menu() -> InlineKeyboardMarkup:
    """
    Public documents catalog - accessible to all users.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заявления", callback_data="docs_cat:zayavleniya")
    kb.button(text="📝 Ходатайства", callback_data="docs_cat:khodataystva")
    kb.button(text="📄 Прочие документы", callback_data="docs_cat:prochie")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


def docs_category_menu(category: str, docs: List[Tuple[str, str]]) -> InlineKeyboardMarkup:
    """
    Documents in a specific category.

    Args:
        category: Category identifier
        docs: List of (doc_id, title) tuples
    """
    kb = InlineKeyboardBuilder()
    for doc_id, title in docs:
        kb.button(text=title, callback_data=f"docs_item:{category}:{doc_id}")
    kb.button(text="🔙 К категориям", callback_data="docs_catalog")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


def docs_item_menu(category: str) -> InlineKeyboardMarkup:
    """
    Individual document view navigation.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 К списку", callback_data=f"docs_cat:{category}")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# HELP MENU
# ============================================================================

def help_menu() -> InlineKeyboardMarkup:
    """
    Help section with various topics.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="📖 Как пользоваться ботом", callback_data="help_howto")
    kb.button(text="📋 Что такое карточки дел", callback_data="help_cases")
    kb.button(text="📄 О документах", callback_data="help_docs")
    kb.button(text="✉️ Контакты", callback_data="help_contacts")
    kb.button(text="ℹ️ О боте", callback_data="help_about")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


def help_item_menu() -> InlineKeyboardMarkup:
    """
    Navigation for individual help items.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 К помощи", callback_data="help")
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# UTILITY KEYBOARDS
# ============================================================================

def confirm_action(action_data: str, case_id: int) -> InlineKeyboardMarkup:
    """
    Confirmation dialog for destructive actions.

    Args:
        action_data: Callback data for confirmation
        case_id: Case ID for back navigation
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"confirm:{action_data}")
    kb.button(text="❌ Отменить", callback_data=f"case_open:{case_id}")
    kb.adjust(2)
    return kb.as_markup()


def back_to_main() -> InlineKeyboardMarkup:
    """
    Simple back to main menu button.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="← Назад", callback_data="main")
    kb.adjust(1)
    return kb.as_markup()


# ============================================================================
# BACKWARD COMPATIBILITY
# ============================================================================

# Aliases for backward compatibility with existing code
main_menu_kb = main_menu
start_ikb = main_menu
home_ikb = main_menu
profile_ikb = profile_menu
my_cases_ikb = my_cases_menu
case_card_ikb = case_card_menu
case_parties_ikb = case_parties_menu
party_view_ikb = party_view_menu
case_assets_ikb = case_assets_menu
asset_view_ikb = asset_view_menu
docs_catalog_ikb = docs_catalog_menu
docs_category_ikb = docs_category_menu
docs_item_ikb = docs_item_menu
help_ikb = help_menu
help_item_ikb = help_item_menu
