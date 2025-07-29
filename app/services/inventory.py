from sqlalchemy import func, or_, select, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.schemas.product import ProductSchema
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.db.service import PaginationService
from app.schemas.inventory import AddInventoryRequest, InventorySchema, InventoryTransactionSchema
from app.models.inventory import Inventory, InventoryStatusEnum, InventoryTransaction, InventoryTransactionSourceEnum, InventoryTransactionTypeEnum
from sqlalchemy.exc import IntegrityError
from app.schemas.pagination import SortOrder
from app.core.exceptions import DatabaseConstraintException, DatabaseException
import asyncpg
from app.utils.mist import is_valid_zipcode
from uuid import UUID

import logging

logger = logging.getLogger(__name__)

class InventoryService:
    def __init__(self):
        pass

    async def add_inventory(self, 
        data: AddInventoryRequest,
        user_id: UUID,
        db: AsyncSession):

        if not is_valid_zipcode(data.location):
            raise HTTPException(status_code=400, detail="invalid zip code.")

        if user_id != data.holder_id and user_id != data.owner_id:
            raise HTTPException(status_code=400, detail="user has to be either holder or owner.")
        if data.available_qty <= 0:
            raise HTTPException(status_code=400, detail="invalid available_qty")

        try:
            #check if existing inventory has same product_id + holder_id + owner_id and status != soft_deleted
            stmt = (
                select(Inventory)
                .where(
                    and_(
                        Inventory.product_id == data.product_id,
                        Inventory.holder_id == data.holder_id,
                        Inventory.owner_id == data.owner_id,
                        Inventory.status != InventoryStatusEnum.soft_deleted,
                    )
                )
                .with_for_update()  # 🔒 Lock the row for safe concurrent update
            )

            result = await db.execute(stmt)
            existing_inventory = result.scalar_one_or_none()

            if existing_inventory:
                # Increment available_qty
                existing_inventory.available_qty += data.available_qty
                existing_inventory.status=InventoryStatusEnum.active

                inventry_transaction = InventoryTransaction(
                    inventory_id=existing_inventory.id,
                    product_id=existing_inventory.product_id,
                    created_by=user_id,
                    transaction_type=InventoryTransactionTypeEnum.credit,
                    quantity=data.available_qty,
                    source=InventoryTransactionSourceEnum.creation,
                    source_ref_id="",
                    note="add inventory")
                db.add(inventry_transaction)
                await db.commit()
                return existing_inventory
            else:
                # Create new inventory record
                new_inventory = Inventory(**data.model_dump())               
                db.add(new_inventory)
                await db.flush()
                inventry_transaction = InventoryTransaction(
                    inventory_id=new_inventory.id,
                    product_id=new_inventory.product_id,
                    created_by=user_id,
                    transaction_type=InventoryTransactionTypeEnum.credit,
                    quantity=new_inventory.available_qty,
                    source=InventoryTransactionSourceEnum.creation,
                    source_ref_id = "",
                    note="add inventory")
                db.add(inventry_transaction)
                await db.commit()
                return new_inventory
        except Exception as ex:
            await db.rollback()
            logger.exception(f"unexpected error adding new inventory")
            raise DatabaseException(500, "Unexpected error while adding a new inventory")
    
    async def get_inventory(self,
            inventory_id: UUID,
            user_id: UUID,
            db: AsyncSession):
            stmt = (
                select(Inventory)
                .options(selectinload(Inventory.product))
                .options(selectinload(Inventory.holder))
                .options(selectinload(Inventory.owner))
                .where(Inventory.id == inventory_id)
            )
            try:
                result = await db.execute(stmt)
                inventory = result.scalar_one_or_none()
                return inventory
            except Exception as ex:
                logger.exception(f"unexpected error fetch a inventory")
                raise DatabaseException(500, "Unexpected error while reading a inventory")

    async def get_inventories_by_owner(self,
            query_str: str,
            page: int,
            limit: int,
            user_id: UUID,
            db: AsyncSession):
        filters = {}
        filters["owner_id"] = user_id
        filters["status"] = InventoryStatusEnum.active
        pagination_service = PaginationService(db)
        try:
            return await pagination_service.paginate_with_full_search(
            model_class=Inventory,
            output_schema=InventorySchema,
            query_str=query_str,
            search_columns=["product.name"],
            page=page,
            limit=limit,
            sort_by="created_at", 
            sort_order=SortOrder.desc,
            eager_load=["product", "holder", "owner"],
            filters=filters
        )
        except Exception as ex:
            logger.exception(f"User {user_id} unexpected error getting inventories")
            raise DatabaseException(500, f"Unexpected error while getting inventories")
        

    async def get_inventories_by_holder(self,
            query_str: str,
            page: int,
            limit: int,
            user_id: UUID,
            db: AsyncSession):
        filters = {}
        filters["holder_id"] = user_id
        filters["status"] = InventoryStatusEnum.active
        pagination_service = PaginationService(db)
        try:
            return await pagination_service.paginate_with_full_search(
            model_class=Inventory,
            output_schema=InventorySchema,
            query_str=query_str,
            search_columns=["product.name"],
            page=page,
            limit=limit,
            sort_by="created_at", 
            sort_order=SortOrder.desc,
            eager_load=["product", "holder", "owner"],
            filters=filters
        )
        except Exception as ex:
            logger.exception(f"User {user_id} unexpected error getting inventories")
            raise DatabaseException(500, f"Unexpected error while getting inventories")

    
    async def get_an_inventory_transactions(self,
        inventory_id: UUID, 
        page: int, 
        limit: int, 
        user_id: UUID, 
        db: AsyncSession):
        filters = {}
        filters["inventory_id"]=inventory_id
        sort_by="created_at"
        sort_order=SortOrder.desc
        pagination_service = PaginationService(db)
        try:
            return await pagination_service.paginate_with_full_search(
                model_class=InventoryTransaction,
                output_schema=InventoryTransactionSchema,
                query_str=None,
                search_columns=[],
                page=page,
                limit=limit,
                sort_by=sort_by, 
                sort_order=sort_order,
                eager_load=["inventory","inventory.holder", "inventory.owner", "product"],
                filters=filters)
        except Exception as ex:
            logger.exception(f"User {user_id} error getting transactions for inventory_id={inventory_id}")
            raise DatabaseException(500, f"Unexpected error while getting inventory transactions.")


    async def get_inventory_transactions(self, 
            as_owner: bool,
            inventory_id: str, 
            query_str: str, 
            page: int,
            limit: int, 
            user_id: str, 
            db: AsyncSession):
        
        pagination_service = PaginationService(db)
        try:
            filters = {}
            if inventory_id:
                filters["inventory.id"] = inventory_id
            if as_owner:
                filters["inventory.owner.id"] = str(user_id)
            else:
                filters["inventory.holder.id"] = str(user_id)
            sort_by = "created_at"
            sort_order: SortOrder = SortOrder.desc

            return await pagination_service.paginate_with_full_search(
            model_class=InventoryTransaction,
            output_schema=InventoryTransactionSchema,
            query_str=query_str,
            search_columns=["inventory.product.name", "inventory.holder.name", "inventory.owner.name"],
            page=page,
            limit=limit,
            sort_by=sort_by, 
            sort_order=sort_order,
            eager_load=["inventory","inventory.product","inventory.holder","inventory.owner"],
            filters=filters)
        except Exception as ex:
            logger.exception(f"unexpected error getting inventory transactions")
            raise DatabaseException(500, f"Unexpected error inventory transactions")
    
    async def delete_inventory(self, inventory_id: UUID, user_id: str, db: AsyncSession):
        result = await db.execute(
            select(Inventory)
            .where(Inventory.id == inventory_id).with_for_update()
        )
        inventory = result.scalar_one_or_none()
        if not inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")
        
        if inventory.owner_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this inventory")

        if inventory.reserved_qty > 0:
            raise HTTPException(status_code=409, detail="Can't delete inventory with reserved units!")

        # Prevent deletion of already deleted inventory,
        if inventory.status not in [InventoryStatusEnum.active, InventoryStatusEnum.inactive]:
            raise HTTPException(status_code=400, detail="Cannot delete a already deleted inventory")
        try:
            inventory.status = InventoryStatusEnum.soft_deleted
            db.add(inventory)
            inventry_transaction = InventoryTransaction(
                inventory_id=inventory.id,
                product_id=inventory.product_id,
                created_by=inventory.owner_id,
                transaction_type=InventoryTransactionTypeEnum.debit,
                quantity=inventory.available_qty,
                source=InventoryTransactionSourceEnum.deletion,
                source_ref_id = "",
                note="delete inventory")
            db.add(inventry_transaction)
            await db.commit()
        except Exception as ex:
            await db.rollback()
            logger.exception(f"unexpected error deleting inventory {inventory_id}")
            raise DatabaseException(500, f"Unexpected error while deleting inventory {inventory_id}")

        
        
            