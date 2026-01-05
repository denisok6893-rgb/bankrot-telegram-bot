from __future__ import annotations

from typing import Any


def build_creditors_header_block(creditors: list[dict] | None) -> str:
    creditors = creditors or []
    if not creditors:
        return "Сведения о кредиторах не представлены."

    names: list[str] = []
    for c in creditors:
        name = str((c or {}).get("name") or "").strip()
        if name:
            names.append(name)

    if not names:
        return "Сведения о кредиторах не представлены."

    if len(names) <= 3:
        return ", ".join(names)
    return ", ".join(names[:3]) + f" и др. (всего {len(names)})"


def build_creditors_block(creditors: list[dict] | None) -> str:
    creditors = creditors or []
    if not creditors:
        return "Сведения о кредиторах не представлены."

    out: list[str] = []
    for i, c in enumerate(creditors, start=1):
        c = c or {}

        name = str(c.get("name") or "").strip() or "Кредитор"
        inn = str(c.get("inn") or "").strip()
        ogrn = str(c.get("ogrn") or "").strip()
        address = str(c.get("address") or "").strip()
        note = str(c.get("note") or "").strip()

        debt_r = str(c.get("debt_rubles") or "").strip()
        debt_k_raw = "" if c.get("debt_kopeks") is None else str(c.get("debt_kopeks")).strip()
        digits = "".join(ch for ch in debt_k_raw if ch.isdigit())
        debt_k = f"{int(digits):02d}" if digits else "00"

        parts = [name]
        if inn:
            parts.append(f"ИНН {inn}")
        if ogrn:
            parts.append(f"ОГРН {ogrn}")
        if address:
            parts.append(f"адрес: {address}")

        line = f"{i}) " + ", ".join(parts)

        if debt_r or digits:
            line += f"; сумма задолженности: {debt_r or '0'} руб. {debt_k} коп."

        if note:
            line += f"; прим.: {note}"

        # быстрый фикс, если в тексте оказались слэши/экранирования
        line = line.replace('\\\\', '"').replace('\\"', '"')

        out.append(line)

    return "\n".join(out)


def sum_creditors_total(creditors: list[dict] | None) -> tuple[int, int]:
    creditors = creditors or []
    total_r = 0
    total_k = 0

    for c in creditors:
        c = c or {}

        r = c.get("debt_rubles")
        k = c.get("debt_kopeks")

        try:
            rr = int(str(r).strip()) if str(r).strip() else 0
        except Exception:
            rr = 0

        kk_raw = "" if k is None else str(k).strip()
        digits = "".join(ch for ch in kk_raw if ch.isdigit())
        try:
            kk = int(digits) if digits else 0
        except Exception:
            kk = 0

        total_r += rr
        total_k += kk

    total_r += total_k // 100
    total_k = total_k % 100
    return total_r, total_k


def build_vehicle_block(card: dict) -> str:
    # пока безопасный дефолт
    return ""


def build_attachments_list(card: dict) -> str:
    # пока безопасный дефолт
    return ""
