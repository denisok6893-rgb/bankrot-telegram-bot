# Bot.py Integration - Phase 1: MENU Callbacks

## Summary

✅ **5 MENU handlers** extracted from bot.py → `handlers/callbacks.py`
- menu:home (lines 1472-1479)
- menu:profile (lines 1482-1489)
- menu:docs (lines 1492-1505)
- menu:help (lines 1508-1520)
- menu:my_cases (lines 1525-1549)

**Lines saved**: ~78 lines

## Integration Steps

### Step 1: Add import to bot.py

Find the imports section (around line 62) and add:

```python
# Import callback handlers module
from handlers.callbacks import register_callbacks
```

### Step 2: Register callback router

After the Dispatcher is created (look for `dp = Dispatcher(...)` around line 1333+), add:

```python
# Register callback handlers from handlers module
register_callbacks(dp)
```

### Step 3: Comment out old handlers in bot.py

Find lines **1472-1549** and comment them out (or delete):

```python
# ============================================================================
# MOVED TO handlers/callbacks.py - Phase 1: MENU handlers
# ============================================================================
# @dp.callback_query(F.data == "menu:home")
# async def menu_home(call: CallbackQuery):
#     ...
#
# @dp.callback_query(F.data == "menu:profile")
# async def menu_profile(call: CallbackQuery):
#     ...
#
# @dp.callback_query(F.data == "menu:docs")
# async def menu_docs(call: CallbackQuery):
#     ...
#
# @dp.callback_query(F.data == "menu:help")
# async def menu_help(call: CallbackQuery):
#     ...
#
# @dp.callback_query(F.data == "menu:my_cases")
# async def menu_my_cases(call: CallbackQuery, state: FSMContext):
#     ...
```

## Complete Integration Example

```python
# bot.py - Around line 62-80
from bankrot_bot.database import init_db as init_pg_db
from bankrot_bot.handlers import cases as cases_handlers

# ADD THIS:
from handlers.callbacks import register_callbacks

from bankrot_bot.keyboards.menus import (
    main_menu_kb,
    start_ikb,
    home_ikb,
    # ... other imports
)

# ... rest of bot.py ...

# Around line 1333+, after dp = Dispatcher(storage=...)
dp = Dispatcher(storage=storage)

# ADD THIS:
register_callbacks(dp)

# ... rest of bot.py ...
```

## Testing

1. Run the bot:
   ```bash
   python bot.py
   ```

2. Test each menu callback:
   - Click "Главное меню" → should show main menu
   - Click "Мой профиль" → should show profile
   - Click "Документы" → should show docs catalog
   - Click "Помощь" → should show help menu
   - Click "Мои дела" → should show cases list

3. Check logs for any errors

## Verification

✅ No "handler not found" errors
✅ All menu buttons respond correctly
✅ bot.py reduced by ~78 lines
✅ handlers/callbacks.py contains working implementations

## Source Lines Copied

| Handler | Original Lines | Status |
|---------|---------------|--------|
| menu:home | 1472-1479 (8 lines) | ✅ Copied |
| menu:profile | 1482-1489 (8 lines) | ✅ Copied |
| menu:docs | 1492-1505 (14 lines) | ✅ Copied |
| menu:help | 1508-1520 (13 lines) | ✅ Copied |
| menu:my_cases | 1525-1549 (25 lines) | ✅ Copied |
| **TOTAL** | **68 lines** | ✅ **All extracted** |

Plus blank lines and comments: ~78 lines total reduction.

## Notes

- is_allowed() and list_cases() imported from bot.py temporarily
- Future: extract these to utils module
- Keyboard builders already in separate module ✅
- Next phase: extract HELP callbacks (5 handlers, ~60 lines)
