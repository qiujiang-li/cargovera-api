from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.schemas.product import ProductSchema 
from app.api.deps import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from functools import lru_cache
from uuid import uuid4
from app.models.user import User
from app.schemas.pagination import SortOrder
from app.schemas.product import AddProductRequest
from typing import List, Optional
from sqlalchemy import select
import logging
from decimal import Decimal
from app.services.product import ProductService
from app.schemas.pagination import PaginatedResponse, PaginationInfo

logger = logging.getLogger("products")

router = APIRouter()

def get_product_service():
    return ProductService()


@router.get("", response_model=PaginatedResponse[ProductSchema])
async def search_products(
    upc: Optional[str] =  Query(None, description="Product UPC"),
    q: str = Query(..., description="Search term"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    product_service = Depends(get_product_service),
    current_user: User = Depends(get_current_user)):
    logger.info(f"received q={q} page={page}, limit={limit}")
    return await product_service.search_products(db, current_user.id, upc, q, page, limit)

@router.post("")
async def add_product(
    data: AddProductRequest,
    db: AsyncSession = Depends(get_db),
    product_service = Depends(get_product_service), 
    current_user: User = Depends(get_current_user)):
    new_product = await product_service.add_product(data, current_user.id, db)
    return {"data": new_product}


