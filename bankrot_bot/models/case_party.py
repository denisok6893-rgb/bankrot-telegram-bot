"""CaseParty model for creditors and debtors."""
from datetime import datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import BigInteger, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from bankrot_bot.database import Base


class CaseParty(Base):
    """Case party (creditor/debtor) model."""
    __tablename__ = "case_parties"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True, comment="ID дела")

    # Party information
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True, comment="Роль: creditor или debtor")
    name: Mapped[str] = mapped_column(String(500), nullable=False, comment="Наименование/ФИО кредитора/должника")
    basis: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Основание требования/долга")
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0, comment="Сумма")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB", comment="Валюта")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Примечания")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        comment="Дата создания"
    )

    def __repr__(self) -> str:
        return f"<CaseParty(id={self.id}, case_id={self.case_id}, role='{self.role}', name='{self.name}')>"

    def to_dict(self) -> dict:
        """Convert party to dictionary."""
        return {
            "id": self.id,
            "case_id": self.case_id,
            "role": self.role,
            "name": self.name,
            "basis": self.basis,
            "amount": float(self.amount) if self.amount else 0,
            "currency": self.currency,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
