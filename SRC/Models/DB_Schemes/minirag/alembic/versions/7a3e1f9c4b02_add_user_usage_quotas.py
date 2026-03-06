"""add user_usage_quotas table

Revision ID: 7a3e1f9c4b02
Revises: 41b8d758a511
Create Date: 2026-03-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7a3e1f9c4b02"
down_revision: Union[str, None] = "41b8d758a511"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_usage_quotas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("upload_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("query_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("prescription_count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_user_usage_date"),
    )
    op.create_index(op.f("ix_user_usage_quotas_id"), "user_usage_quotas", ["id"], unique=False)
    op.create_index(op.f("ix_user_usage_quotas_user_id"), "user_usage_quotas", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_usage_quotas_user_id"), table_name="user_usage_quotas")
    op.drop_index(op.f("ix_user_usage_quotas_id"), table_name="user_usage_quotas")
    op.drop_table("user_usage_quotas")
