import base64
import binascii
import logging
from datetime import datetime
from uuid import UUID, uuid4
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from functools import lru_cache
from typing import Any, List, Optional, Tuple

from fastapi import File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DatabaseException,
    ExternalServiceException,
    InsufficientBalanceException,
    LabelValidationException,
    NegativeAmountException,
    RateNotAvailableException,
    UnSupportedCarrierException,
)
from app.db.service import PaginationService
from app.external.aws_s3 import (
    download_and_upload_label,
    generate_signed_url,
    upload_file_to_s3,
    upload_label_to_s3,
)
from app.external.fedex import FedExService
from app.external.usps import USPSService
from app.models.label import CarriersEnum, Label, LabelStatus
from app.models.order import Order, OrderStatus
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.label import (
    BuyLabelRequest,
    CancelLabelRequest,
    LabelSchema,
    ShipmentRatesRequest,
    ShipmentRatesResponse,
)
from app.schemas.pagination import SortOrder
from app.utils.money import Money
import asyncio


logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_FILE_COUNT = 10

@lru_cache()
def get_fedex_service() -> FedExService:
    """Create and cache FedEx API client instance."""
    return FedExService()


@lru_cache()
def get_usps_service() -> FedExService:
    """Create and cache FedEx API client instance."""
    return USPSService()

