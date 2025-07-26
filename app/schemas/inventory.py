from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import ConfigDict
from uuid import UUID
from datetime import datetime

class ProductBrief(BaseModel):
    id: UUID
    name: str
    upc: str
    model_config = ConfigDict(from_attributes=True)

class UserBrief(BaseModel):
    id: UUID
    email: str
    name: str
    model_config = ConfigDict(from_attributes=True)

class InventorySchema(BaseModel):
    id: UUID
    product: ProductBrief
    available_qty: int
    reserved_qty: int
    holder: UserBrief
    owner: UserBrief
    location: str

    model_config = ConfigDict(from_attributes=True)

class AddInventoryRequest(BaseModel):
    product_id: UUID
    available_qty: int
    holder_id: UUID
    owner_id: UUID
    location: str
    


class InventoryTransactionSchema(BaseModel):
    id: UUID
    inventory: InventorySchema
    transaction_type: str
    quantity: int
    source: str
    source_ref_id: str
    note: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)



