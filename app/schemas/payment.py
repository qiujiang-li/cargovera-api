from pydantic import BaseModel, UUID4, Field
from typing import List

from decimal import Decimal

class PaymentRequest(BaseModel):
    amount: Decimal = Field(ge=25, lt=1000)
    currency: str = Field(default="usd", pattern="^[a-z]{3}$")

class PaymentResponse(BaseModel):
    client_secret: str