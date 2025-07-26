from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.schemas.label import ShipmentRatesRequest, BuyLabelRequest, LabelSchema, CancelLabelRequest
from app.external.fedex import FedExService
from app.api.deps import get_current_admin
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from uuid import uuid4, UUID
from app.models.user import User
from app.schemas.user import UserSchema, UpdateMultiplierRequest, TopUpRequest
from app.services.admin import AdminService
from app.schemas.pagination import SortOrder
from typing import List, Optional
from sqlalchemy import select
import logging
from decimal import Decimal
from app.services.label import LabelService
logger = logging.getLogger("labels")

router = APIRouter()

logger = logging.getLogger("admin")


def get_admin_service():
    return AdminService()

@router.get("/users")
async def get_users(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    admin_service: LabelService = Depends(get_admin_service),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    is_active: Optional[bool] = None,
    email: Optional[str] = None):
    user_id = current_user.id
    return await admin_service.get_users(   
        db,     
        page,
        limit,
        is_active,
        email
    )

@router.post("/{user_id}/activate")
async def activate_user(
    user_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    admin_service: LabelService = Depends(get_admin_service)
    ):

    return await admin_service.activate_user(user_id, db)

@router.post("/{user_id}/multiplier")
async def update_multiplier(user_id: UUID, data: UpdateMultiplierRequest, 
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    admin_service: AdminService = Depends(get_admin_service)):

    multiplier = data.multiplier
    return await admin_service.update_multiplier(user_id, multiplier, db)


@router.post("/{user_id}/topup")
async def update_balance(user_id: UUID, data: TopUpRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    admin_service: AdminService = Depends(get_admin_service)):
    logger.info(f"request topup for user {user_id}, amount {data.amount}")

    return await admin_service.update_balance(user_id, data.amount, db)
