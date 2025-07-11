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


class TransactionType(str ,Enum):
    deposit = "deposit"
    usage = "usage"
    refund = "refund"
    adjustment = "adjustment"

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    new_balance_cents = Column(Integer, nullable=False)
    trans_type = Column(SqlEnum(TransactionType, name="trans_type"), nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")

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

    @property
    def new_balance(self) -> Money:
        """Expose as Money when reading."""
        return Money.from_cents(self.new_balance_cents).amount
    
    @new_balance.setter
    def new_balance(self, value: Money | Decimal | str | float):
        """Allow setting as Money, Decimal, str, or float."""
        if not isinstance(value, Money):
            value = Money(value)
        self.new_balance_cents = value.to_cents()