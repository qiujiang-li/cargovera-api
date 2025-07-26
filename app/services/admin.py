

from app.models.user import User
from app.db.service import PaginationService
import logging
from app.external.fedex import FedExService
from app.models.label import CarriersEnum, Label, LabelStatus
from app.models.transaction import Transaction, TransactionType
from app.schemas.label import BuyLabelRequest,ShipmentRatesRequest,ShipmentRatesResponse, LabelSchema
from app.models.user import User
from app.schemas.user import UserSchema
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.pagination import SortOrder
from typing import List, Optional
from sqlalchemy import select, update
from functools import lru_cache
from app.core.exceptions import LabelValidationException, RateNotAvailableException, InsufficientBalanceException, DatabaseException
from uuid import uuid4
from decimal import Decimal
from app.utils.money import Money
from app.db.service import PaginationService

logger = logging.getLogger(__name__)

class AdminService:
    def __init__(self):
        pass

    async def get_users(self,
        db: AsyncSession,
        page: int,
        limit: int,
        is_active: bool,
        email: str,
        ): 

        filters = {}
        filters["is_active"] = is_active   

        if email:
            filters["email"] = email  

        sort_by = "created_at"
        sort_order: SortOrder = SortOrder.desc 

        pagination_service = PaginationService(db)
        try:
            return await pagination_service.paginate(
            model_class=User,
            output_schema=UserSchema,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters
        )
        except Exception as ex:
            logger.exception(f"User {user_id} unexpected error getting users: {ex}")
            raise DatabaseException(500, f"Unexpected error while getting labels")
        
    async def activate_user(self, user_id:str, db:AsyncSession):
        try:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(is_active=True)
                .execution_options(synchronize_session="fetch")
                .returning(User)
            )
            result = await db.execute(stmt)
            await db.commit()
            return result.scalar_one_or_none()
        except Exception as ex:
            logger.exception(f"failed to activate {user_id} error: {ex}")
            raise DatabaseException(500, f"Unexpected error while getting labels")

    
    async def update_multiplier(self, user_id:str, multiplier: Decimal, db: AsyncSession):
        try:
            if not (Decimal("1.00") <= multiplier <= Decimal("1.99")):
                raise HTTPException(status_code=400, detail="Multiplier must be between 1.00 and 1.99")
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(multiplier=multiplier)
            )
            await db.commit()
            return {"success": True}
        except Exception as ex:
            logger.exception(f"failed to update user {user_id} with new multiplier: {ex}")
            raise DatabaseException(500, f"failed to update the multiplier")


    async def update_balance(self, user_id:str, amount: Decimal, db: AsyncSession):
 
        try:
            # Step 1: lock the user row to safely update balance
            result = await db.execute(
                select(User).where(User.id == user_id).with_for_update()
            )
            user_locked = result.scalar_one()
                        # Step 4: create transaction and update balance
            user_locked.balance += amount

            transaction = Transaction(
                id=str(uuid4()),
                user_id=user_locked.id,
                amount=amount,
                new_balance=user_locked.balance,
                trans_type=TransactionType.adjustment,
                note=f"adjusted balance by admin"
            )

            db.add(transaction)
            await db.commit()
        except Exception as ex:
            await db.rollback()
            logger.exception(f"Failed to update balance change DB: {ex}")
            raise DatabaseException(500, "Failed to update balance.")



