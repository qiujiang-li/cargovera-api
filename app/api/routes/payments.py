from fastapi import APIRouter, Depends,Request
from app.core.config import settings
from app.models import User
from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.payment import PaymentRequest
from app.services.payment import PaymentService
import stripe
import os
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional


router = APIRouter()

def get_payment_service():
    return PaymentService()

@router.post("/create-payment-intent")
async def create_payment_intent(request: PaymentRequest, 
    current_user: User = Depends(get_current_user), 
    payment_service: PaymentService = Depends(get_payment_service),
    db: AsyncSession = Depends(get_db)):
    user_id = current_user.id
    result = await payment_service.create_payment_intent(request, user_id, db)
    return result
    


@router.post("/stripe/webhook")
async def process_stripe_webhook(request: Request, 
    payment_service: PaymentService = Depends(get_payment_service),
    db: AsyncSession = Depends(get_db)):
    return await payment_service.process_stripe_webhook(request, db)

