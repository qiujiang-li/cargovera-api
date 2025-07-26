# app/services/amazon_token_refresher.py
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select
from datetime import datetime, timedelta
from app.db.session import get_db
from app.models.webstore import WebStore
from app.core import config
import logging
import os

logger = logging.getLogger(__name__)
# Use environment variable from config
DATABASE_URL = os.getenv("DATABASE_URL")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
engine = create_async_engine(DATABASE_URL, echo=DEBUG)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def refresh_amazon_tokens_task():
    while True:
        logger.error("🔄 Running Amazon token refresh task...")
        await refresh_tokens()
        await asyncio.sleep(60 * 1)  # every 30 minutes

async def refresh_tokens():
    # Step 1: read stores
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WebStore.id, WebStore.refresh_token).where(WebStore.store_type == "amazon"))
        stores = result.all()

    updates = []

    # Step 2: call Amazon
    for store_id, refresh_token in stores:
        if not refresh_token:
            continue

        data = {...}
        async with httpx.AsyncClient(timeout=10) as client:
            # resp = await client.post(config.AMAZON_TOKEN_URL, data=data)
            resp = await client.post("token_url", data=data)

        if resp.status_code == 200:
            token_data = resp.json()
            updates.append({
                "id": store_id,
                "access_token": token_data.get("access_token"),
                "access_token_expires_at": datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
            })

    # Step 3: bulk update
    async with AsyncSessionLocal() as db:
        for upd in updates:
            await db.execute(
                update(WebStore)
                .where(WebStore.id == upd["id"])
                .values(
                    access_token=upd["access_token"],
                    access_token_expires_at=upd["access_token_expires_at"]
                )
            )
        await db.commit()
