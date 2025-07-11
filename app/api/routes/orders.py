from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.models.order import Order
from app.models.user import User
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.service import PaginationService
from app.schemas.pagination import SortOrder
from typing import Optional
from app.schemas.order import OrderSchema
from typing import List
from sqlalchemy.exc import IntegrityError
from app.schemas.order import OrderStatus
import asyncpg
from datetime import datetime
from app.services.order import OrderService
from uuid import UUID

router = APIRouter()    

def get_order_service():
    return OrderService()

@router.get("/")
async def get_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    order_service: OrderService = Depends(get_order_service),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    status: Optional[OrderStatus] = Query(None),
    order_number: Optional[str] = Query(None),
    store_name: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    user_id =  current_user.id
    return await order_service.get_orders(
        page=page,
        limit=limit,
        status=status,
        order_number=order_number,
        store_name=store_name,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        db=db,
    )
@router.post("/{order_id}/skip")
async def skip_order(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), order_service: OrderService = Depends(get_order_service)):
    print("hello")
    user_id = current_user.id
    resp = await order_service.skip_a_order(user_id, db, order_id)
    return {"data": resp}



@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def create_orders(orders: List[OrderSchema], current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), order_service: OrderService = Depends(get_order_service)):
    user_id = current_user.id
    await order_service.create_orders_bulk(user_id, orders, db)
    return {"message": "Orders created successfully"}