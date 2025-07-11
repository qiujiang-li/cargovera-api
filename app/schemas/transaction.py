from pydantic import BaseModel, UUID4
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from pydantic import ConfigDict
from typing import Optional


class TransactionSchema(BaseModel):
    id: UUID4
    amount: Decimal
    new_balance: Decimal
    trans_type: str
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)