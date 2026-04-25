from .minirag_base import SQLAlchemyBase
from sqlalchemy import Column , Integer , String , Boolean , DateTime , func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.orm import relationship



class Project(SQLAlchemyBase) :
    __tablename__ = "projects"

    project_id = Column(Integer , primary_key = True , autoincrement = True)
    project_uuid = Column(UUID(as_uuid = True) , default = uuid.uuid4 , unique = True, nullable = False)

    create_at  =Column(DateTime(timezone = True) , server_default = func.now(), nullable = False)
    update_at  =Column(DateTime(timezone = True) , default=func.now(), onupdate = func.now(), nullable = False)
    
    title = Column(String, default="New Prescription")
    is_pinned = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    share_token = Column(String, nullable=True, unique=True)

    chunks = relationship("dataChunk" , back_populates = "project")
    assets = relationship("Asset" , back_populates = "project")
    