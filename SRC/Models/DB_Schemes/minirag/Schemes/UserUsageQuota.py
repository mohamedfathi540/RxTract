from sqlalchemy import Column, Integer, Date, UniqueConstraint, ForeignKey
from sqlalchemy.sql import func
from .minirag_base import SQLAlchemyBase


class UserUsageQuota(SQLAlchemyBase):
    __tablename__ = "user_usage_quotas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, server_default=func.current_date())
    upload_count = Column(Integer, default=0, server_default="0", nullable=False)
    query_count = Column(Integer, default=0, server_default="0", nullable=False)
    prescription_count = Column(Integer, default=0, server_default="0", nullable=False)
    api_call_count = Column(Integer, default=0, server_default="0", nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_usage_date"),
    )
