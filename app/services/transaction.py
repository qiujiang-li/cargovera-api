
from app.models.transaction import TransactionType, Transaction
from app.schemas.transaction import TransactionSchema
from app.schemas.pagination import SortOrder
from app.db.service import PaginationService
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)

class TransactionService:
    def __init__(self):
        pass

    async def get_transactions(self,
        user_id: str,
        db: AsyncSession,
        page: int = 1,
        limit: Optional[int] =  10,
        trans_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None):

        filters = {}
        filters["user_id"] = user_id

        sort_by = "created_at"
        sort_order: SortOrder = SortOrder.desc

        if trans_type:
            filters["trans_type"] = trans_type

        trans_date_filters = {}
        if date_from:
            date_from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            order_date_filters["gte"] = date_from_date
        if date_to:
            date_to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
            order_date_filters["lte"] = date_to_date

        if trans_date_filters:
            filters["created_at"] = trans_date_filters

        pagination_service = PaginationService(db)
        try:
            return await pagination_service.paginate(
            model_class=Transaction,
            output_schema=TransactionSchema,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters
        )
        except Exception as ex:
            logger.exception(f"User {user_id} unexpected error getting orders: {ex}")
            raise DatabaseException(500, f"Unexpected error while getting orders")