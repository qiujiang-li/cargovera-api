from sqlalchemy import func, or_, select
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.schemas.product import ProductSchema
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

class ProductService:
    def __init__(self):
        pass

    async def search_products(
        self,
        db: AsyncSession,
        user_id: str,
        upc: str,
        query_str: str,
        page: int,
        limit: int) -> PaginatedResponse[ProductSchema]:
        # Primary: pg_trgm similarity

        pagination_service = PaginationService(db)
        try:
            filters = {}
            filters["user_id"] = user_id
            if upc:
                filters["upc"] = upc
            sort_by = "created_at"
            sort_order: SortOrder = SortOrder.desc

            return await pagination_service.paginate_with_full_search(
            model_class=Product,
            output_schema=ProductSchema,
            query_str=query_str,
            search_columns=["name"],
            page=page,
            limit=limit,
            sort_by=sort_by, 
            sort_order=sort_order,
            eager_load=[],
            filters=filters)

        except Exception as ex:
            logger.exception(f"unexpected error getting products")
            raise DatabaseException(500, f"Unexpected error while searching products")
    

    async def add_product(self, 
        data: AddProductRequest,
        user_id: str,
        db: AsyncSession):

        if not is_valid_upc(data.upc):
            raise HTTPException(status_code=400, detail="invalid upc code")
        try:
            payload = data.model_dump()
            payload["user_id"] = user_id
            new_product = Product(**payload)
            db.add(new_product)
            await db.commit()
            await db.refresh(new_product)
            return new_product
        except IntegrityError as error:
            await db.rollback()
            #logger.error(f"user {current_user.id} Error creating bulk orders: {error}")
            if isinstance(error.orig, asyncpg.UniqueViolationError):
                logger.warning(f"tried to add duplicate upc code: {error}")
                raise ResourceConflictException("upc already exists.")
            else:
                logger.error(f"IntegrityError adding new product: {error}")
                raise DatabaseConstraintException("upc already exists.")
        except Exception as ex:
            await db.rollback()
            logger.exception(f"unexpected error adding new product")
            raise DatabaseException(500, "Unexpected error while adding a new product")


