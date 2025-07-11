from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.core.security import verify_password

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def authenticate_user(db: AsyncSession, email: str, password: str):
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


# async def get_or_create_wallet(db: AsyncSession, user_id):
#     result = await db.execute(select(PostageWallet).where(PostageWallet.user_id == user_id))
#     wallet = result.scalar_one_or_none()
#     if wallet is None:
#         wallet = PostageWallet(user_id=user_id)
#         db.add(wallet)
#         await db.commit()
#         await db.refresh(wallet)
#     return wallet

# async def top_up_wallet(db: AsyncSession, user_id, amount_cents: int):
#     wallet = await get_or_create_wallet(db, user_id)
#     wallet.balance_cents += amount_cents
#     await db.commit()
#     await db.refresh(wallet)
#     return wallet