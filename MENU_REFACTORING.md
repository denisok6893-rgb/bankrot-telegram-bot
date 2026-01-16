# Menu System Refactoring

## Summary

Complete refactoring of the bankrot-telegram-bot menu system with the following goals:
- ✅ **Only InlineKeyboardMarkup** (removed all ReplyKeyboardMarkup)
- ✅ **Consistent "← Back" button** (callback_data="main")
- ✅ **edit_message_text** for clean navigation (no chat spam)
- ✅ **Preserved FSM functionality** (new case creation with inline keyboards)

## Files Changed

### 1. `keyboards.py` (Refactored)
Complete rewrite of keyboard module with:
- All keyboards use `InlineKeyboardMarkup`
- Consistent "← Назад" button with `callback_data="main"`
- Type hints for all functions
- Comprehensive documentation
- Backward compatibility aliases

**Key Functions:**
- `main_menu()` - Main menu (Profile, New Case, My Cases)
- `profile_menu()` - Profile submenu
- `my_cases_menu()` - Cases list
- `case_card_menu()` - Case details
- `new_case_cancel()` - FSM cancel button
- `new_case_skip_cancel()` - FSM skip/cancel buttons

### 2. `handlers/callbacks.py` (Refactored)
Complete rewrite of callback handlers with:
- All handlers use `edit_message_text`
- Proper error handling with `safe_edit_message()`
- Consistent callback_data structure
- Type hints and documentation

**Key Callbacks:**
- `main` - Main menu (central hub for all back buttons)
- `profile`, `profile_data`, `profile_edit`, `profile_stats` - Profile actions
- `my_cases` - My cases list
- `case_open:<id>` - Open case card
- `case_parties:<id>`, `case_assets:<id>`, `case_docs:<id>` - Case sections
- `help`, `help_*` - Help menu items
- `docs_catalog`, `docs_cat:*`, `docs_item:*` - Documents catalog
- `cancel_fsm` - Cancel FSM flow
- `skip_step` - Skip optional FSM steps

### 3. `handlers/newcase_fsm.py` (Refactored)
Complete rewrite of FSM handlers with:
- All keyboards use `InlineKeyboardMarkup`
- "← Отмена" (Cancel) button in all steps
- "⏭️ Пропустить" (Skip) button for optional steps
- Both callback and message triggers
- Proper state management

**FSM States:**
1. `NewCase.name` - Enter debtor's full name
2. `NewCase.debt` - Enter total debt amount
3. `NewCase.income` - Enter monthly income (optional)
4. `NewCase.assets` - Enter asset value (optional)
5. `NewCase.dependents` - Enter dependents count (optional)

### 4. `bot.py` (Updated)
- Registered `callback_router` from `handlers.callbacks`
- Updated `/start` command to use new `main_menu()`
- Removed ReplyKeyboardMarkup from start command

## Menu Structure

```
🏠 MAIN MENU (callback_data="main")
├── 👤 Мой профиль (callback_data="profile")
│   ├── 📋 Данные профиля (callback_data="profile_data")
│   ├── ✏️ Редактировать (callback_data="profile_edit")
│   ├── 📊 Статистика (callback_data="profile_stats")
│   └── ← Назад (callback_data="main")
│
├── ➕ Новое дело (callback_data="new_case")
│   └── [FSM Flow with inline keyboards]
│       ├── Step 1: Name
│       ├── Step 2: Debt
│       ├── Step 3: Income (optional)
│       ├── Step 4: Assets (optional)
│       ├── Step 5: Dependents (optional)
│       └── [← Отмена at each step]
│
└── 📋 Мои дела (callback_data="my_cases")
    ├── ➕ Новое дело
    ├── [Case List]
    │   └── Case Card (callback_data="case_open:<id>")
    │       ├── 💰 Кредиторы/должники
    │       ├── 🏠 Опись имущества
    │       ├── 📎 Документы по делу
    │       ├── ✏️ Редактировать
    │       ├── 💬 Помощь (ИИ)
    │       ├── 🔙 К списку дел
    │       └── ← Назад
    └── ← Назад (callback_data="main")
```

## Router Priority

```python
# 1. Commands (highest priority)
dp.include_router(cases_handlers.router)

# 2. FSM states with StateFilter
dp.include_router(newcase_fsm.router)

# 3. Callback handlers (refactored menu system)
dp.include_router(callback_router)

# 4. Direct dp handlers (lowest priority)
```

## Key Features

### 1. No Chat Spam
All navigation uses `edit_message_text` instead of sending new messages:
```python
async def safe_edit_message(call: CallbackQuery, text: str, reply_markup=None):
    """Safely edit message, handling all exceptions."""
    try:
        await call.message.edit_text(text=text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        # Handle "message is not modified" and other errors
        ...
```

### 2. Consistent Navigation
All menus have "← Назад" button that returns to main menu:
```python
kb.button(text="← Назад", callback_data="main")
```

### 3. FSM with Inline Keyboards
FSM flow now uses InlineKeyboardMarkup with Cancel and Skip buttons:
```python
# Cancel button (all steps)
new_case_cancel() → callback_data="cancel_fsm"

# Skip + Cancel buttons (optional steps)
new_case_skip_cancel() → callback_data="skip_step" or "cancel_fsm"
```

### 4. Backward Compatibility
Old function names still work via aliases:
```python
main_menu_kb = main_menu  # Old name → new function
home_ikb = main_menu
profile_ikb = profile_menu
```

## Testing

### Manual Testing Checklist
- [ ] `/start` command shows main menu
- [ ] Main menu buttons work (Profile, New Case, My Cases)
- [ ] Profile menu and submenus work
- [ ] My Cases shows case list
- [ ] New Case FSM flow works with inline keyboards
- [ ] Cancel button works in FSM
- [ ] Skip button works for optional steps
- [ ] All "← Back" buttons return to main menu
- [ ] No chat spam (messages are edited, not resent)
- [ ] Case card opens and shows options
- [ ] Help menu works

### Syntax Validation
```bash
# All files pass syntax check
python3 -m py_compile keyboards.py
python3 -m py_compile handlers/callbacks.py
python3 -m py_compile handlers/newcase_fsm.py
```

## Migration Notes

### For Bot Operators
1. No configuration changes required
2. No database changes required
3. Router priority is maintained
4. Old ReplyKeyboardMarkup removed (users will see only inline buttons)

### For Developers
1. All new menus should use `keyboards.py` functions
2. All new callbacks should go in `handlers/callbacks.py`
3. Use `safe_edit_message()` for editing messages
4. Follow callback_data naming convention:
   - `main` - main menu
   - `<section>` - top-level section (e.g., "profile", "my_cases")
   - `<section>_<action>` - section action (e.g., "profile_edit")
   - `<section>_<action>:<id>` - action with ID (e.g., "case_open:123")

## Known Limitations

1. Some placeholders remain for incomplete features:
   - Profile editing
   - Case editing
   - AI helper
   - Documents generation

2. Case database integration is partially implemented
   - `list_cases()` works
   - `get_case()` works
   - Case creation saves to database (TODO in FSM)

## Future Improvements

1. Add case creation database integration
2. Complete profile editing functionality
3. Add case editing functionality
4. Implement documents generation
5. Add AI helper integration
6. Add pagination for long case lists
7. Add search/filter in cases list

## Credits

Refactored by: Claude Code
Date: 2026-01-16
Branch: claude/refactor-menu-system-qdtKP
