"""add case_assets and case_parties tables

Revision ID: 002
Revises: 001
Create Date: 2026-01-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create case_assets and case_parties tables."""
    # Create case_assets table
    op.create_table(
        'case_assets',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('case_id', sa.BigInteger(), nullable=False, comment='ID дела'),
        sa.Column('kind', sa.String(length=200), nullable=False, comment='Вид имущества (недвижимость, авто, акции и т.п.)'),
        sa.Column('description', sa.Text(), nullable=False, comment='Описание имущества'),
        sa.Column('qty_or_area', sa.String(length=100), nullable=True, comment='Количество или площадь'),
        sa.Column('value', sa.Numeric(precision=15, scale=2), nullable=True, comment='Стоимость'),
        sa.Column('notes', sa.Text(), nullable=True, comment='Примечания'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='Дата создания'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_assets_case_id'), 'case_assets', ['case_id'], unique=False)

    # Create case_parties table
    op.create_table(
        'case_parties',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('case_id', sa.BigInteger(), nullable=False, comment='ID дела'),
        sa.Column('role', sa.String(length=20), nullable=False, comment='Роль: creditor или debtor'),
        sa.Column('name', sa.String(length=500), nullable=False, comment='Наименование/ФИО кредитора/должника'),
        sa.Column('basis', sa.Text(), nullable=True, comment='Основание требования/долга'),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False, comment='Сумма'),
        sa.Column('currency', sa.String(length=3), nullable=False, comment='Валюта'),
        sa.Column('notes', sa.Text(), nullable=True, comment='Примечания'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='Дата создания'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_parties_case_id'), 'case_parties', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_parties_role'), 'case_parties', ['role'], unique=False)


def downgrade() -> None:
    """Drop case_assets and case_parties tables."""
    op.drop_index(op.f('ix_case_parties_role'), table_name='case_parties')
    op.drop_index(op.f('ix_case_parties_case_id'), table_name='case_parties')
    op.drop_table('case_parties')

    op.drop_index(op.f('ix_case_assets_case_id'), table_name='case_assets')
    op.drop_table('case_assets')
