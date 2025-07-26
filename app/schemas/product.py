# app/schemas/label.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import ConfigDict
from uuid import UUID
from datetime import datetime
from app.models.label import LabelStatus

class ProductSchema(BaseModel):
    id: UUID
    name: str
    upc: str
    description: str | None = None
    model_config = ConfigDict(from_attributes=True)


class AddProductRequest(BaseModel):
    name: str
    upc: str
    description: str | None = None

