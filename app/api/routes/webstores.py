from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_db, get_current_user
from app.schemas.webstore import WebstoreCreate, WebstoreOut, WebstoreUpdate
from app.models.user import User
from app.models.webstore import Webstore
import uuid
from app.schemas.webstore import ListWebstoreResponse
router = APIRouter()

@router.get("/")
async def list_webstores(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Webstore).where(Webstore.user_id == current_user.id))
    return ListWebstoreResponse(data=result.scalars().all())

@router.post("/", response_model=WebstoreOut)
async def add_webstore(ws_in: WebstoreCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ws = Webstore(
        id=str(uuid.uuid4()),
        user_id=user_id,
        **ws_in.dict()
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws

@router.put("/{webstore_id}", response_model=WebstoreOut)
async def update_webstore(webstore_id: str, ws_in: WebstoreUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Webstore).where(Webstore.id == webstore_id, Webstore.user_id == current_user.id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Webstore not found")
    for field, value in ws_in.dict(exclude_unset=True).items():
        setattr(ws, field, value)
    await db.commit()
    await db.refresh(ws)
    return ws

@router.delete("/{webstore_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webstore(webstore_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Webstore).where(Webstore.id == webstore_id, Webstore.user_id == current_user.id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Webstore not found")
    await db.delete(ws)
    await db.commit()
    return 
