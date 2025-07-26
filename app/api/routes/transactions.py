from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.api.deps import get_current_user
from app.models.user import User
from app.db.session import get_db
from app.schemas.transaction import TransactionSchema
from app.models.transaction import Transaction, TransactionType
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.db.service import PaginationService
from app.services.transaction import TransactionService
from app.schemas.pagination import SortOrder
router = APIRouter()


def get_transaction_service():
    return TransactionService()

@router.get("")
async def get_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    trans_service: TransactionService = Depends(get_transaction_service),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] =  Query(20, ge=2, le=100),
    trans_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None):

    user_id = current_user.id
    return await trans_service.get_transactions(
        page=page,
        limit=limit,
        trans_type=trans_type,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        db=db,
    )