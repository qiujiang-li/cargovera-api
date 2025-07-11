from pydantic import BaseModel, Field
from uuid import UUID

class WalletTopUpRequest(BaseModel):
    amount_cents: int = Field(gt=0)

class WalletOut(BaseModel):
    id: UUID
    balance_cents: int
    class Config:
        orm_mode = True