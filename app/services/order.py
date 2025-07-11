from app.models.order import Order, OrderStatus
from app.schemas.order import OrderSchema, SkipOrderResponse
from app.schemas.pagination import SortOrder
from app.db.service import PaginationService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime
from fastapi import HTTPException
import logging
from sqlalchemy.exc import IntegrityError
import asyncpg
from app.core.exceptions import DatabaseConstraintException, DatabaseException
from uuid import UUID
logger = logging.getLogger(__name__)

class OrderService:
    def __init__(self):
        pass
    async def skip_a_order(self,
        user_id: str,
        db: AsyncSession,
        order_id: UUID):
        logger.error(f"user_id {user_id} and order id {order_id}")
        result = await db.execute(
            select(Order).where(Order.id == order_id, Order.user_id == user_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise OrderNotFoundException(f"order_id {order_id} not found")
        if order.status != OrderStatus.new:
            raise InconsistentStatusException(f"order id {order_id} should be in new status")
        from sqlalchemy import update

        try:
            result = await db.execute(
                update(Order)
                .where(Order.id == order_id, Order.status == OrderStatus.new)
                .values(status=OrderStatus.others)
                .execution_options(synchronize_session="fetch")
            )

            if result.rowcount == 0:
                raise InconsistentStatusException("order id {order_id} should be in new status")
            await db.commit()
            return SkipOrderResponse(
                order_id=order_id,
                status=OrderStatus.others      
            )
        except Exception as ex:
            await db.rollback()
            logger.exception(f"failed to update the status for order id {order_id} with {ex}")
            raise DatabaseException(500, f"failed to update the status for order id {order_id}" )

    async def get_orders(self,  
        user_id: str,
        db: AsyncSession,
        page: int = 1,
        limit: Optional[int] =  10,
        status: Optional[OrderStatus] = OrderStatus.new,
        order_number: Optional[str] = None,
        store_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None):

        filters = {}
        filters["user_id"] = user_id

        sort_by = "created_at"
        sort_order: SortOrder = SortOrder.desc

        if status:
            filters["status"] = status
        if order_number:
            filters["order_number"] = order_number
        if store_name:
            filters["store_name"] = store_name
        

        order_date_filters = {}
        if date_from:
            date_from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            order_date_filters["gte"] = date_from_date
        if date_to:
            date_to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
            order_date_filters["lte"] = date_to_date

        if order_date_filters:
            filters["order_date"] = order_date_filters

        pagination_service = PaginationService(db)
        try:
            return await pagination_service.paginate(
            model_class=Order,
            output_schema=OrderSchema,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters
        )
        except Exception as ex:
            logger.exception(f"User {user_id} unexpected error getting orders: {ex}")
            raise DatabaseException(500, f"Unexpected error while getting orders")

    async def create_order(self, order: OrderSchema, db: AsyncSession):
          pass
    
    async def create_orders_bulk(self, user_id: str, orders: List[OrderSchema], db: AsyncSession):
        try:
            new_orders = [Order(**order.model_dump(), user_id=user_id) for order in orders]
            db.add_all(new_orders)
            await db.commit()
            for order in new_orders:
                await db.refresh(order)
            return new_orders
        except IntegrityError as error:
            await db.rollback()
            #logger.error(f"user {current_user.id} Error creating bulk orders: {error}")
            if isinstance(error.orig, asyncpg.UniqueViolationError):
                logger.warning(f"User {user_id} tried to insert duplicate order number: {error}")
                raise ResourceConflictException("Order number already exists!")
            else:
                logger.error(f"User {user_id} IntegrityError creating bulk orders: {error}")
                raise DatabaseConstraintException("Database integrity error while creating orders")
        except Exception as ex:
            await db.rollback()
            logger.exception(f"User {user_id} unexpected error creating bulk orders: {ex}")
            raise DatabaseException(500, "Unexpected error while creating orders")