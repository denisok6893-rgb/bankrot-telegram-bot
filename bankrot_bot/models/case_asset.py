"""CaseAsset model for case property/assets inventory."""
from datetime import datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import BigInteger, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from bankrot_bot.database import Base


class CaseAsset(Base):
    """Case asset/property model."""
    __tablename__ = "case_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True, comment="ID дела")

    # Asset information
    kind: Mapped[str] = mapped_column(String(200), nullable=False, comment="Вид имущества (недвижимость, авто, акции и т.п.)")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="Описание имущества")
    qty_or_area: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Количество или площадь")
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True, comment="Стоимость")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Примечания")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        comment="Дата создания"
    )

    def __repr__(self) -> str:
        return f"<CaseAsset(id={self.id}, case_id={self.case_id}, kind='{self.kind}')>"

    def to_dict(self) -> dict:
        """Convert asset to dictionary."""
        return {
            "id": self.id,
            "case_id": self.case_id,
            "kind": self.kind,
            "description": self.description,
            "qty_or_area": self.qty_or_area,
            "value": float(self.value) if self.value else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
