# Phase 1 Integration: Menu Callbacks

## What Was Done

✅ Extracted 5 MENU callback handlers from bot.py:
- `menu:home` (line 1472-1479)
- `menu:profile` (line 1482-1489)
- `menu:docs` (line 1492-1505)
- `menu:help` (line 1508-1520)
- `menu:my_cases` (line 1525-1549)

✅ Created `handlers/callbacks.py` with implementations

## Dependencies Issue

The handlers need these from bot.py:
- `is_allowed(uid)` - permission check function (line 927)
- `list_cases(owner_user_id, limit)` - database query function (line 1036)

## Integration Options

### Option 1: Create utils module (RECOMMENDED)

Create `utils/permissions.py` and `utils/database.py`:

```python
# utils/permissions.py
def is_allowed(uid: int) -> bool:
    """Move from bot.py:927"""
    # Implementation from bot.py
    pass

# utils/queries.py
def list_cases(owner_user_id: int, limit: int = 20):
    """Move from bot.py:1036"""
    # Implementation from bot.py
    pass
```

Then update `handlers/callbacks.py`:
```python
from utils.permissions import is_allowed
from utils.queries import list_cases
```

### Option 2: Pass via router.callback_query decorator (middleware)

Use aiogram middleware to inject is_allowed as a dependency.

### Option 3: Import from bot (TEMPORARY - works now)

For quick testing, update `handlers/callbacks.py`:

```python
# At the top, add:
import sys
sys.path.insert(0, '/home/user/bankrot-telegram-bot')
from bot import is_allowed, list_cases
```

**Then uncomment the permission checks in each handler.**

## How to Test (Option 3 - Quick Test)

1. **Update handlers/callbacks.py imports:**

```python
# Add after existing imports:
import sys
sys.path.insert(0, '/home/user/bankrot-telegram-bot')
from bot import is_allowed, list_cases
```

2. **Uncomment all the permission checks** in the 5 menu handlers

3. **Register in bot.py** (add after line 1333 or at end of imports):

```python
# Import the callback router
from handlers.callbacks import callback_router

# Register the router BEFORE defining handlers
# (Add after dp = Dispatcher(storage=...) line)
dp.include_router(callback_router)
```

4. **Comment out the OLD handlers** in bot.py:

Find lines 1472-1549 and wrap them:
```python
# ========== OLD HANDLERS - MOVED TO handlers/callbacks.py ==========
# @dp.callback_query(F.data == "menu:home")
# async def menu_home(call: CallbackQuery):
#     ...
# ... (all 5 handlers)
```

5. **Test the bot:**

```bash
python bot.py
```

Try clicking menu buttons to verify the handlers work.

## Verification Checklist

- [ ] Menu navigation works (home button)
- [ ] Profile button shows profile
- [ ] Docs button shows document catalog
- [ ] Help button shows help menu
- [ ] My Cases button shows cases list
- [ ] No "handler not found" errors in logs

## Next Steps After Testing

Once confirmed working:
1. Extract is_allowed and list_cases to proper modules
2. Extract next batch: HELP callbacks (5 handlers)
3. Extract DOCS callbacks (2 handlers)
4. Continue with CASE callbacks (20+ handlers)

## File Changes Summary

```
NEW FILES:
+ handlers/callbacks.py (menu handlers)
+ INTEGRATION_PHASE1.md (this file)

MODIFIED FILES (after integration):
~ bot.py (add router registration, comment out old handlers)
~ handlers/callbacks.py (uncomment permission checks after imports added)
```

## Code Snippets for bot.py

### Add to imports section (around line 80):

```python
# Import callback handlers
from handlers.callbacks import callback_router
```

### Add after Dispatcher creation (around line 1333+):

```python
# Register callback router from handlers module
dp.include_router(callback_router)
```

### Comment out old handlers (lines 1472-1549):

```python
# ============================================================================
# MOVED TO handlers/callbacks.py - Phase 1 Refactoring
# ============================================================================
# @dp.callback_query(F.data == "menu:home")
# async def menu_home(call: CallbackQuery):
#     uid = call.from_user.id
#     if not is_allowed(uid):
#         await call.answer()
#         return
#     await call.message.answer("Главное меню:", reply_markup=home_ikb())
#     await call.answer()
#
# ... rest of handlers commented out ...
```

## Diff Preview

This will reduce bot.py by approximately **78 lines** (5 handlers × ~15 lines each).

After all 58 callbacks are extracted, bot.py will reduce by ~1500-2000 lines.
