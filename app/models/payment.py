import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey,Float, Integer, Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.base import Base
from enum import Enum
from uuid import uuid4
from app.utils.money import Money
from decimal import Decimal
from sqlalchemy.sql import func


class PaymentStatus(str ,Enum):
    initiate = "initiated"
    success = "success"
    failure = "failure"



class Payment(Base):
    __tablename__ = "payments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    intent_id = Column(String, unique=True, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    status = Column(SqlEnum(PaymentStatus), name="status", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=func.now())

    @property
    def amount(self) -> Money:
        """Expose as Money when reading."""
        return Money.from_cents(self.amount_cents).amount
    
    @amount.setter
    def amount(self, value: Money | Decimal | str | float):
        """Allow setting as Money, Decimal, str, or float."""
        if not isinstance(value, Money):
            value = Money(value)
        self.amount_cents = value.to_cents()

    # 🔁 Back-reference to User
    user = relationship("User", back_populates="payments")

