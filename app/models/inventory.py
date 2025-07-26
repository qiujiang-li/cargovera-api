# app/models/inventory.py
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Integer, Index
from sqlalchemy.orm import relationship
from app.models.base import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy import Enum as SqlEnum
from enum import Enum
from datetime import datetime
from app.utils.money import Money
from decimal import Decimal

class InventoryStatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"
    soft_deleted = "soft_deleted"

class Inventory(Base):
    __tablename__ = "inventories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))
    holder_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    available_qty = Column(Integer, nullable=False)
    reserved_qty = Column(Integer, nullable=False, default=0)
    location = Column(String, nullable=False)
    status = Column(SqlEnum(InventoryStatusEnum, name="invstatus"), default=InventoryStatusEnum.active, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    product = relationship("Product")
    holder = relationship("User", foreign_keys=[holder_id])
    owner = relationship("User", foreign_keys=[owner_id])

    __table_args__ = (
        Index("product_id", "owner_id"),
    )


class InventoryTransactionTypeEnum(str, Enum):
    credit = "credit"
    debit = "debit"

class InventoryTransactionSourceEnum(str, Enum):
    creation = "creation"
    outbound = "outbound"
    transfer = "transfer"
    adjustment = "adjustment"
    deletion = "deletion"

class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventories.id"))
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    transaction_type = Column(SqlEnum(InventoryTransactionTypeEnum, name="inv_trans_type"), nullable=False)
    quantity = Column(Integer, nullable=False)
    source = Column(SqlEnum(InventoryTransactionSourceEnum, name="inv_trans_source"), nullable=False)
    source_ref_id = Column(String, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", foreign_keys=[product_id])
    inventory = relationship("Inventory", foreign_keys=[inventory_id])

