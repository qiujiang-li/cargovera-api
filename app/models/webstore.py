from sqlalchemy import Column, String, ForeignKey, DateTime, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.base import Base
from sqlalchemy.dialects.postgresql import UUID
import enum
import uuid

class StoreType(str, enum.Enum):
    amazon = "amazon"
    walmart = "walmart"

class Webstore(Base):
    __tablename__ = "webstores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    store_type = Column(Enum(StoreType), nullable=False)
    name = Column(String, nullable=False)
    store_id = Column(String, nullable=False)
    auth_config = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="webstores")
