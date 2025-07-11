# from fastapi import APIRouter, Depends
# from sqlalchemy.ext.asyncio import AsyncSession
# from app.db.session import get_db
# from app.api.deps import get_current_user
# from app.models.user import User
# from app.schemas.accounts import AmazonAccountCreate, WalmartAccountCreate, AmazonAccountOut, WalmartAccountOut
# from app.crud.amazon_account import create_amazon_account, get_user_amazon_accounts
# from app.crud.walmart_account import create_walmart_account, get_user_walmart_accounts
# from typing import List

# router = APIRouter()

# @router.post("/amazon", response_model=AmazonAccountOut)
# async def register_amazon_account(
#     payload: AmazonAccountCreate,
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     return await create_amazon_account(db, user.id, payload.seller_id, payload.marketplace)

# @router.get("/amazon", response_model=list[AmazonAccountOut])
# async def list_amazon_accounts(
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     return await get_user_amazon_accounts(db, user.id)

# @router.post("/walmart", response_model=WalmartAccountOut)
# async def register_walmart_account(
#     payload: WalmartAccountCreate,
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     return await create_walmart_account(db, user.id, payload.client_id)

# @router.get("/walmart", response_model=list[WalmartAccountOut])
# async def list_walmart_accounts(
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     return await get_user_walmart_accounts(db, user.id)
