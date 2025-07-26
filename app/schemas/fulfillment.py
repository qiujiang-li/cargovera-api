from pydantic import BaseModel, UUID4, conint
from typing import List, Optional
from uuid import UUID
from app.models.fulfillment import FulfillmentRequeestStatusEnum
from app.schemas.inventory import ProductBrief, UserBrief
from uuid import UUID
from datetime import datetime
from pydantic import ConfigDict



class FulfillmentItemCreate(BaseModel):
    inventory_id: UUID4
    quantity: conint(gt=0)
    label_urls: List[str]



class FulfillmentRequestCreate(BaseModel):
    owner_id: UUID
    holder_id: UUID
    items: List[FulfillmentItemCreate]


class FulfillmentInventorySchema(BaseModel):
    id: UUID
    product: ProductBrief
    holder: UserBrief
    owner: UserBrief
    model_config = ConfigDict(from_attributes=True)

class FulfillmentItemSchema(BaseModel):
    id: UUID
    quantity: int
    label_urls: List[str]
    note: Optional[str] = None 
    fulfilled_at: Optional[datetime] = None
    inventory: FulfillmentInventorySchema
    model_config = ConfigDict(from_attributes=True)
class FulfillmentRequestSchema(BaseModel):
    id: UUID
    status: FulfillmentRequeestStatusEnum
    created_at: datetime
    items: List[FulfillmentItemSchema]

    model_config = ConfigDict(from_attributes=True)
