# app/models/order.py
from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric, JSON, Integer, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.models.base import Base
from sqlalchemy import Enum as SqlEnum
from enum import Enum
from datetime import datetime
from app.utils.money import Money
from decimal import Decimal

class OrderStatus(str, Enum):
    new = "new"
    shipped = "shipped"
    others = "others"

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    store_name = Column(String, nullable=False, index=True)
    order_number = Column(String, nullable=False, index=True, unique=True)
    item_name = Column(String, nullable=False)
    item_sku = Column(String, nullable=False)
    item_qty = Column(Integer, nullable=False)

    order_date = Column(Date, nullable=False)
    ship_by = Column(Date, nullable=True)
    deliver_by = Column(Date, nullable=True)
    status = Column(SqlEnum(OrderStatus, name="order_status"), default=OrderStatus.new, nullable=False)
    total_amount_cents = Column(Integer, nullable=False)
    delivery_notes = Column(String, nullable=True)
    # snapshot of buyer's shipping address at time of orde
    buyer_address = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=func.now())

    @property
    def total_amount(self) -> Money:
        """Expose as Money when reading."""
        return Money.from_cents(self.total_amount_cents).amount
    
    @total_amount.setter
    def total_amount(self, value: Money | Decimal | str | float):
        """Allow setting as Money, Decimal, str, or float."""
        if not isinstance(value, Money):
            value = Money(value)
        self.total_amount_cents = value.to_cents()

    # Relationships
    user = relationship("User", back_populates="orders")
    #webstore = relationship("Webstore", back_populates="orders")

