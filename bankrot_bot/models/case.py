"""Case model for bankruptcy cases."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from bankrot_bot.database import Base


class CaseStage(str, enum.Enum):
    """Case stage enumeration."""
    OBSERVATION = "наблюдение"
    RESTRUCTURING = "реструктуризация"
    REALIZATION = "реализация"
    COMPLETED = "завершено"


class Case(Base):
    """Bankruptcy case model."""
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Telegram user ID")

    # Case information
    debtor_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="Имя должника")
    debtor_inn: Mapped[Optional[str]] = mapped_column(String(12), nullable=True, comment="ИНН должника")
    case_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Номер дела (А00-00000/0000)")
    court: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="Наименование суда")
    stage: Mapped[Optional[str]] = mapped_column(
        SQLEnum(CaseStage, native_enum=False, length=50),
        nullable=True,
        comment="Стадия банкротства"
    )
    manager_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="Арбитражный управляющий")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        comment="Дата создания"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Дата обновления"
    )

    def __repr__(self) -> str:
        return f"<Case(id={self.id}, debtor_name='{self.debtor_name}', case_number='{self.case_number}')>"

    def to_dict(self) -> dict:
        """Convert case to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "debtor_name": self.debtor_name,
            "debtor_inn": self.debtor_inn,
            "case_number": self.case_number,
            "court": self.court,
            "stage": self.stage.value if self.stage else None,
            "manager_name": self.manager_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def format_card(self) -> str:
        """Format case as a card for display."""
        lines = [
            f"📌 Дело #{self.id}",
            f"👤 Должник: {self.debtor_name}",
        ]

        if self.debtor_inn:
            lines.append(f"🔢 ИНН: {self.debtor_inn}")

        if self.case_number:
            lines.append(f"📋 Номер дела: {self.case_number}")

        if self.court:
            lines.append(f"⚖️ Суд: {self.court}")

        if self.stage:
            stage_emoji = {
                CaseStage.OBSERVATION: "👁",
                CaseStage.RESTRUCTURING: "🔄",
                CaseStage.REALIZATION: "💰",
                CaseStage.COMPLETED: "✅",
            }
            emoji = stage_emoji.get(self.stage, "📍")
            lines.append(f"{emoji} Стадия: {self.stage.value if isinstance(self.stage, CaseStage) else self.stage}")

        if self.manager_name:
            lines.append(f"👨‍💼 АУ: {self.manager_name}")

        lines.extend([
            f"",
            f"📅 Создано: {self.created_at.strftime('%d.%m.%Y %H:%M')}",
            f"🔄 Обновлено: {self.updated_at.strftime('%d.%m.%Y %H:%M')}",
        ])

        return "\n".join(lines)
