from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Integer, Index, Text
from sqlalchemy.orm import relationship
from app.models.base import Base
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
import uuid
from sqlalchemy import Enum as SqlEnum
from enum import Enum
from datetime import datetime
from app.utils.money import Money
from decimal import Decimal

class FulfillmentRequeestStatusEnum(str, Enum):
    pending = "pending" 
    fulfilled = "fulfilled"
    cancelled = "cancelled"

class FulfillmentRequest(Base):
    __tablename__ = "fulfillment_requests"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    holder_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    status = Column(SqlEnum(FulfillmentRequeestStatusEnum, name="fulfill_status"), default=FulfillmentRequeestStatusEnum.pending, nullable=False)
    created_at = Column(DateTime, default=func.now())
    items = relationship("FulfillmentItem", back_populates="request", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_fulfillment_owner_id", "owner_id"),
        Index("ix_fulfillment_holder_id", "holder_id"),
    )


class FulfillmentItem(Base):
    __tablename__ = "fulfillment_items"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID, ForeignKey("fulfillment_requests.id"), nullable=False)
    inventory_id = Column(UUID, ForeignKey("inventories.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    label_urls = Column(ARRAY(Text), nullable=True)
    note = Column(Text, nullable=True)
    fulfilled_at = Column(DateTime, nullable=True)

    request = relationship("FulfillmentRequest", back_populates="items")
    inventory = relationship("Inventory")
