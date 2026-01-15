# Bot.py Refactoring Guide

## Current State
- **bot.py**: 4332 lines (MONOLITHIC - too large!)
- **handlers/cases.py**: 475 lines (already extracted ✓)
- **services/**: docx_forms.py, database.py (working ✓)

## Problem
bot.py is unmaintainable at 4332 lines. Need to extract handlers into modules.

## Refactoring Strategy

### Phase 1: Extract Callback Handlers ✓ SKELETON CREATED
**Target**: Reduce bot.py by ~1500-2000 lines

**Status**: Skeleton created in `handlers/callbacks.py`

**58 callback handlers identified:**
```python
# Menu callbacks (5): menu:home, menu:profile, menu:docs, menu:help, menu:my_cases
# Help callbacks (5): help:howto, help:cases, help:docs, help:contacts, help:about
# Docs callbacks (2): docs_cat:*, docs_item:*
# Profile callbacks (1): profile:cases
# Case callbacks (20+): case:open:*, case:docs:*, case:gen:*, case:file:*, etc.
# AI/Misc (2): ai:placeholder, noop
```

**Line ranges in bot.py** (found via grep):
- Callbacks start: ~line 1472
- Callbacks end: ~line 2100+ (estimated)

**Next steps:**
1. Copy each handler function from bot.py to handlers/callbacks.py
2. Remove TODO comments and add actual implementation
3. Test each group (menu, help, docs, cases) incrementally
4. Import and register in bot.py: `from handlers.callbacks import register_callbacks`

### Phase 2: Extract FSM Handlers (Future)
**Target**: Multi-step conversation flows

**FSM States to extract** (search for `State` and `StatesGroup` in bot.py):
- AddCase (bankruptcy case creation flow)
- AddParty (creditor/debtor party flow)
- AddAsset (asset addition flow)
- AddDebt (debt addition flow)
- EditCase (case editing flow)

**Create**: `handlers/fsm.py` with FSM handlers

### Phase 3: Extract Command Handlers (Future)
**Target**: Simple command handlers

**Commands to extract** (search for `@dp.message(Command` in bot.py):
- /start
- /help
- /menu
- /cases
- /newcase
- /profile
- etc.

**Create**: `handlers/commands.py`

### Phase 4: Extract Message Handlers (Future)
**Target**: Text/media message handlers

**Create**: `handlers/messages.py` for non-command messages

### Phase 5: Final Cleanup
- bot.py should only contain:
  - Imports and configuration
  - Bot/Dispatcher initialization
  - Router registration
  - Main polling loop
- Target: **bot.py < 300 lines**

## File Structure (Target)

```
bankrot-telegram-bot/
├── bot.py (< 300 lines: init + main only)
├── handlers/
│   ├── __init__.py
│   ├── callbacks.py (~800 lines: 58 handlers)
│   ├── cases.py (475 lines: exists ✓)
│   ├── commands.py (~400 lines: to create)
│   ├── fsm.py (~600 lines: to create)
│   └── messages.py (~300 lines: to create)
├── services/
│   ├── database.py (✓ working)
│   ├── docx_forms.py (✓ working)
│   └── keyboards.py (to create: extract keyboard builders)
└── config/
    └── settings.py (to create: extract config)
```

## Implementation Checklist

### Phase 1: Callbacks (CURRENT)
- [x] Create handlers/ directory
- [x] Create handlers/__init__.py
- [x] Create handlers/callbacks.py skeleton
- [ ] Extract menu:* handlers (5 handlers)
- [ ] Extract help:* handlers (5 handlers)
- [ ] Extract docs_* handlers (2 handlers)
- [ ] Extract profile:* handlers (1 handler)
- [ ] Extract case:* handlers (20+ handlers)
- [ ] Extract AI/misc handlers (2 handlers)
- [ ] Test callback handlers
- [ ] Register in bot.py
- [ ] Verify all callbacks work
- [ ] Commit and push

### Phase 2-5: TBD
(To be planned after Phase 1 completion)

## Testing Strategy

1. **Incremental testing**: Test each category as you extract it
2. **Keep bot.py running**: Don't remove handlers until new ones are tested
3. **Use existing test**: Decimal test (500006.68 → DOCX) should still pass
4. **Verification**:
   - All menu navigation works
   - Case creation works
   - Document generation works
   - No callback errors in logs

## Safety Rules

1. **NO full bot.py reads**: File is too large (4332 lines)
2. **Use grep/targeted reads**: Extract specific line ranges
3. **One category at a time**: Don't extract everything at once
4. **Test after each extraction**: Verify functionality
5. **Keep backups**: Use git branches for each phase

## Current Branch
- Working on: `claude/refactor-bot-py-GMLAX`
- Merged: `claude/fix-decimal-serialization-bc9cQ` → main ✓

## Grep Patterns for Extraction

```bash
# Find all callback handlers
grep -n "^@dp.callback_query" bot.py

# Find callback by prefix
grep -n "@dp.callback_query.*menu:" bot.py

# Find FSM states
grep -n "class.*StatesGroup" bot.py

# Find command handlers
grep -n "@dp.message.*Command" bot.py

# Get function signature
grep -A1 "@dp.callback_query.*menu:home" bot.py
```

## Notes
- ✅ Services layer (database, docx_forms) already working
- ✅ Decimal serialization fix merged
- ✅ Test infrastructure exists
- 🎯 Focus: Extract callbacks first (biggest win)
