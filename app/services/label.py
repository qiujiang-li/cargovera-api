import logging
from app.external.fedex import FedExService
from app.models.label import CarriersEnum, Label, LabelStatus
from app.models.transaction import Transaction, TransactionType
from app.schemas.label import BuyLabelRequest,ShipmentRatesRequest,ShipmentRatesResponse, LabelSchema
from app.models.user import User
from app.models.order import Order, OrderStatus
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.pagination import SortOrder
from typing import List, Optional
from sqlalchemy import select
from functools import lru_cache
from app.core.exceptions import LabelValidationException, RateNotAvailableException, InsufficientBalanceException, DatabaseException, NegativeAmountException
from uuid import uuid4
from decimal import Decimal, ROUND_HALF_UP
from app.utils.money import Money
from app.db.service import PaginationService

logger = logging.getLogger(__name__)


@lru_cache()
def get_fedex_service() -> FedExService:
    """Create and cache FedEx API client instance."""
    return FedExService()

class LabelService:
    def __init__(self):
        pass
    async def get_rates(self, carrier: CarriersEnum, data: ShipmentRatesRequest, user: User):
        if carrier == CarriersEnum.fedex:
            sumarry_rates = await self._get_fedex_rates(data)
            #apply multiplier
            results = [
                ShipmentRatesResponse(
                    **rate.model_dump(exclude={"total_charge"}),
                    total_charge=self._apply_multiplier_to_rates(rate.total_charge, user.multiplier)
                )
                for rate in sumarry_rates
            ]
            return results
        else:
            raise UnSupportedCarrierException(carrier)

    async def buy_label(self, carrier: CarriersEnum, data: BuyLabelRequest, user: User, db: AsyncSession):
        if carrier == CarriersEnum.fedex:
            return await self._buy_fedex_label(data, user, db)
        else:
            raise UnSupportedCarrierException(carrier)

    async def cancel_label(self, carrier: CarriersEnum, data: BuyLabelRequest, user: User, db: AsyncSession):
        if carrier == CarriersEnum.fedex:
            return await self._cancel_fedex_label(data, user, db)
        else:
            raise UnSupportedCarrierException(carrier)

    
    async def validate_shipment(self, carrier: CarriersEnum, data: BuyLabelRequest):
        if carrier == CarriersEnum.fedex:
            return await self._validate_fedex_shipment(data)
        else:
            raise UnSupportedCarrierException(carrier)

    async def get_labels(self,
        user_id: str,
        db: AsyncSession,
        page: int = 1,
        limit: Optional[int] =  10,
        status: Optional[OrderStatus] = LabelStatus.new,
        carrier: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None):

        filters = {}
        filters["user_id"] = user_id

        sort_by = "created_at"
        sort_order: SortOrder = SortOrder.desc

        if status:
            filters["status"] = status
        if carrier:
            filters["carrier"] = carrier        

        lable_date_filters = {}
        if date_from:
            date_from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            lable_date_filters["gte"] = date_from_date
        if date_to:
            date_to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
            lable_date_filters["lte"] = date_to_date

        if lable_date_filters:
            filters["create_at"] = lable_date_filters

        pagination_service = PaginationService(db)
        try:
            return await pagination_service.paginate(
            model_class=Label,
            output_schema=LabelSchema,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters
        )
        except Exception as ex:
            logger.exception(f"User {user_id} unexpected error getting labels: {ex}")
            raise DatabaseException(500, f"Unexpected error while getting labels")
    
    
    async def _cancel_fedex_label(self, data: BuyLabelRequest, user: User, db: AsyncSession):
        fedex = get_fedex_service()
        success = await fedex.cancel_label(tracking_number=data.tracking_number)
        if not success:
            raise ExternalServiceException(f"fail to cancel fedex label {data.tracking_number}")
        try:
            # Step 1: lock the label row to ensure it isn't updated concurrently
            result = await db.execute(
                select(Label).where(Label.tracking_number == data.tracking_number).with_for_update()
            )
            label = result.scalar_one_or_none()
            if not label:
                raise DatabaseException(404, "Label not found")

            if label.status == LabelStatus.cancelled:
                raise DatabaseException(400, "Label already cancelled")

            # Step 2: lock the user row to safely update balance
            result = await db.execute(
                select(User).where(User.id == user.id).with_for_update()
            )
            user_locked = result.scalar_one()

            # Step 3: update label status
            label.status = LabelStatus.cancelled

            # Step 4: create transaction and update balance
            user_locked.balance += label.cost_estimate

            transaction = Transaction(
                id=str(uuid4()),
                user_id=user_locked.id,
                amount=label.cost_estimate,
                new_balance=user_locked.balance,
                trans_type=TransactionType.refund,
                note=f"Refund label purchase for tracking {label.tracking_number} - {label.service_type}"
            )

            db.add(transaction)
            await db.commit()
            return
        except Exception as ex:
            await db.rollback()
            logger.exception(f"Failed to commit label cancel to DB: {ex}")
            raise DatabaseException(500, "Failed to commit label cancel to DB")

    async def _get_fedex_rates(self, data: ShipmentRatesRequest):
        fedex = get_fedex_service()
        rates = await fedex.get_quick_rates(
                pickup_postal_code=data.shipper.postal_code,
                pickup_country_code=data.shipper.country_code,
                destination_postal_code=data.recipient.postal_code, 
                destination_country_code=data.recipient.country_code,
                packages=data.packages)
       
        sumarry_rates = [ShipmentRatesResponse(
                            service_provider="FedEx",
                            service_type= rate.get("serviceType"), 
                            total_charge=rate["ratedShipmentDetails"][0]["totalNetFedExCharge"],
                            delivery_date=rate.get("commit",{}).get("dateDetail",{}).get("dayFormat"),  
                            delivery_dayofweek=rate.get("commit",{}).get("dateDetail",{}).get("dayOfWeek")) for rate in rates]
        return sumarry_rates

    
    async def _buy_fedex_label(self, data: BuyLabelRequest, user: User, db: AsyncSession):
        fedex = get_fedex_service()
        res = await fedex.validate_shipment(shipper_address=data.shipper, 
                                    recipient_address=data.recipient, 
                                    serviceType=data.service_type, 
                                    total_weight=data.total_weight, 
                                    packages=data.packages, 
                                    ship_date=data.ship_date, 
                                    pickup_type=data.pickup_type or "DROPOFF_AT_FEDEX_LOCATION", 
                                    labelStockType=data.label_stock_type or "PAPER_4X6", 
                                    mergeLabelDocOption=data.merge_label_doc_option or "NONE")

        if not res:
            raise LabelValidationException("not able to validate the shipment, please retry!")
        if not res.get("success"):
            raise LabelValidationException(res.get("error", "not able to validate the shipment, please retry!"))

        # get rates
        rates = await fedex.get_quick_rates(
                pickup_postal_code=data.shipper.postal_code,
                pickup_country_code=data.shipper.country_code,
                destination_postal_code=data.recipient.postal_code, 
                destination_country_code=data.recipient.country_code,
                packages=data.packages)
    
        filtered_rates = [r["ratedShipmentDetails"][0]["totalNetFedExCharge"] for r in rates if  r.get("serviceType") == data.service_type ]

        if not filtered_rates:
            raise RateNotAvailableException(data.service_type)
        
        estimated_rate = self._apply_multiplier_to_rates(filtered_rates[0], user.multiplier)

        # check if user has enough balance
        if user.balance < estimated_rate:
            raise InsufficientBalanceException(user.balance, filtered_rates[0])

        # buy label
        result = await fedex.buy_label(shipper_address=data.shipper, 
                                    recipient_address=data.recipient, 
                                    serviceType=data.service_type, 
                                    total_weight=data.total_weight, 
                                    packages=data.packages, 
                                    ship_date=data.ship_date, 
                                    pickup_type=data.pickup_type or "DROPOFF_AT_FEDEX_LOCATION", 
                                    labelStockType=data.label_stock_type or "PAPER_4X6", 
                                    mergeLabelDocOption=data.merge_label_doc_option or "NONE")  

        label_details = result.get("output", {}).get("transactionShipments", [])[0].get("pieceResponses",[]);
        labels = [] 
        for label_detail in label_details:  
            label = Label(
                id=str(uuid4()),
                user_id=user.id,
                order_number=data.order_number,
                tracking_number=label_detail.get("trackingNumber"),
                label_url=label_detail.get("packageDocuments",[])[0].get("url"),
                status=LabelStatus.new,
                carrier=CarriersEnum.fedex,
                service_type=data.service_type,
                cost_estimate=self._apply_multiplier_to_rates(label_detail.get("baseRateAmount", 0), user.multiplier)
            ) 
            labels.append(label)

        try:
            # Step 1: lock the user row
            result = await db.execute(
                select(User).where(User.id == user.id).with_for_update()
            )
            user_locked = result.scalar_one()
            
            # Step 2: update the order status (if needed)
            result = await db.execute(
                select(Order).where(Order.order_number == data.order_number)
            )
            order = result.scalars().first()
            if order:
                order.status = OrderStatus.shipped

            # Step 3: create transaction records and update user's balance
            transactions = []
            for label in labels:
                user_locked.balance -= label.cost_estimate  # deduct cost for each label

                transaction = Transaction(
                    id=str(uuid4()),
                    user_id=user_locked.id,
                    amount=label.cost_estimate,
                    new_balance=user_locked.balance,   # store the *new* balance after deduction
                    trans_type=TransactionType.usage,
                    note=f"Label purchase for tracking {label.tracking_number} - {label.service_type}"
                )   
                transactions.append(transaction)

            # Step 4: add and commit all at once
            db.add_all(labels)
            db.add_all(transactions)
            await db.commit()
            return labels
        except Exception as ex:
            await db.rollback()
            logger.exception(f"failed to commit changes of buy label to db {ex}")
            raise DatabaseException(500, "failed to commit changes of buy label to db")

    async def _validate_fedex_shipment(self, data:BuyLabelRequest):
        fedex_service = get_fedex_service()
        return await fedex_service.validate_shipment(shipper_address=data.shipper, 
                                            recipient_address=data.recipient, 
                                            serviceType=data.service_type, 
                                            total_weight=data.total_weight, 
                                            packages=data.packages, 
                                            ship_date=data.ship_date, 
                                            pickup_type=data.pickup_type or "DROPOFF_AT_FEDEX_LOCATION", 
                                            labelStockType=data.label_stock_type or "PAPER_4X6", 
                                            mergeLabelDocOption=data.merge_label_doc_option or "NONE")
    
    def _apply_multiplier_to_rates(self, init_value: Decimal, multiplier: Decimal):
        if not isinstance(init_value, Decimal):
            init_value = Decimal(str(init_value))  # safe coercion from float
        if not isinstance(multiplier, Decimal):
            multiplier = Decimal(str(multiplier))

        if init_value < 0:
            raise NegativeAmountException(init_value)

        new_value = (init_value * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        logger.info(f"_apply_multiplier_to_rates init_value={init_value}, new_value={new_value}")
        return new_value