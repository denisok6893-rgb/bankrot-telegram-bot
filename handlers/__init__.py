"""
Handlers package for bankrot-telegram-bot

This package contains organized handlers extracted from bot.py:
- callbacks.py: Callback query handlers (~58 handlers)
- cases.py: Case-related command handlers (existing, 475 lines)
- commands.py: General command handlers (to be created)
- fsm.py: FSM (Finite State Machine) handlers (to be created)

Refactoring strategy:
1. Extract callback handlers first (this reduces bot.py by ~1500-2000 lines)
2. Extract FSM handlers for multi-step flows
3. Extract command handlers
4. Keep only initialization code in bot.py

NOTE: Removed import of register_callbacks to break circular import chain:
  bot.py → handlers → handlers.callbacks → bot (circular!)
This was causing "Router is already attached" error.
"""

__all__ = []
