# app/schemas/label.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import ConfigDict
from uuid import UUID
from datetime import datetime
from app.models.label import LabelStatus

class AddressSchema(BaseModel):
    contact_name: str
    company_name: Optional[str] = None
    street_line1: str
    street_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country_code: str
    phone: Optional[str] = None
    email: Optional[str] = None

class ShipmentRatesResponse(BaseModel):
    service_provider: str = Field(..., description="Name of the service provider")
    service_type: str = Field(..., description="Name of the service")
    total_charge: Decimal = Field(..., gt=0, description="Total charge in USD")
    delivery_promise: str = Field(..., description="Transit time in days")

class ShipmentRatesRequest(BaseModel):
    order_number: str
    service_type: Optional[str] = None
    shipper: AddressSchema
    recipient: AddressSchema
    packages: List[Dict[str, Any]] = Field(..., min_length=1)

class CancelLabelRequest(BaseModel):
    tracking_number: str

class BuyLabelRequest(BaseModel):
    order_number: Optional[str] = None
    service_type: str
    pickup_type: Optional[str] = None
    total_weight: Optional[float] = None
    ship_date: Optional[str] = None
    label_stock_type: Optional[str] = None
    merge_label_doc_option: Optional[str] = None
    shipper: AddressSchema
    recipient: AddressSchema
    packages:  List[Dict[str, Any]]
    signature_option: str


class LabelSchema(BaseModel):
    id: UUID
    status: LabelStatus
    order_number: Optional[str] = None
    tracking_number: str
    label_url: str
    carrier: str
    service_type: str
    cost_estimate: Decimal
    cost_actual: Optional[Decimal] = None
    invoice_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


#USPS 
class USPSLabelReqAddress(BaseModel):
    firstName: str
    lastName: str
    streetAddress: str
    secondaryAddress: str
    city: str
    state: str
    ZIPCode: str

class USPSLabelRequest(BaseModel):
    toAddress: USPSLabelReqAddress
    fromAddress: USPSLabelReqAddress
