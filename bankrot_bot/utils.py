"""
Утилиты для форматирования и валидации данных.
"""
from typing import Any


def format_creditor_line(idx: int, creditor: dict[str, Any]) -> str:
    """
    Форматирует строку кредитора для отображения.

    Args:
        idx: Порядковый номер кредитора
        creditor: Словарь с данными кредитора

    Returns:
        Отформатированная строка
    """
    name = (creditor.get("name") or "Кредитор").strip()

    inn = str(creditor.get("inn") or "").strip()
    ogrn = str(creditor.get("ogrn") or "").strip()

    ids_parts = []
    if inn:
        ids_parts.append(f"ИНН {inn}")
    if ogrn:
        ids_parts.append(f"ОГРН {ogrn}")

    name_with_ids = name + (f" ({', '.join(ids_parts)})" if ids_parts else "")

    debt_r = creditor.get("debt_rubles")
    debt_k = creditor.get("debt_kopeks")
    note = str(creditor.get("note") or "").strip()

    parts = [f"{idx}) {name_with_ids}"]

    if debt_r not in (None, "", "-"):
        dr = "".join(ch for ch in str(debt_r) if ch.isdigit())
        if dr:
            parts.append(f" — {dr} руб.")

    if debt_k not in (None, "", "-"):
        dk = "".join(ch for ch in str(debt_k) if ch.isdigit())
        if dk:
            parts.append(f" {int(dk):02d} коп.")

    if note:
        parts.append(f" ({note})")

    return "".join(parts)


def humanize_missing_fields(missing: list[str], field_meta: dict[str, dict]) -> str:
    """
    Преобразует список отсутствующих полей в читаемую строку.

    Args:
        missing: Список ключей отсутствующих полей
        field_meta: Метаданные полей с названиями

    Returns:
        Строка с перечислением полей через запятую
    """
    titles = []
    for key in missing:
        meta = field_meta.get(key)
        if meta:
            titles.append(meta.get("title", key))
        else:
            titles.append(key)

    return ", ".join(titles)


def calculate_card_completion(card: dict[str, Any], required_fields: list[str]) -> tuple[int, int]:
    """
    Подсчитывает количество заполненных полей карточки.

    Args:
        card: Словарь с данными карточки
        required_fields: Список обязательных полей

    Returns:
        Кортеж (заполнено, всего)
    """
    filled = 0
    total = len(required_fields)

    for field in required_fields:
        val = card.get(field)
        if val is not None and str(val).strip() != "":
            filled += 1

    return filled, total


def safe_digits(s: str) -> str:
    """
    Извлекает только цифры из строки.

    Args:
        s: Исходная строка

    Returns:
        Строка, содержащая только цифры
    """
    return "".join(ch for ch in s if ch.isdigit())
