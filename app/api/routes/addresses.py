from fastapi import APIRouter, Query, Depends, status, HTTPException
from app.api.deps import get_current_user
from app.models.user import User
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.address import Address
from app.schemas.address import AddressSchema
from typing import List, Optional
from app.db.service import PaginationService
from app.schemas.pagination import SortOrder
from uuid import UUID
import logging

logger = logging.getLogger("addresses")

router = APIRouter()

@router.get("/")
async def get_addresses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100)
):

    #build filters.
    user_id = current_user.id
    filters = {}
    filters["user_id"] = user_id

    sort_by = "created_at"
    sort_order: SortOrder = SortOrder.desc

    pagination_service = PaginationService(db)
    try:
        return await pagination_service.paginate(
            model_class=Address,
            output_schema=AddressSchema,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters
        )  
    except Exception as ex:
        logger.exception(f"User {user_id} unexpected error getting addresses: {ex}")
        raise HTTPException(status_code=500, detail=f"Unexpected error while getting addresses")

@router.post("/")
async def create_address(address: AddressSchema, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = current_user.id
    try:
        new_address = Address(
            user_id=user_id,
            alias=address.alias,
            company_name=address.company_name,
            contact_name=address.contact_name,
            phone=address.phone,
            street_line1=address.street_line1,
            street_line2=address.street_line2,
            city=address.city,
            state=address.state,
            zip_code=address.zip_code,
            country=address.country
        )
        db.add(new_address)
        await db.commit()
        await db.refresh(new_address)
        return new_address;
    except Exception as ex:
        logger.exception(f"User {user_id} unexpected error creating address: {ex}")
        raise HTTPException(status_code=500, detail=f"Unexpected error while creating address")

@router.put("/{address_id}")
async def update_address(address_id: UUID, address_in: AddressSchema, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = current_user.id
    try:
        result = await db.execute(select(Address).where(Address.id == address_id, Address.user_id == user_id))
        address = result.scalar_one_or_none()

        if not address:
            raise HTTPException(status_code=404, detail="Address not found")

        for field, value in address_in.dict(exclude_unset=True).items():
            setattr(address, field, value)

        await db.commit()
        await db.refresh(address)
        return address
    except Exception as ex:
        logger.exception(f"User {current_user.id} unexpected error updating address: {ex}")
        raise HTTPException(status_code=500, detail=f"Unexpected error while updating address")

@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    try:
        result = await db.execute(select(Address).where(Address.id == address_id, Address.user_id == user_id))
        address = result.scalar_one_or_none()

        if not address:
            raise HTTPException(status_code=404, detail="Address not found")

        await db.delete(address)
        await db.commit()
        return {"message": "Address deleted successfully"}
    except Exception as ex:
        logger.exception(f"User {user_id} unexpected error deleting address: {ex}")
        raise HTTPException(status_code=500, detail=f"Unexpected error while deleting address")
