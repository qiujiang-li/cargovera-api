from pydantic import BaseModel
from uuid import UUID

class AmazonAccountCreate(BaseModel):
    seller_id: str
    marketplace: str = "US"

class WalmartAccountCreate(BaseModel):
    client_id: str

class AmazonAccountOut(BaseModel):
    id: UUID
    seller_id: str
    marketplace: str
    class Config:
        orm_mode = True

class WalmartAccountOut(BaseModel):
    id: UUID
    client_id: str
    class Config:
        orm_mode = True