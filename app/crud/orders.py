from sqlalchemy.future import select
from app.models.order import Order
from sqlalchemy.ext.asyncio import AsyncSession

async def get_orders(db: AsyncSession):
    result = await db.execute(select(Order))
    return result.scalars().all()

