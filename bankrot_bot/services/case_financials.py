"""Service layer for case financial data: assets and parties (creditors/debtors)."""
import logging
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bankrot_bot.models.case_asset import CaseAsset
from bankrot_bot.models.case_party import CaseParty

logger = logging.getLogger(__name__)


# ========== CaseParty (Кредиторы/Должники) ==========

async def get_case_parties(session: AsyncSession, case_id: int, role: Optional[str] = None) -> List[CaseParty]:
    """
    Получить список кредиторов/должников по делу.

    Args:
        session: AsyncSession
        case_id: ID дела
        role: Фильтр по роли ("creditor", "debtor") или None (все)

    Returns:
        Список CaseParty
    """
    stmt = select(CaseParty).where(CaseParty.case_id == case_id)
    if role:
        stmt = stmt.where(CaseParty.role == role)
    stmt = stmt.order_by(CaseParty.created_at.desc())

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_case_party(
    session: AsyncSession,
    case_id: int,
    role: str,
    name: str,
    amount: Decimal,
    basis: Optional[str] = None,
    currency: str = "RUB",
    notes: Optional[str] = None
) -> CaseParty:
    """Добавить кредитора/должника к делу."""
    party = CaseParty(
        case_id=case_id,
        role=role,
        name=name,
        amount=amount,
        basis=basis,
        currency=currency,
        notes=notes
    )
    session.add(party)
    await session.flush()
    return party


async def delete_case_party(session: AsyncSession, party_id: int, case_id: int) -> bool:
    """Удалить кредитора/должника (с проверкой принадлежности к делу)."""
    stmt = select(CaseParty).where(CaseParty.id == party_id, CaseParty.case_id == case_id)
    result = await session.execute(stmt)
    party = result.scalar_one_or_none()

    if not party:
        return False

    await session.delete(party)
    await session.flush()
    return True


def calculate_parties_totals(parties: List[CaseParty]) -> Dict[str, Decimal]:
    """
    Подсчитать итоги по контрагентам.

    Returns:
        dict с ключами: total_creditors, total_debtors, creditors_count, debtors_count
    """
    total_creditors = Decimal(0)
    total_debtors = Decimal(0)
    creditors_count = 0
    debtors_count = 0

    for p in parties:
        if p.role == "creditor":
            total_creditors += p.amount
            creditors_count += 1
        elif p.role == "debtor":
            total_debtors += p.amount
            debtors_count += 1

    return {
        "total_creditors": total_creditors,
        "total_debtors": total_debtors,
        "creditors_count": creditors_count,
        "debtors_count": debtors_count,
    }


def format_parties_for_doc(parties: List[CaseParty], role: str = "creditor") -> List[Dict]:
    """
    Преобразовать CaseParty в формат для генерации документа.

    Возвращает список словарей совместимых с существующими build_creditors_block().
    Формат: {name, debt_rubles, debt_kopeks, inn, ogrn, address, note}
    """
    result = []
    for p in parties:
        if p.role != role:
            continue

        amount = p.amount or Decimal(0)
        rubles = int(amount)
        kopeks = int((amount - rubles) * 100)

        result.append({
            "name": p.name,
            "debt_rubles": str(rubles),
            "debt_kopeks": f"{kopeks:02d}",
            "inn": "",  # В базовой схеме нет ИНН, можно расширить позже
            "ogrn": "",
            "address": "",
            "note": p.notes or "",
        })

    return result


# ========== CaseAsset (Имущество) ==========

