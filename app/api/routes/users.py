from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.user import UpdateProfileSchema, UserMeSchema
from uuid import UUID
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import UserNotFoundException
from sqlalchemy import select
router = APIRouter()


@router.put("/", )
async def update_profile(
    data: UpdateProfileSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ):
        result = await db.execute(select(User).where(User.id == current_user.id))
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


