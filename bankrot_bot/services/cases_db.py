"""
SQLite database functions for case management.

This module breaks circular imports between bot.py and handlers by providing
shared database access functions that can be imported by both.

All functions use SQLite3 for the legacy database system.
"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple

logger = logging.getLogger(__name__)

# Will be set by init_cases_db() during bot startup
_DB_PATH: str | None = None


def init_cases_db(db_path: str) -> None:
    """
    Initialize cases database module with DB path.

    Must be called once during bot startup before any database functions are used.

    Args:
        db_path: Path to SQLite database file

    Example:
        >>> init_cases_db("/data/bankrot.db")
    """
    global _DB_PATH
    _DB_PATH = db_path
    logger.info(f"Cases DB module initialized with path: {db_path}")


def get_db_path() -> str:
    """
    Get database path.

    Returns:
        Database path

    Raises:
        RuntimeError: If init_cases_db() not called
    """
    if _DB_PATH is None:
        raise RuntimeError(
            "Database path not initialized. Call init_cases_db() before using database functions."
        )
    return _DB_PATH


# ============================================
# Helper functions
# ============================================
def _now() -> str:
    """Get current timestamp as string."""
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ============================================
# Constants
# ============================================
CASE_CARDS_ALLOWED_COLUMNS = frozenset([
    "data", "court_address", "judge_name", "debtor_full_name"
])

CASE_CARD_REQUIRED_FIELDS = [
    "court_name",
    "court_address",
    "debtor_full_name",
    "debtor_last_name",
    "debtor_first_name",
    "debtor_gender",
    "debtor_birth_date",
    "debtor_address",
    "passport_series",
    "passport_number",
    "passport_issued_by",
    "passport_date",
    "passport_code",
    "total_debt_rubles",
    "total_debt_kopeks",
]


# ============================================
# Database schema migration
# ============================================
def migrate_case_cards_table(con: sqlite3.Connection | None = None) -> set[str]:
    """
    Safely migrate case_cards table schema.

    Adds missing columns from CASE_CARDS_ALLOWED_COLUMNS whitelist.

    Args:
        con: Optional database connection (creates new if None)

    Returns:
        Set of current column names after migration

    Security:
        Column names validated against whitelist to prevent SQL injection
    """
    close_con = con is None
    if con is None:
        con = sqlite3.connect(get_db_path())

    cur = con.cursor()
    cur.execute("PRAGMA table_info(case_cards)")
    cols = {row[1] for row in cur.fetchall()}

    # Add missing columns (WHITELIST validation)
    for col in CASE_CARDS_ALLOWED_COLUMNS:
        if col not in cols:
            # Safe: col is from trusted whitelist, not user input
            # SQLite doesn't support parameterized ALTER TABLE
            if not col.isidentifier():  # Extra safety check
                logger.error(f"Invalid column name rejected: {col}")
                raise ValueError(f"Invalid column name: {col}")

            cur.execute(f"ALTER TABLE case_cards ADD COLUMN {col} TEXT")
            logger.info(f"Added column {col} to case_cards table")

    con.commit()

    # Return updated column list
    cur.execute("PRAGMA table_info(case_cards)")
    result = {row[1] for row in cur.fetchall()}

    if close_con:
        con.close()

    return result


# ============================================
# Case CRUD operations
# ============================================
def create_case(owner_user_id: int, code_name: str) -> int:
    """
    Create a new case.

    Args:
        owner_user_id: User ID of case owner
        code_name: Code name for the case

    Returns:
        ID of newly created case
    """
    now = _now()
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO cases (owner_user_id, code_name, created_at, updated_at) VALUES (?,?,?,?)",
            (owner_user_id, code_name.strip(), now, now),
        )
        con.commit()
        return int(cur.lastrowid)


def list_cases(owner_user_id: int, limit: int = 20) -> List[Tuple]:
    """
    Get list of user's cases.

    Args:
        owner_user_id: User ID of case owner
        limit: Maximum number of cases (default 20)

    Returns:
        List of tuples: (id, code_name, case_number, stage, updated_at)
    """
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id, code_name, case_number, stage, updated_at "
            "FROM cases WHERE owner_user_id=? ORDER BY id DESC LIMIT ?",
            (owner_user_id, limit),
        )
        return cur.fetchall()


def get_case(owner_user_id: int, cid: int) -> Tuple | None:
    """
    Get full case information.

    Args:
        owner_user_id: User ID of case owner
        cid: Case ID

    Returns:
        Tuple with case data or None if not found
    """
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, owner_user_id, code_name, case_number, court, judge, fin_manager,
                   stage, notes, created_at, updated_at
              FROM cases
             WHERE owner_user_id = ?
               AND id = ?
            """,
            (owner_user_id, cid),
        )
        return cur.fetchone()


