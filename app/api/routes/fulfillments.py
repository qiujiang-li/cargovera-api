from fastapi import APIRouter, Depends, status, Query, HTTPException, BackgroundTasks
from app.schemas.fulfillment import FulfillmentRequestCreate, ConfirmFulfillRequest
from app.models.fulfillment import FulfillmentRequeestStatusEnum
from app.api.deps import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from functools import lru_cache
from uuid import uuid4, UUID
from app.models.user import User
from app.schemas.pagination import SortOrder
from typing import List, Optional
from sqlalchemy import select
import logging
from decimal import Decimal
from app.services.fulfillment import FulfillmentService
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.schemas.inventory import AddInventoryRequest
from datetime import datetime

logger = logging.getLogger("__main__")

router = APIRouter()

def get_fulfillment_service():
    return FulfillmentService()

@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_fulfillment_request(
    data: FulfillmentRequestCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user), 
    fulfillment_service: FulfillmentService = Depends(get_fulfillment_service),
    db: AsyncSession = Depends(get_db)):
    return await fulfillment_service.create_fulfillment_request(data, current_user.id, db, background_tasks)

@router.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fulfillment_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user), 
    fulfillment_service: FulfillmentService = Depends(get_fulfillment_service),
    db: AsyncSession = Depends(get_db)):
    return await fulfillment_service.delete_fulfillment_request(request_id, current_user.id, db)

@router.get("/requests/owner")
async def get_fulfillment_requests(
    status: Optional[FulfillmentRequeestStatusEnum] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    fulfillment_service: FulfillmentService = Depends(get_fulfillment_service),
    current_user: User = Depends(get_current_user)):
    as_owner = True
    return await fulfillment_service.get_fulfillment_requests(as_owner, status, date_from, date_to, page, limit, db, current_user)


@router.get("/requests/holder")
async def get_fulfillment_requests(
    status: Optional[FulfillmentRequeestStatusEnum] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    fulfillment_service: FulfillmentService = Depends(get_fulfillment_service),
    current_user: User = Depends(get_current_user)):
    as_owner = False
    return await fulfillment_service.get_fulfillment_requests(as_owner, status, date_from, date_to, page, limit, db, current_user)

@router.post("/requests/{request_id}")
async def fulfill_request(
    request_id: UUID,
    data: ConfirmFulfillRequest,
    db: AsyncSession = Depends(get_db),
    fulfillment_service: FulfillmentService = Depends(get_fulfillment_service),
    current_user: User = Depends(get_current_user)):
    return await fulfillment_service.fulfill_request(request_id, data.note, current_user.id, db)

