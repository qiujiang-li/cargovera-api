from pydantic import BaseModel, UUID4
from typing import List
from decimal import Decimal
from datetime import datetime
from enum import Enum
from pydantic import ConfigDict
from uuid import UUID
from typing import Optional
from datetime import date
class OrderStatus(str, Enum):
    new = "new"
    shipped = "shipped"
    others = "others" 

class OrderSchema(BaseModel):
    id: Optional[UUID] = None
    order_number: str
    store_name: str
    item_name: str
    item_sku: str
    item_qty: int
    status: OrderStatus;
    order_date: Optional[date] = None
    ship_by: Optional[date] = None
    deliver_by: Optional[date] = None
    total_amount: Decimal
    delivery_notes: str
    buyer_address: str 
    
    model_config = ConfigDict(from_attributes=True)

class SkipOrderResponse(BaseModel):
    order_id: UUID
    status: OrderStatus


# class OrderInSchema(BaseModel):
#     user_id: UUID
#     order_number: str
#     store_name: str
#     item_name: str
#     item_sku: str
#     item_qty: int
#     status: OrderStatus;
#     order_date: Optional[date] = None
#     ship_by: Optional[date] = None
#     deliver_by: Optional[date] = None
#     total_amount: Decimal
#     delivery_notes: str
#     buyer_address: str 

    
#     model_config = ConfigDict(from_attributes=True)

