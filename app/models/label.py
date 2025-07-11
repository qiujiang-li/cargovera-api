# app/models/label.py
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Integer
from sqlalchemy.orm import relationship
from app.models.base import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy import Enum as SqlEnum
from enum import Enum
from datetime import datetime
from app.utils.money import Money
from decimal import Decimal

class CarriersEnum(str, Enum):
    fedex = "FedEx"
    ups = "UPS"
    usps = "USPS"
    other = "Other"

class LabelStatus(str, Enum):
    new = "new"
    shipped = "shipped"
    cancelled = "cancelled"

class Label(Base):
    __tablename__ = "labels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    order_number = Column(String, index=True, nullable=True)
    tracking_number = Column(String, index=True)
    label_url = Column(String)  # link to the file if stored, or FedEx label URL
    carrier = Column(SqlEnum(CarriersEnum, name="carriers"), default=CarriersEnum.fedex, nullable=False)
    service_type = Column(String, nullable=False)
    cost_estimate_cents = Column(Integer, nullable=False)
    cost_actual_cents = Column(Integer, nullable=True)
    status = Column(SqlEnum(LabelStatus, default=LabelStatus.new, nullable=False))
    invoice_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="labels")

    @property
    def cost_estimate(self) -> Money:
        """Expose as Money when reading."""
        return Money.from_cents(self.cost_estimate_cents).amount
    
    @cost_estimate.setter
    def cost_estimate(self, value: Money | Decimal | str | float):
        """Allow setting as Money, Decimal, str, or float."""
        if not isinstance(value, Money):
            value = Money(value)
        self.cost_estimate_cents = value.to_cents()

    @property
    def cost_actual(self) -> Money:
        """Expose as Money when reading."""
        if self.cost_actual_cents is None:
            return None
        return Money.from_cents(self.cost_actual_cents).amount
    
    @cost_actual.setter
    def cost_actual(self, value: Money | Decimal | str | float):
        """Allow setting as Money, Decimal, str, or float."""
        if not isinstance(value, Money):
            value = Money(value)
        self.cost_actual_cents = value.to_cents()

 