async def get_case_assets(session: AsyncSession, case_id: int) -> List[CaseAsset]:
    """Получить список имущества по делу."""
    stmt = select(CaseAsset).where(CaseAsset.case_id == case_id).order_by(CaseAsset.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_case_asset(
    session: AsyncSession,
    case_id: int,
    kind: str,
    description: str,
    qty_or_area: Optional[str] = None,
    value: Optional[Decimal] = None,
    notes: Optional[str] = None
) -> CaseAsset:
    """Добавить имущество к делу."""
    asset = CaseAsset(
        case_id=case_id,
        kind=kind,
        description=description,
        qty_or_area=qty_or_area,
        value=value,
        notes=notes
    )
    session.add(asset)
    await session.flush()
    return asset


async def delete_case_asset(session: AsyncSession, asset_id: int, case_id: int) -> bool:
    """Удалить имущество (с проверкой принадлежности к делу)."""
    stmt = select(CaseAsset).where(CaseAsset.id == asset_id, CaseAsset.case_id == case_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()

    if not asset:
        return False

    await session.delete(asset)
    await session.flush()
    return True


def calculate_assets_total(assets: List[CaseAsset]) -> Decimal:
    """Подсчитать общую стоимость имущества."""
    total = Decimal(0)
    for a in assets:
        if a.value:
            total += a.value
    return total


# ========== Утилиты ==========

def parse_amount_input(text: str) -> Decimal:
    """
    Парсинг пользовательского ввода суммы.

    Принимает: "100000", "100 000", "100 000.50", "100000,50"
    Возвращает Decimal (или Decimal(0) при ошибке).

    Args:
        text: User input string with amount

    Returns:
        Parsed Decimal value, or Decimal(0) on parse error

    Examples:
        >>> safe_parse_decimal("100 000,50")
        Decimal('100000.50')
        >>> safe_parse_decimal("invalid")
        Decimal('0')
    """
    normalized = text.strip().replace(" ", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as e:
        # Expected errors: invalid decimal format
        logger.warning(f"Failed to parse decimal '{text}': {e}")
        return Decimal(0)
    except (AttributeError, TypeError) as e:
        # Unexpected: text is not a string (programmer error)
        logger.error(f"safe_parse_decimal called with invalid type {type(text)}: {e}")
        return Decimal(0)


def normalize_amount_to_string(text: str) -> Optional[str]:
    """
    Парсинг и нормализация суммы для JSON-safe хранения в FSM state.

    Принимает: "100000", "100 000", "100 000.50", "100000,50", "1 200 000"
    Возвращает нормализованную строку: "100000.00", "100000.50", "1200000.00" или None при ошибке.

    Эта функция безопасна для Redis FSM storage (JSON-serializable).

    Args:
        text: User input string with amount

    Returns:
        Normalized amount string with 2 decimal places, or None on error

    Examples:
        >>> normalize_amount_to_string("100 000,50")
        '100000.50'
        >>> normalize_amount_to_string("-500")
        None
        >>> normalize_amount_to_string("invalid")
        None
    """
    normalized = text.strip().replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(normalized)
        if amount < 0:
            logger.warning(f"Negative amount rejected: {text}")
            return None
        # Normalize to 2 decimal places as string
        return str(amount.quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError) as e:
        # Expected errors: invalid decimal format
        logger.warning(f"Failed to normalize amount '{text}': {e}")
        return None
    except (AttributeError, TypeError) as e:
        # Unexpected: text is not a string
        logger.error(f"normalize_amount_to_string called with invalid type {type(text)}: {e}")
        return None


def string_to_decimal(amount_str: str) -> Decimal:
    """
    Конвертация нормализованной строки обратно в Decimal для DB.

    Args:
        amount_str: Нормализованная строка вида "100000.00"

    Returns:
        Decimal значение, или Decimal(0) при ошибке

    Examples:
        >>> string_to_decimal("100000.50")
        Decimal('100000.50')
        >>> string_to_decimal("invalid")
        Decimal('0')
    """
    try:
        return Decimal(amount_str)
    except (InvalidOperation, ValueError) as e:
        # Expected errors: invalid decimal string
        logger.warning(f"Failed to convert '{amount_str}' to Decimal: {e}")
        return Decimal(0)
    except (AttributeError, TypeError) as e:
        # Unexpected: amount_str is not a string
        logger.error(f"string_to_decimal called with invalid type {type(amount_str)}: {e}")
        return Decimal(0)
