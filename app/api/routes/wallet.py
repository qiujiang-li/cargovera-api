
# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession
# from app.api.deps import get_current_user
# from app.db.session import get_db
# from app.models.user import User
# from app.schemas.wallet import WalletTopUpRequest, WalletOut
# from app.crud.wallet import top_up_wallet, get_or_create_wallet

# router = APIRouter()

# @router.post("/top-up", response_model=WalletOut)
# async def top_up_balance(
#     payload: WalletTopUpRequest,
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     # In real use, you'd verify Stripe payment intent here
#     return await top_up_wallet(db, user.id, payload.amount_cents)

# @router.get("/", response_model=WalletOut)
# async def get_wallet(
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     return await get_or_create_wallet(db, user.id)