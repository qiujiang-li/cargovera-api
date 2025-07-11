import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Numeric, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from sqlalchemy.orm import relationship
from app.models.base import Base
from app.utils.money import Money
from decimal import Decimal

class User(Base):
    __tablename__ = 'users'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=True)
    password_hash = Column(String)
    is_email_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False)
    multiplier = Column(Numeric(5, 2), nullable=False, default=1.00)
    balance_cents = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payments = relationship("Payment", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    addresses = relationship("Address", back_populates="user")
    webstores = relationship("Webstore", back_populates="user")
    labels = relationship("Label", back_populates="user")
    orders = relationship("Order", back_populates="user")

    __table_args__ = (
        CheckConstraint('multiplier >= 1.00 AND multiplier <= 1.99', name='multiplier_range'),
    )

    @property
    def balance(self) -> Money:
        """Expose as Money when reading."""
        return Money.from_cents(self.balance_cents).amount
    
    @balance.setter
    def balance(self, value: Money | Decimal | str | float):
        """Allow setting as Money, Decimal, str, or float."""
        if not isinstance(value, Money):
            value = Money(value)
        self.balance_cents = value.to_cents()