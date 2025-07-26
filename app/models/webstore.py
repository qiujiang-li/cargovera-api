from sqlalchemy import Column, String, ForeignKey, DateTime, Enum, JSON, ARRAY,Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.models.base import Base
from sqlalchemy.dialects.postgresql import UUID
import enum
import uuid

class StoreType(str, enum.Enum):
    amazon = "amazon"
    walmart = "walmart"

class ConnectionStatus(str,  enum.Enum):
    connected = "connected"   #successfully exchanges OAuth code → set
    error = "error"   
    disconnected = "disconnected" #   refresh token / call API and get an error: 'error' or 'disconnected'.
    pending = "pending"   #user started OAuth but hasn’t finished yet.

class WebStore(Base):
    __tablename__ = 'webstores'
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    user_id = Column(UUID, ForeignKey('users.id'), nullable=False)
    store_type = Column(Enum(StoreType), nullable=False)  # 'amazon', 'walmart'
    store_unique_id = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    access_token = Column(String, nullable=True)
    access_token_expires_at = Column(DateTime, nullable=True)
    marketplace_ids = Column(ARRAY(String))
    connection_status =  Column(Enum(ConnectionStatus), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_sync_at = Column(DateTime)
    is_active=Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'store_type', 'store_unique_id'),
    )
