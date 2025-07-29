from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.schemas.product import ProductSchema 
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
from app.services.inventory import InventoryService
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.schemas.inventory import AddInventoryRequest

logger = logging.getLogger("inventory")

router = APIRouter()

def get_inventory_service():
    return InventoryService()


@router.post("")
async def add_inventory(
    data: AddInventoryRequest,
    db: AsyncSession = Depends(get_db),
    inventory_service = Depends(get_inventory_service), 
    current_user: User = Depends(get_current_user)):
    return await inventory_service.add_inventory(data,current_user.id, db)

# @router.get("/{inventory_id}")
# async def get_inventroy(
#     inventory_id: UUID,
#     inventory_service = Depends(get_inventory_service),
#     current_user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db)):
#     return await inventory_service.get_inventory(inventory_id, current_user.id, db)

@router.get("/owner")
async def get_owner_inventory(
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    q: str = Query(..., description="Search term"),
    inventory_service = Depends(get_inventory_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    return await inventory_service.get_inventories_by_owner(q, page, limit, current_user.id, db)

@router.get("/holder")
async def get_owner_inventory(
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    q: str = Query(..., description="Search term"),
    inventory_service = Depends(get_inventory_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    return await inventory_service.get_inventories_by_holder(q, page, limit, current_user.id, db)


@router.get("/{inventory_id}/transactions")
async def get_an_inventory_transactions(
    inventory_id: UUID,
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    inventory_service = Depends(get_inventory_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    return await inventory_service.get_an_inventory_transactions(inventory_id, page, limit, current_user.id, db)

@router.get("/transactions/owner")
async def get_inventory_transactions(
    inventory_id: Optional[UUID] =  Query(None, description="Inventory Id"),
    q: str = Query(..., description="Search term"),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    inventory_service = Depends(get_inventory_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    as_owner = True
    return await inventory_service.get_inventory_transactions(as_owner, inventory_id, q, page,limit, current_user.id, db)

@router.get("/transactions/holder")
async def get_inventory_transactions(
    inventory_id: Optional[UUID] =  Query(None, description="Inventory Id"),
    q: str = Query(..., description="Search term"),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    inventory_service = Depends(get_inventory_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    as_owner = False
    return await inventory_service.get_inventory_transactions(as_owner, inventory_id, q, page,limit, current_user.id, db)

@router.delete("/{inventory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory(
    inventory_id: UUID,
    inventory_service = Depends(get_inventory_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    return await inventory_service.delete_inventory(inventory_id, current_user.id, db)
