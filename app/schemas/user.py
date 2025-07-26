from pydantic import BaseModel,condecimal, Field, constr
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from pydantic import ConfigDict
from typing import Optional
class UserSchema(BaseModel):
    id: UUID
    email: str
    name: str
    phone: Optional[str] = None
    is_active: bool
    is_email_verified: bool
    is_admin: bool
    balance: Decimal
    multiplier: condecimal(gt=0.99, lt=2.0) = Field(default=1.00)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserMeSchema(BaseModel):
    id: UUID
    email: str
    name: str
    phone: Optional[str] = None
    balance: Decimal
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSearchSchema(BaseModel):
    id: UUID
    email: str
    name: str
    phone: str
    model_config = ConfigDict(from_attributes=True)



class UpdateMultiplierRequest(BaseModel):
    multiplier: Decimal
    model_config = ConfigDict(from_attributes=True)

class TopUpRequest(BaseModel):
    amount: Decimal
    model_config = ConfigDict(from_attributes=True)    


class UpdateProfileSchema(BaseModel):
    name: Optional[constr(strip_whitespace=True, max_length=50)] = None
    phone: Optional[constr(strip_whitespace=True, max_length=20)] = None

