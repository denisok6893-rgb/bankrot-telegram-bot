"""
Shared utilities to break circular imports.

This module contains functions that are imported by both bot.py and handlers,
preventing circular dependency chains.

All functions follow strict type-safety and error handling standards.
"""
from typing import Set
import logging

logger = logging.getLogger(__name__)

# ============================================
# Authorization (moved from bot.py to break circular imports)
# ============================================
_allowed_users: Set[int] = set()
_admin_users: Set[int] = set()


def init_allowed_users(allowed: Set[int], admins: Set[int]) -> None:
    """
    Initialize allowed and admin user sets.

    Must be called once during bot startup BEFORE any handlers execute.

    Args:
        allowed: Set of user IDs allowed to use bot
        admins: Set of user IDs with admin privileges (superset of allowed)

    Example:
        >>> init_allowed_users({123456, 789012}, {123456})
        >>> is_allowed(123456)  # True
        >>> is_admin(789012)    # False
    """
    global _allowed_users, _admin_users
    _allowed_users = allowed
    _admin_users = admins
    logger.info(f"Initialized authorization: {len(allowed)} allowed users, {len(admins)} admins")


def is_allowed(user_id: int) -> bool:
    """
    Check if user is authorized to use bot.

    Args:
        user_id: Telegram user ID

    Returns:
        True if user is in allowed list or admins list

    Note:
        All admins are automatically allowed (admins ⊆ allowed)
    """
    return user_id in _allowed_users or user_id in _admin_users


def is_admin(user_id: int) -> bool:
    """
    Check if user has admin privileges.

    Args:
        user_id: Telegram user ID

    Returns:
        True if user is in admin list
    """
    return user_id in _admin_users


def get_allowed_users() -> Set[int]:
    """
    Get copy of allowed users set.

    Returns:
        Copy of allowed users (modifications won't affect original)
    """
    return _allowed_users.copy()


def get_admin_users() -> Set[int]:
    """
    Get copy of admin users set.

    Returns:
        Copy of admin users (modifications won't affect original)
    """
    return _admin_users.copy()
