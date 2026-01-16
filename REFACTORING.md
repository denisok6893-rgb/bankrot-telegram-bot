# Bot.py Refactoring Progress

## Goal
Extract handlers from bot.py into modular files in `handlers/` directory for better maintainability.

## Branch Strategy
**Main refactor branch**: `claude/add-case-callbacks-phase-8-e3i3K`

## Progress Overview

### Callback Handlers (handlers/callbacks.py)
**Total in bot.py**: ~58 callbacks
**Migrated**: 14 callbacks (24%)
**Remaining**: ~44 callbacks

| Phase | Category | Handlers | Status | Commit |
|-------|----------|----------|--------|--------|
| 8 | CASE (part 1) | 5 | ✅ Complete | f338312 |
| 9 | CASE (part 2) | 4 | ✅ Complete | 150487e |
| 10 | PROFILE + AI/MISC | 5 | ✅ Complete | 7f10311 |

### Completed Handlers

#### CASE Callbacks (9 handlers) ✅
1. `case:edit:` (count==2) - Edit menu shell (bot.py:2072-2166)
2. `case:file:` - File send (bot.py:2347-2373)
3. `case:open:` - Open case (bot.py:2694-2735)
4. `case:card:` - Card open (bot.py:2738-2773)
5. `case:card:` - Card menu (bot.py:3037-3048)
6. `case:card_edit:` - Card edit (bot.py:3050-3085)
7. `case:cardfield:` - Card field start (bot.py:3127-3155)
8. `case:creditors:` - Creditors menu (bot.py:3312-3324)
9. `case:edit:` (count==3) - Case edit start + FSM (bot.py:3591-3682)

#### PROFILE Callbacks (2 handlers) ✅
1. `profile:menu` - Show profile (bot.py:2198-2227)
2. `profile:edit` - Start profile editing FSM (bot.py:2228-2238)

#### AI/MISC Callbacks (3 handlers) ✅
1. `ai:placeholder` - AI feature placeholder (bot.py:1552-1560)
2. `noop` - No-operation callback (bot.py:1999-2001)
3. `back:main` - Back to main menu (bot.py:2385-2388)

### Remaining Handlers (~44)

#### High Priority
- [ ] Navigation callbacks (case:list, case:new, back:cases, docs:back_menu)
- [ ] Docs callbacks (docs:choose_case, docs:case:*, docs:petition:*)
- [ ] Creditors FSM callbacks (creditors:add:*, creditors:del:*, creditors:delone:*, creditors:text:*, creditors:text_clear:*)
- [ ] Card fill callbacks (card:fill:*)

#### Medium Priority
- [ ] Party/Asset/Debt callbacks (FSM-based)
- [ ] Document generation callbacks
- [ ] Archive callbacks

#### Low Priority
- [ ] Misc navigation and utility callbacks

## File Structure

```
handlers/
├── __init__.py          # Package init with register_callbacks()
├── callbacks.py         # Callback query handlers (14/58 migrated)
└── cases.py            # Existing case command handlers (475 lines)
```

## Integration Status

### Current State
- ✅ handlers/ directory created
- ✅ handlers/__init__.py created
- ✅ handlers/callbacks.py created with 14 handlers
- ⚠️ NOT yet integrated into bot.py (handlers not registered)

### Integration Steps (TODO)
1. Add imports to bot.py
2. Remove migrated handlers from bot.py
3. Register handlers via `register_callbacks(dp)`
4. Test all migrated functionality
5. Deploy to Timeweb

## Statistics

| Metric | Value |
|--------|-------|
| Total callbacks in bot.py | 58 |
| Migrated to handlers/callbacks.py | 14 |
| Progress | 24% |
| Lines in bot.py | ~4,000+ |
| Lines in handlers/callbacks.py | 509 |
| Estimated reduction after full migration | ~1,500-2,000 lines |

## Next Steps

### Phase 11: Navigation Callbacks (next 5)
- [ ] `case:list` - List all cases
- [ ] `case:new` - Create new case
- [ ] `back:cases` - Back to cases menu
- [ ] `docs:back_menu` - Back to docs menu
- [ ] `docs:choose_case` - Choose case for docs

### Phase 12: Docs & Creditors Callbacks
- Continue extracting remaining patterns

## Notes
- All changes are incremental and Timeweb-safe
- Each phase committed separately for easy rollback
- Exact code copied from bot.py with source line references
- No breaking changes to existing functionality
