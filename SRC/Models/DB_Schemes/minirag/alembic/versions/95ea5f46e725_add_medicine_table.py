"""Add Medicine table

Revision ID: 95ea5f46e725
Revises: 7a3e1f9c4b02
Create Date: 2026-03-29 21:09:35.559237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '95ea5f46e725'
down_revision: Union[str, None] = '7a3e1f9c4b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'medicines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_name', sa.String(), nullable=False),
        sa.Column('active_ingredient', sa.String(), nullable=True),
        sa.Column('pharmacological_class', sa.String(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('dosage_form', sa.String(), nullable=True),
        sa.Column('raw_description', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_medicines_active_ingredient'), 'medicines', ['active_ingredient'], unique=False)
    op.create_index(op.f('ix_medicines_id'), 'medicines', ['id'], unique=False)
    op.create_index(op.f('ix_medicines_trade_name'), 'medicines', ['trade_name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_medicines_trade_name'), table_name='medicines')
    op.drop_index(op.f('ix_medicines_id'), table_name='medicines')
    op.drop_index(op.f('ix_medicines_active_ingredient'), table_name='medicines')
    op.drop_table('medicines')
