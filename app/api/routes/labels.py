from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.schemas.label import ShipmentRatesRequest, BuyLabelRequest, LabelSchema, CancelLabelRequest
from app.external.fedex import FedExService
from app.api.deps import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from functools import lru_cache
from app.models.label import CarriersEnum, LabelStatus
from uuid import uuid4
from app.models.label import Label
from app.models.user import User
from app.db.service import PaginationService
from app.schemas.pagination import SortOrder
from typing import List, Optional
from sqlalchemy import select
import logging
from app.core.exceptions import InsufficientBalanceException
from decimal import Decimal
from app.services.label import LabelService
logger = logging.getLogger("labels")

router = APIRouter()

def get_label_service():
    return LabelService()

@lru_cache()
def get_fedex_service() -> FedExService:
    """Create and cache FedEx API client instance."""
    return FedExService()

@router.post("/fedex/rates")
async def rate_shipment(data: ShipmentRatesRequest, label_service: LabelService = Depends(get_label_service),  user=Depends(get_current_user)):
    sumarry_rates = await label_service.get_rates(CarriersEnum.fedex, data, user)
    return {"data": sumarry_rates}

@router.post("/fedex/buy-label",)
async def buy_label(data: BuyLabelRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user), label_service: LabelService = Depends(get_label_service)):
    labels = await label_service.buy_label(CarriersEnum.fedex, data, user, db)
    # Convert labels using from_orm
    label_responses = [LabelSchema.from_orm(label) for label in labels]
    return {"data": label_responses}

@router.post("/fedex/validate")
async def validate_shipment(data: BuyLabelRequest, label_service: LabelService = Depends(get_label_service)):
    return await label_service.validate_shipment(CarriersEnum.fedex, data)


@router.post("/fedex/cancel-label", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_label(data: CancelLabelRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user), label_service: LabelService = Depends(get_label_service)):
    return await label_service.cancel_label(CarriersEnum.fedex, data, user, db)

@router.get("/")
async def get_labels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    status: Optional[str] = None,
    carrier: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None):
    user_id = current_user.id
    return await label_service.get_labels(        
        page=page,
        limit=limit,
        status=status,
        carrier=carrier,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        db=db,
    )