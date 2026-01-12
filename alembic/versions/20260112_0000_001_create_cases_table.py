"""create cases table

Revision ID: 001
Revises:
Create Date: 2026-01-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cases table."""
    op.create_table(
        'cases',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='Telegram user ID'),
        sa.Column('debtor_name', sa.String(length=500), nullable=False, comment='Имя должника'),
        sa.Column('debtor_inn', sa.String(length=12), nullable=True, comment='ИНН должника'),
        sa.Column('case_number', sa.String(length=50), nullable=True, comment='Номер дела (А00-00000/0000)'),
        sa.Column('court', sa.String(length=500), nullable=True, comment='Наименование суда'),
        sa.Column('stage', sa.String(length=50), nullable=True, comment='Стадия банкротства'),
        sa.Column('manager_name', sa.String(length=500), nullable=True, comment='Арбитражный управляющий'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='Дата создания'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, comment='Дата обновления'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cases_user_id'), 'cases', ['user_id'], unique=False)


def downgrade() -> None:
    """Drop cases table."""
    op.drop_index(op.f('ix_cases_user_id'), table_name='cases')
    op.drop_table('cases')
