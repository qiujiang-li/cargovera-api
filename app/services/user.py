from sqlalchemy import func, or_, select
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import UserSearchSchema, UpdateProfileSchema, UserMeSchema
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.db.service import PaginationService
from app.schemas.product import AddProductRequest
from sqlalchemy.exc import IntegrityError
from app.schemas.pagination import SortOrder
from app.core.exceptions import DatabaseConstraintException, DatabaseException
import asyncpg
from app.utils.mist import is_valid_upc

import logging

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self):
        pass

    async def search_users(
        self,
        db: AsyncSession,
        query_str: str,
        page: int,
        limit: int) -> PaginatedResponse[UserSearchSchema]:
        # Primary: pg_trgm similarity

        pagination_service = PaginationService(db)
        try:
            filters = {}
            sort_by = "created_at"
            sort_order: SortOrder = SortOrder.desc

            return await pagination_service.paginate_with_full_search(
            model_class=User,
            output_schema=UserSearchSchema,
            query_str=query_str,
            search_columns=["name", "email"],
            page=page,
            limit=limit,
            sort_by=sort_by, 
            sort_order=sort_order,
            eager_load=[],
            filters=filters)

        except Exception as ex:
            logger.exception(f"unexpected error getting users")
            raise DatabaseException(500, f"Unexpected error while searching users")

    async def update_user(self,
        data:UpdateProfileSchema,
        user_id: str,
        db: AsyncSession):
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            raise UserNotFoundException(current_user.id)

        if data.name: 
            setattr(user, "name", data.name)
        if data.phone:
            setattr(user, "phone", data.phone)

        await db.commit()
        await db.refresh(user)
        return UserMeSchema.from_orm(user)
    