def update_case_fields(
    owner_user_id: int,
    cid: int,
    *,
    case_number: str | None = None,
    court: str | None = None,
    judge: str | None = None,
    fin_manager: str | None = None,
) -> None:
    """
    Update case fields.

    Args:
        owner_user_id: User ID of case owner
        cid: Case ID
        case_number: Case number
        court: Court name
        judge: Judge name
        fin_manager: Financial manager name
    """
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            """
            UPDATE cases
               SET case_number = COALESCE(?, case_number),
                   court = COALESCE(?, court),
                   judge = COALESCE(?, judge),
                   fin_manager = COALESCE(?, fin_manager),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
               AND owner_user_id = ?
            """,
            (case_number, court, judge, fin_manager, cid, owner_user_id),
        )
        con.commit()


def update_case_meta(
    owner_user_id: int,
    cid: int,
    *,
    stage: str | None = None,
    notes: str | None = None,
) -> None:
    """
    Update case metadata.

    Args:
        owner_user_id: User ID of case owner
        cid: Case ID
        stage: Case stage
        notes: Case notes
    """
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            """
            UPDATE cases
               SET stage = COALESCE(?, stage),
                   notes = COALESCE(?, notes),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
               AND owner_user_id = ?
            """,
            (stage, notes, cid, owner_user_id),
        )
        con.commit()


# ============================================
# Case card operations
# ============================================
def _compose_debtor_full_name(data: dict[str, Any]) -> str | None:
    """Compose full debtor name from individual fields."""
    last = (data.get("debtor_last_name") or "").strip()
    first = (data.get("debtor_first_name") or "").strip()
    middle = (data.get("debtor_middle_name") or "").strip()
    parts = [p for p in (last, first, middle) if p]
    return " ".join(parts) if parts else None


def get_case_card(owner_user_id: int, cid: int) -> dict[str, Any]:
    """
    Get case card with debtor data.

    Args:
        owner_user_id: User ID of case owner
        cid: Case ID

    Returns:
        Dictionary with case card data
    """
    migrate_case_cards_table()
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT data, court_name, court_address, judge_name, debtor_full_name
              FROM case_cards
             WHERE owner_user_id = ?
               AND case_id = ?
            """,
            (owner_user_id, cid),
        )
        row = cur.fetchone()

    base: dict[str, Any] = {}
    if row:
        raw_data, court_name, court_address, judge_name, debtor_full_name = row
        if raw_data:
            try:
                base = json.loads(raw_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse case card JSON for case_id={cid}: {e}")
                base = {}
        if court_name and not base.get("court_name"):
            base["court_name"] = court_name
        if court_address and not base.get("court_address"):
            base["court_address"] = court_address
        if judge_name and not base.get("judge_name"):
            base["judge_name"] = judge_name
        if debtor_full_name and not base.get("debtor_full_name"):
            base["debtor_full_name"] = debtor_full_name

    for field in CASE_CARD_REQUIRED_FIELDS:
        base.setdefault(field, None)

    if base.get("debtor_full_name") is None:
        base["debtor_full_name"] = _compose_debtor_full_name(base)

    return base


def validate_case_card(card: dict[str, Any]) -> dict[str, list[str]]:
    """
    Validate case card.

    Args:
        card: Dictionary with case card data

    Returns:
        Dictionary with "missing" key containing list of missing fields
    """
    missing = []
    for field in CASE_CARD_REQUIRED_FIELDS:
        val = card.get(field)
        if val is None or str(val).strip() == "":
            missing.append(field)
    return {"missing": missing}


# ============================================
# Profile operations
# ============================================
def get_profile(owner_user_id: int) -> tuple | None:
    """
    Get user profile.

    Args:
        owner_user_id: User ID

    Returns:
        Tuple with profile data or None
    """
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT owner_user_id, full_name, role, address, phone, email, created_at, updated_at "
            "FROM profiles WHERE owner_user_id=?",
            (owner_user_id,),
        )
        return cur.fetchone()


def upsert_profile(
    owner_user_id: int,
    *,
    full_name: str | None = None,
    role: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> None:
    """
    Insert or update user profile.

    Args:
        owner_user_id: User ID
        full_name: Full name
        role: User role
        address: Address
        phone: Phone number
        email: Email address
    """
    with sqlite3.connect(get_db_path()) as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO profiles (owner_user_id, full_name, role, address, phone, email, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(owner_user_id) DO UPDATE SET
                full_name = COALESCE(excluded.full_name, profiles.full_name),
                role      = COALESCE(excluded.role, profiles.role),
                address   = COALESCE(excluded.address, profiles.address),
                phone     = COALESCE(excluded.phone, profiles.phone),
                email     = COALESCE(excluded.email, profiles.email),
                updated_at = CURRENT_TIMESTAMP
            """,
            (owner_user_id, full_name, role, address, phone, email),
        )
        con.commit()