class LabelService:
    def __init__(self):
        pass

    async def get_rates(self, data: ShipmentRatesRequest, user: User):
        num_of_packages = len(data.packages)
        if num_of_packages == 1:
            fedex_rates, usps_rates = await asyncio.gather(
                self._get_fedex_rates(data),
                self._get_usps_rates(data)
            )
            summary_rates = fedex_rates + usps_rates
        else: 
            #USPS doesn't support multiple package in one request
            summary_rates = await self._get_fedex_rates(data)

        rates = [
            ShipmentRatesResponse(
                **rate.model_dump(exclude={"total_charge"}),
                total_charge=self._apply_multiplier_to_rates(rate.total_charge, user.multiplier)
            ) for rate in summary_rates]
        results = sorted(rates, key=lambda x: x.total_charge)
        return results

    async def buy_label(
        self,
        carrier: CarriersEnum,
        data: BuyLabelRequest,
        user: User,
        db: AsyncSession,
    ):
        if carrier == CarriersEnum.fedex:
            return await self._buy_fedex_label(data, user, db)
        if carrier == CarriersEnum.usps:
            return await self._buy_usps_label(data, user, db)
        raise UnSupportedCarrierException(carrier)

    async def cancel_label(
        self,
        carrier: CarriersEnum,
        data: CancelLabelRequest,
        user: User,
        db: AsyncSession,
    ):
        if carrier == CarriersEnum.fedex:
            return await self._cancel_fedex_label(data, user, db)
        if carrier == CarriersEnum.usps:
            return await self._cancel_usps_label(data, user, db)
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
            logger.exception(f"User {user_id} unexpected error getting labels")
            raise DatabaseException(500, f"Unexpected error while getting labels")
    
    
    async def _cancel_fedex_label(
        self, data: CancelLabelRequest, user: User, db: AsyncSession
    ):
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
        except DatabaseException as ex:
            raise ex
        except Exception as ex:
            await db.rollback()
            logger.exception(f"Failed to commit label cancel to DB")
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
                            delivery_promise=rate.get("commit",{}).get("dateDetail",{}).get("dayFormat")) for rate in rates] 
        return sumarry_rates



    
    async def _buy_fedex_label(self, data: BuyLabelRequest, user: User, db: AsyncSession):
        fedex = get_fedex_service()

        fedex_signature_option = fedex.get_signature_option(data.signature_option)

        packages = data.packages
        updated_packages = [
            {**pkg, "packageSpecialServices": {"signatureOptionType": fedex_signature_option}}
            for pkg in packages
        ]
        data.packages = updated_packages

        # res = await fedex.validate_shipment(shipper_address=data.shipper, 
        #                             recipient_address=data.recipient, 
        #                             serviceType=data.service_type, 
        #                             total_weight=data.total_weight, 
        #                             packages=data.packages, 
        #                             ship_date=data.ship_date, 
        #                             pickup_type=data.pickup_type or "DROPOFF_AT_FEDEX_LOCATION", 
        #                             labelStockType=data.label_stock_type or "PAPER_4X6", 
        #                             mergeLabelDocOption=data.merge_label_doc_option or "NONE")

        # if not res:
        #     raise LabelValidationException("not able to validate the shipment, please retry!")
        # if not res.get("success"):
        #     raise LabelValidationException(res.get("error", "not able to validate the shipment, please retry!"))

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
        for idx, label_detail in enumerate(label_details,start=1):
            s3_key = download_and_upload_label(label_detail.get("packageDocuments",[])[0].get("url"), 
                   data.order_number, idx, CarriersEnum.fedex.value)
            label = Label(
                id=str(uuid4()),
                user_id=user.id,
                order_number=data.order_number,
                tracking_number=label_detail.get("trackingNumber"),
                label_url=s3_key,
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
            logger.exception(f"failed to commit changes of buy label to db")
            raise DatabaseException(500, "failed to commit changes of buy label to db")

    async def _buy_usps_label(
        self, data: BuyLabelRequest, user: User, db: AsyncSession
    ) -> List[Label]:
        usps = get_usps_service()

        rates = await usps.get_rates(
            pickup_postal_code=data.shipper.postal_code,
            destination_postal_code=data.recipient.postal_code,
            packages=data.packages,
        )

        matching_rate = next(
            (rate for rate in rates if rate.get("mailClass") == data.service_type),
            None,
        )
        if not matching_rate:
            raise RateNotAvailableException(data.service_type)

        base_price = self._to_decimal(matching_rate.get("price"))
        if base_price is None:
            raise ExternalServiceException(
                "Unable to determine USPS rate for requested service type."
            )

        estimated_price = self._apply_multiplier_to_rates(base_price, user.multiplier)
        if user.balance < estimated_price:
            raise InsufficientBalanceException(user.balance, base_price)

        purchase_response = await usps.buy_label(
            shipper_address=data.shipper,
            recipient_address=data.recipient,
            serviceType=data.service_type,
            packages=data.packages,
            signature_option=data.signature_option,
            ship_date=data.ship_date,
        )

        label_payloads = self._normalize_usps_label_response(purchase_response)
        if not label_payloads:
            raise ExternalServiceException("USPS did not return label details.")

        labels: List[Label] = []
        for idx, payload in enumerate(label_payloads, start=1):
            tracking_number = (
                payload.get("trackingNumber")
                or payload.get("tracking_number")
                or payload.get("trackingId")
            )
            if not tracking_number:
                raise ExternalServiceException(
                    "USPS label response missing tracking number."
                )

            label_base_price = self._to_decimal(
                payload.get("price")
                or payload.get("amount")
                or payload.get("totalPrice")
                or base_price
            )
            if label_base_price is None:
                label_base_price = base_price

            cost_estimate = self._apply_multiplier_to_rates(
                label_base_price, user.multiplier
            )

            order_reference = str(data.order_number or tracking_number)
            label_url = self._extract_usps_label_url(payload)
            if label_url:
                s3_key = download_and_upload_label(
                    label_url, order_reference, idx, CarriersEnum.usps.value
                )
            else:
                label_bytes, extension = self._extract_usps_label_bytes(payload)
                if label_bytes is None:
                    raise ExternalServiceException(
                        "USPS label response missing printable document."
                    )
                s3_key = upload_label_to_s3(
                    label_bytes,
                    order_reference,
                    idx,
                    carrier=CarriersEnum.usps.value,
                    extension=extension,
                )

            label = Label(
                id=str(uuid4()),
                user_id=user.id,
                order_number=data.order_number,
                tracking_number=tracking_number,
                label_url=s3_key,
                status=LabelStatus.new,
                carrier=CarriersEnum.usps,
                service_type=data.service_type,
                cost_estimate=cost_estimate,
            )
            if label_base_price is not None:
                label.cost_actual = label_base_price
            labels.append(label)

        try:
            result = await db.execute(
                select(User).where(User.id == user.id).with_for_update()
            )
            user_locked = result.scalar_one()

            result = await db.execute(
                select(Order).where(Order.order_number == data.order_number)
            )
            order = result.scalars().first()
            if order:
                order.status = OrderStatus.shipped

            transactions: List[Transaction] = []
            for label in labels:
                user_locked.balance -= label.cost_estimate
                transaction = Transaction(
                    id=str(uuid4()),
                    user_id=user_locked.id,
                    amount=label.cost_estimate,
                    new_balance=user_locked.balance,
                    trans_type=TransactionType.usage,
                    note=(
                        f"Label purchase for tracking {label.tracking_number} - "
                        f"{label.service_type}"
                    ),
                )
                transactions.append(transaction)

            db.add_all(labels)
            db.add_all(transactions)
            await db.commit()
            return labels
        except Exception:
            await db.rollback()
            logger.exception("failed to commit USPS label purchase to db")
            raise DatabaseException(500, "failed to commit changes of buy label to db")

    async def _cancel_usps_label(
        self, data: CancelLabelRequest, user: User, db: AsyncSession
    ):
        usps = get_usps_service()
        await usps.cancel_label(tracking_number=data.tracking_number)

        try:
            result = await db.execute(
                select(Label)
                .where(Label.tracking_number == data.tracking_number)
                .with_for_update()
            )
            label = result.scalar_one_or_none()
            if not label:
                raise DatabaseException(404, "Label not found")

            if label.status == LabelStatus.cancelled:
                raise DatabaseException(400, "Label already cancelled")

            result = await db.execute(
                select(User).where(User.id == user.id).with_for_update()
            )
            user_locked = result.scalar_one()

            label.status = LabelStatus.cancelled

            refund_amount = label.cost_estimate

            user_locked.balance += refund_amount

            transaction = Transaction(
                id=str(uuid4()),
                user_id=user_locked.id,
                amount=refund_amount,
                new_balance=user_locked.balance,
                trans_type=TransactionType.refund,
                note=(
                    f"Refund label purchase for tracking {label.tracking_number} - "
                    f"{label.service_type}"
                ),
            )

            db.add(transaction)
            await db.commit()
        except DatabaseException:
            raise
        except Exception:
            await db.rollback()
            logger.exception("Failed to commit USPS label cancel to DB")
            raise DatabaseException(500, "Failed to commit label cancel to DB")

    def _normalize_usps_label_response(self, response: Any) -> List[dict]:
        if response is None:
            return []

        if isinstance(response, dict):
            for key in (
                "labels",
                "label",
                "labelDetails",
                "labelResponses",
                "labelList",
                "shippingLabels",
            ):
                value = response.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    return [value]

            for wrapper_key in ("data", "result", "response"):
                if wrapper_key in response:
                    nested = self._normalize_usps_label_response(
                        response[wrapper_key]
                    )
                    if nested:
                        return nested

            return [response]

        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]

        return []

    def _extract_usps_label_url(self, payload: dict) -> Optional[str]:
        possible_keys = [
            "labelUrl",
            "labelURL",
            "label_url",
            "url",
            "downloadUrl",
            "downloadURL",
            "href",
        ]

        for key in possible_keys:
            value = payload.get(key)
            if value:
                return value

        nested_sections = [
            "labelDownload",
            "labelDocument",
            "labelFile",
            "document",
        ]

        for nested_key in nested_sections:
            nested_value = payload.get(nested_key)
            if isinstance(nested_value, dict):
                for key in possible_keys:
                    inner = nested_value.get(key)
                    if inner:
                        return inner
            elif isinstance(nested_value, list):
                for item in nested_value:
                    if not isinstance(item, dict):
                        continue
                    for key in possible_keys:
                        inner = item.get(key)
                        if inner:
                            return inner

        links = payload.get("links")
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                if link.get("href"):
                    return link["href"]

        return None

    def _extract_usps_label_bytes(self, payload: dict) -> Tuple[Optional[bytes], str]:
        candidates = [
            payload.get("labelData"),
            payload.get("label"),
            payload.get("labelBytes"),
            payload.get("labelFile"),
            payload.get("labelDocument"),
            payload.get("document"),
        ]

        for candidate in candidates:
            if not candidate:
                continue

            if isinstance(candidate, list):
                for item in candidate:
                    decoded = self._decode_usps_label_candidate(item)
                    if decoded:
                        return decoded
                continue

            decoded = self._decode_usps_label_candidate(candidate)
            if decoded:
                return decoded

        return None, "pdf"

    def _decode_usps_label_candidate(
        self, candidate: Any
    ) -> Optional[Tuple[bytes, str]]:
        if not candidate:
            return None

        content_type: Optional[str] = None
        data = candidate

        if isinstance(candidate, dict):
            content_type = (
                candidate.get("contentType")
                or candidate.get("mimeType")
                or candidate.get("type")
                or candidate.get("format")
            )

            for key in ("data", "content", "value", "file", "bytes", "label"):
                if candidate.get(key) is not None:
                    data = candidate[key]
                    break

            if isinstance(data, dict):
                nested = self._decode_usps_label_candidate(data)
                if nested:
                    bytes_data, extension = nested
                    if content_type:
                        extension = self._extension_from_content_type(content_type)
                    return bytes_data, extension

        if isinstance(data, bytes):
            return data, self._extension_from_content_type(content_type)

        if isinstance(data, str):
            encoded = data
            if data.startswith("data:"):
                header, encoded = data.split(",", 1)
                if not content_type:
                    content_type = header.split(";", 1)[0].split(":", 1)[1]

            try:
                decoded_bytes = base64.b64decode(encoded)
            except (binascii.Error, ValueError):
                return None

            return decoded_bytes, self._extension_from_content_type(content_type)

        return None

    def _extension_from_content_type(self, content_type: Optional[str]) -> str:
        if not content_type:
            return "pdf"

        lowered = content_type.lower()
        if "png" in lowered:
            return "png"
        if "zpl" in lowered:
            return "zpl"
        if "jpeg" in lowered or "jpg" in lowered:
            return "jpg"
        if "gif" in lowered:
            return "gif"
        return "pdf"

    def _to_decimal(self, value: Any) -> Optional[Decimal]:
        if value is None:
            return None

        if isinstance(value, Decimal):
            return value

        if isinstance(value, Money):
            return value.to_decimal()

        if isinstance(value, dict):
            for key in ("amount", "value", "price"):
                if value.get(key) is not None:
                    return self._to_decimal(value[key])
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            logger.debug("Unable to convert value to Decimal: %s", value)
            return None

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
        logger.debug(f"_apply_multiplier_to_rates init_value={init_value}, new_value={new_value}")
        return new_value


    async def _get_usps_rates(self, data: ShipmentRatesRequest):
        usps = get_usps_service()
        rates_options = await usps.get_rates(
                pickup_postal_code=data.shipper.postal_code,
                destination_postal_code=data.recipient.postal_code, 
                packages=data.packages)
       
        sumarry_rates = [ShipmentRatesResponse(
                            service_provider="USPS",
                            service_type= rates.get("mailClass"), 
                            total_charge= rates.get("price"),
                            delivery_promise=rates.get("productDefinition")) for rates in rates_options] 
        return sumarry_rates
    
    async def get_labels_by_order(self, order_number: str, db: AsyncSession,  user: User):
        try:
            result = await db.execute(
                    select(Label).where(Label.order_number == order_number)
                )
            labels = result.scalars().all()
            if len(labels) == 0:
                raise HTTPException(404, "Label not found")
            links = [] 
            for label in labels:
                s3_key = label.label_url
                signed_url = generate_signed_url(s3_key)
                links.append(signed_url)
            return links
        except Exception as ex:
            logger.exception(f"Failed to retrieve labels for order_number {order_number}")
            raise DatabaseException(500, "Failed to commit label cancel to DB")

    async def get_labels_by_id(self, label_id: UUID, db: AsyncSession,  user: User):
        result = await db.execute(
                select(Label).where(Label.id == label_id)
            )
        label = result.scalar_one_or_none()
        if not label:
            raise HTTPException(status_code=404, detail=f"label {label_id} not found")
        s3_key = label.label_url
        try:
            signed_url = generate_signed_url(s3_key)
            return signed_url
        except Exception as ex:
            logger.exception(f"Failed to retrieve label {label_id}")
            raise DatabaseException(500, "Failed to retrieve label")
    
    async def upload_labels(self,
        label_files: List[UploadFile],
        user_id: str,
        db: AsyncSession):

        MAX_FILE_COUNT = 10
        MAX_FILE_SIZE_MB = 5
        MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
        ORDER_NUM_PLACEHOLDER = "0123456789"

        if len(label_files) > MAX_FILE_COUNT:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum of {MAX_FILE_COUNT} files allowed."
            )

        seen_filenames = set()
        labels=[]
        label_ids = []

        for file in label_files:
            if file.content_type != "application/pdf":
                raise HTTPException(status_code=400, detail=f"{file.filename} is not a PDF.")

            filename = file.filename.lower()
            if filename in seen_filenames:
                raise HTTPException(status_code=400, detail=f"Duplicate file: {file.filename}")
            seen_filenames.add(filename)

            file_data = await file.read()

            if len(file_data) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"{file.filename} exceeds the {MAX_FILE_SIZE_MB}MB size limit."
                )

            s3_key = upload_file_to_s3(
                file_data=file_data,
                filename=file.filename,
                content_type=file.content_type
            )

            label = Label(
                id=uuid4(),
                user_id=user_id,
                order_number=ORDER_NUM_PLACEHOLDER,
                tracking_number="n/a",
                label_url = s3_key,
                carrier = CarriersEnum.other,
                status = LabelStatus.new,
                service_type = "default",
                cost_estimate_cents=0,
                cost_actual_cents=0)
            labels.append(label)
            label_ids.append(label.id)
        try:
            if len(labels) > 0:
                db.add_all(labels)
                await db.commit()
            return {"label_ids": label_ids}
        except Exception as ex:
            logger.exception(f"Failed to upload labels")
            raise DatabaseException(500, "Failed to upload labels")
        



