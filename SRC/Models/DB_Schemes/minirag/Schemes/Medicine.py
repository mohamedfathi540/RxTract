from sqlalchemy import Column, Integer, String, Float
from .minirag_base import SQLAlchemyBase

class Medicine(SQLAlchemyBase):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    trade_name = Column(String, index=True, nullable=False)
    active_ingredient = Column(String, index=True, nullable=True)
    pharmacological_class = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    dosage_form = Column(String, nullable=True)
    
    # Optionally store the full raw text used for parsing context
    raw_description = Column(String, nullable=True)
