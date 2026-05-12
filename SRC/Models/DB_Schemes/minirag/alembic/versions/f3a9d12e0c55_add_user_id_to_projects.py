"""add_user_id_to_projects

Revision ID: f3a9d12e0c55
Revises: b0c6ccecc679
Create Date: 2026-05-12 14:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9d12e0c55'
down_revision: Union[str, None] = 'b0c6ccecc679'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add user_id as a nullable FK so existing rows are preserved with NULL.
    # New prescriptions will always be stamped with the authenticated user's id.
    op.add_column(
        'projects',
        sa.Column('user_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_projects_user_id_users',
        'projects', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_index('ix_projects_user_id', 'projects', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_projects_user_id', table_name='projects')
    op.drop_constraint('fk_projects_user_id_users', 'projects', type_='foreignkey')
    op.drop_column('projects', 'user_id')
