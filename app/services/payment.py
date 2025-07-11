from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from fastapi import HTTPException, Request
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.models.transaction import Transaction, TransactionType
from app.core.exceptions import NegativeAmountException, DatabaseException, PaymentNotFoundException, UserNotFoundException
from app.schemas.payment import PaymentRequest, PaymentResponse
from uuid import uuid4
import json
import stripe
import logging
import os

logger = logging.getLogger(__name__)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

class PaymentService:
    def __init__(self):
        pass
    async def create_payment_intent(self, request: PaymentRequest, user_id: str, db: AsyncSession):
        # Validate amount
        if request.amount <= 0:
            raise NegativeAmountException(request.amount)
        # Create PaymentIntent
        amount_cents = (request.amount  * 100).to_integral_value(rounding=ROUND_DOWN)
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=request.currency,
            metadata={'user_id': user_id}
        )
        payment = Payment(
            id=str(uuid4()),
            user_id = user_id,
            intent_id = intent.id,
            amount = request.amount,
            status = PaymentStatus.initiate
        )
        try:
            db.add(payment)
            await db.commit()
            logger.info(f"payment with intent_id={intent.id} added")
            return PaymentResponse(client_secret = intent.client_secret)
        except Exception as ex:
            await db.rollback()
            logger.exception(f"failed persit payment record with {ex}")
            raise DatabaseException(500, "failed to persit payment")
    

    async def process_stripe_webhook(self, request: Request, db: AsyncSession):
        
        payload = await self.verify_webhook_signature(request)
    
        try:
            event = stripe.Event.construct_from(
                json.loads(payload), stripe.api_key
            )         
            logger.info(f"Received webhook event: {event.type}")         
            if event.type == 'payment_intent.succeeded':
                payment_intent = event.data.object
                await self._handle_successful_payment(payment_intent.id, db)
            elif event.type == 'payment_intent.payment_failed':
                await self._handle_failed_payment(payment_intent.id, db)
            
            elif event.type == "payment_intent.created":
                # Handle failed payment
                logger.warning(f"Payment created but no need handle here")
            else:
                logger.warning("event of payement type {event.type} received but ignore here.")                        
            return {"status": "success"}
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=400, detail="Webhook error")


    async def verify_webhook_signature(self, request: Request):
        """Verify Stripe webhook signature"""
        try:
            payload = await request.body()
            sig_header = request.headers.get('stripe-signature')
            
            if not sig_header:
                raise HTTPException(status_code=400, detail="Missing signature")
            
            # Verify webhook signature
            #webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
            webhook_secret = "whsec_97b55a96f74a136568ff3256861dca29a0062277223195959eb69f457a362c93"
            stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            return payload
        except ValueError:
            print("debbug1")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            print("debbug2")
            raise HTTPException(status_code=400, detail="Invalid signature")
      

    async def _handle_failed_payment(self, intent_id:str, db: AsyncSession):
        # Lock both Payment and User row
        try:
            logger.info("find out payment with intent_id={intent_id}")
            result = await db.execute(
                select(Payment)
                .where(Payment.intent_id == intent_id)
                .options(selectinload(Payment.user))
                .with_for_update()
            )
            payment = result.scalars().first()
            if not payment:
                raise PaymentNotFoundException(f"Payment with stripe intent_id {intent_id} not found")
            
            #avoid double processing
            if payment.status == PaymentStatus.failure:
                return
            
            payment.status = PaymentStatus.failure
            # Commit all
            await db.commit()
        except Exception as ex:
            await db.rollback()
            logger.exception(f"failed handle failed payment {ex}")
            #raise DatabaseException(500, "failed handle failed payment")


    async def _handle_successful_payment(self, intent_id: str, db: AsyncSession):
    # Lock both Payment and User row
        try:
            result = await db.execute(
                select(Payment)
                .where(Payment.intent_id == intent_id)
                .options(selectinload(Payment.user))
                .with_for_update()
            )
            payment = result.scalars().first()
            logger.info("to found id intent_id={intent_id}")
            if not payment:
                raise PaymentNotFoundException(f"Payment with stripe intent_id {intent_id} not found")
            #avoid double processing
            if payment.status == PaymentStatus.success:
                return

            # Lock user row explicitly to prevent balance race condition
            user_result = await db.execute(
                select(User).where(User.id == payment.user_id).with_for_update()
            )
            user = user_result.scalars().first()

            if not user:
                raise UserNotFoundException(payment.user_id)

            # Now safe to update balance
            user.balance += Decimal(payment.amount)

            # Add transaction record
            transaction = Transaction(
                id=str(uuid4()),
                user_id=user.id,
                amount=payment.amount,
                new_balance=user.balance,
                trans_type=TransactionType.deposit,
                note=f"funds from strip payment {intent_id}"
            )
            db.add(transaction)
            # Update payment status
            payment.status = PaymentStatus.success
            # Commit all

            await db.commit()
            logger.info(f"[Webhook] Updated balance: {user.balance}")
        except Exception as ex:
            await db.rollback()
            logger.exception(f"failed handle failed payment {ex}")
            #raise DatabaseException(500, "failed handle failed payment")
            #TODO sending notification
        

