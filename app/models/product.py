# app/models/product.py
from sqlalchemy import Column, Text, String, Float, ForeignKey, DateTime, Integer
from sqlalchemy.orm import relationship
from app.models.base import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy import Enum as SqlEnum
from enum import Enum
from datetime import datetime
from app.utils.money import Money
from decimal import Decimal


class Product(Base):
    __tablename__ = "products"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    upc = Column(String, index=True, nullable=False)
    name = Column(String, index=True, nullable=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

