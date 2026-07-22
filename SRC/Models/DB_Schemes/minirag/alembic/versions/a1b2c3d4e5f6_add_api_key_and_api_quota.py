"""add_api_key_and_api_quota

Revision ID: a1b2c3d4e5f6
Revises: b0c6ccecc679
Create Date: 2026-05-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f3a9d12e0c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add api_key to users
    op.add_column('users', sa.Column('api_key', sa.String(), nullable=True))
    op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=True)
    
    # Add api_call_count to user_usage_quotas
    op.add_column('user_usage_quotas', sa.Column('api_call_count', sa.Integer(), server_default='0', nullable=False))

def downgrade() -> None:
    # Drop api_call_count from user_usage_quotas
    op.drop_column('user_usage_quotas', 'api_call_count')
    
    # Drop api_key from users
    op.drop_index(op.f('ix_users_api_key'), table_name='users')
    op.drop_column('users', 'api_key')
