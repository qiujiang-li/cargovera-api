from pydantic import BaseModel, UUID4
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from pydantic import ConfigDict

class AddressSchema(BaseModel):
    id: Optional[UUID4] = None
    alias: str
    company_name: Optional[str] = None
    contact_name: str
    phone: str
    street_line1: str
    street_line2: str
    city: str
    state: str
    zip_code: str
    country: str 

    model_config = ConfigDict(from_attributes=True)