from fastapi import APIRouter, Depends, Query
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.user import UpdateProfileSchema
from uuid import UUID
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import UserNotFoundException
from sqlalchemy import select
from app.services.user import UserService
router = APIRouter()

def get_user_service():
    return UserService()


@router.put("", )
async def update_profile(
    data: UpdateProfileSchema,
    current_user: User = Depends(get_current_user),
    user_service = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
    ):
    return await user_service.update_user(data, current_user.id, db)

@router.get("")
async def get_users(
    q: str = Query(..., description="Search terms"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    user_service = Depends(get_user_service),
    current_user: User = Depends(get_current_user)):
    return await user_service.search_users(db, q, page, limit)


