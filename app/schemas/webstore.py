from pydantic import BaseModel
from typing import Optional, Dict, List
import enum

class StoreType(str, enum.Enum):
    amazon = "amazon"
    walmart = "walmart"

class WebstoreCreate(BaseModel):
    store_type: StoreType
    name: str
    store_id: str
    auth_config: Optional[Dict[str, str]] = {}

class WebstoreUpdate(BaseModel):
    name: Optional[str]
    auth_config: Optional[Dict[str, str]]

class WebstoreOut(BaseModel):
    id: str
    store_type: StoreType
    name: str
    store_id: str
    auth_config: Optional[Dict[str, str]]

    class Config:
        orm_mode = True

class ListWebstoreResponse(BaseModel):
    data: List[WebstoreOut]
