from sqlalchemy import func, or_, select, and_, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, BackgroundTasks,Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.fulfillment import FulfillmentRequest, FulfillmentItem, FulfillmentRequeestStatusEnum
from app.models.user import User
from app.models.label import Label, LabelStatus
from app.schemas.fulfillment import FulfillmentRequestCreate, FulfillmentRequestSchema
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.db.service import PaginationService
from app.schemas.inventory import AddInventoryRequest, InventorySchema, InventoryTransactionSchema
from app.models.inventory import Inventory, InventoryStatusEnum, InventoryTransaction, InventoryTransactionSourceEnum, InventoryTransactionTypeEnum
from sqlalchemy.exc import IntegrityError
from app.schemas.pagination import SortOrder
from app.core.exceptions import DatabaseConstraintException, DatabaseException
from app.services.email import EmailService
import asyncpg
from app.utils.mist import is_valid_zipcode
import uuid
import logging
import datetime

logger = logging.getLogger(__name__)

class FulfillmentService:
    def __init__(self):
        pass

    def send_fulfilment_email(self, data, request_id, inventories: dict, background_tasks: BackgroundTasks):
            email_service = EmailService()
            first_inv = next(iter(inventories.values()), None)
            if first_inv:
                owner_name = first_inv.owner.name
                owner_email = first_inv.owner.email
                holder_email = first_inv.holder.email
            products = [{
                "name": inventories.get(item.inventory_id, {}).product.name,
                "upc": inventories.get(item.inventory_id, {}).product.upc,
                "quantity": item.quantity
            } for item in data.items]

            context = {
                "owner_name": owner_name,
                "shipment_id": request_id,
                "products": products,
                "notes": "Please ship ASAP."
            }
            subject = f"CARGOVERA Shipment Notification: {request_id}"
            first_inv = next(iter(inventories.values()), None)
            if first_inv and first_inv.holder:
                holder = first_inv.holder
                email_service.schedule_shipment_email(holder.email, owner_email, subject, context, "shipment_email.html", background_tasks)
            else:
                logging.warning(f"no email notficiation sent for fulfillment request id {request_id}")

    async def create_fulfillment_request(self, data: FulfillmentRequestCreate, user_id: str, db: AsyncSession, background_tasks: BackgroundTasks):
        if not data.items:
            raise HTTPException(status_code=400, detail="No items provided.")
        # Fetch all inventories involved
        inventory_ids = [item.inventory_id for item in data.items]
        result = await db.execute(
            select(Inventory)
            .options(selectinload(Inventory.owner))
            .options(selectinload(Inventory.holder))
            .options(selectinload(Inventory.product))
            .where(Inventory.id.in_(inventory_ids))
        )
        inventories = result.scalars().all()
        inventories_dict = {inv.id: inv for inv in inventories}

        if len(inventories_dict) != len(inventory_ids):
            raise HTTPException(status_code=404, detail="Some inventories not found.")

        # Validate that all inventories belong to same holder
        holder_ids = {inv.holder_id for inv in inventories}
        if len(holder_ids) > 1:
            raise HTTPException(status_code=400, detail="All items must belong to the same holder.")

        holder_id = holder_ids.pop()

                # Validate that all inventories belong to same holder
        owner_ids = {inv.owner_id for inv in inventories}
        if len(owner_ids) > 1:
            raise HTTPException(status_code=400, detail="All items must belong to the same owner.")

        owner_id = owner_ids.pop()

        if owner_id != user_id:
            raise HTTPException(status_code=400, detail="All items must belong to the current user")

        #check if all inventory in active status
        if any(inv.status != InventoryStatusEnum.active for inv in inventories):
            raise HTTPException(status_code=400, detail="All inventories must be in active status.")

        # Check quantity availability and reserve
        for item in data.items:
            inventory = inventories_dict[item.inventory_id]
            if inventory.available_qty - inventory.reserved_qty < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough quantity for inventory {item.inventory_id}"
                )
            inventory.reserved_qty += item.quantity  # reserve now

        try:
            # Create fulfillment request and items
            fulfillment_request = FulfillmentRequest(
                id=uuid.uuid4(),
                owner_id=user_id,
                holder_id=holder_id,
            )
            db.add(fulfillment_request)

            for item in data.items:
                fulfillment_item = FulfillmentItem(
                    id=uuid.uuid4(),
                    request_id=fulfillment_request.id,
                    inventory_id=item.inventory_id,
                    quantity=item.quantity,
                    label_urls=item.label_urls
                )
                db.add(fulfillment_item)
            await db.commit()
            request_id = str(fulfillment_request.id)
            self.send_fulfilment_email(data, request_id, inventories_dict, background_tasks)
            return {"data":{"request_id": request_id}}
        except Exception as ex:
            await db.rollback()
            logger.exception(f"unexpected error adding new fulfillment request")
            raise DatabaseException(500, "Unexpected error while adding new fulfillment request")
    
    async def delete_fulfillment_request(self, request_id: uuid.UUID, user_id: str, db: AsyncSession):
        # Fetch the request
        result = await db.execute(
            select(FulfillmentRequest)
            .where(FulfillmentRequest.id == request_id)
            .options(selectinload(FulfillmentRequest.items))  # load FulfillmentItems
        )
        request = result.scalar_one_or_none()

        if not request:
            raise HTTPException(status_code=404, detail="Fulfillment request not found")

        # Only allow owner to delete their own requests
        if request.owner_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this request")

        # Prevent deletion of fulfilled or canceled requests
        if request.status != FulfillmentRequeestStatusEnum.pending:
            raise HTTPException(status_code=400, detail="Cannot delete a completed or canceled request")


        try:
            #Step 1: Update reserved quantities on each inventory
            for item in request.items:
                inventory_result = await db.execute(
                    select(Inventory)
                    .where(Inventory.id == item.inventory_id)
                    .with_for_update()  # 🔒 this locks the row until the transaction ends
                )
                inventory = inventory_result.scalar_one_or_none()
                if inventory:
                    if item.quantity >inventory.reserved_qty:
                        logging.warning(f"should not happen but qty from fulfillment request {item.quantity} larger than inventory recorded reserved_qty{inventory.reserved_qty}")
                    inventory.reserved_qty = max(inventory.reserved_qty - item.quantity, 0)
                    db.add(inventory)
            await db.delete(request)
            await db.commit()
        except Exception as ex:
            logger.exception(f"unexpected error deleting new fulfillment request {request_id}")
            raise DatabaseException(500, "Unexpected error while deleting a fulfillment request {request_id}")

    async def get_fulfillment_requests(self,
        as_owner: bool,
        status: FulfillmentRequeestStatusEnum,
        created_from: datetime, 
        created_to: datetime, 
        page: int,
        limit: int,
        db: AsyncSession,
        current_user: User):
            """
            Paginated list of fulfillment requests for the current user with optional filters.
            """
            offset = (page - 1) * limit

            stmt = select(FulfillmentRequest).options(
                selectinload(FulfillmentRequest.items)
                .selectinload(FulfillmentItem.inventory)
                .options(
                selectinload(Inventory.product),
                selectinload(Inventory.owner),
                selectinload(Inventory.holder))
            )

            filters = []
            # Filter by owner or holder
            if as_owner:
                filters.append(FulfillmentRequest.owner_id == current_user.id)
            else:
                filters.append(FulfillmentRequest.holder_id == current_user.id)

            # Filter by status
            if status:
                filters.append(FulfillmentRequest.status == status)
            else:
                filters.append(FulfillmentRequest.status == FulfillmentRequeestStatusEnum.pending)

            # Filter by created_at range
            if created_from:
                filters.append(FulfillmentRequest.created_at >= created_from)
            if created_to:
                filters.append(FulfillmentRequest.created_at <= created_to)

            stmt = stmt.where(and_(*filters))

            # Apply sorting
            sort_column = getattr(FulfillmentRequest, "created_at", None)
            stmt = stmt.order_by(desc(sort_column))

            # Count total
            total_stmt = select(func.count()).select_from(stmt.subquery())
            total_result = await db.execute(total_stmt)
            total_items = total_result.scalar_one()
            total_pages = (total_items + limit - 1) // limit

            # Fetch paginated records
            result = await db.execute(stmt.offset(offset).limit(limit))
            requests = result.scalars().all()

            pagination = PaginationInfo(
                current_page=page,
                total_pages=total_pages,
                total_items=total_items,
                items_per_page=limit,
                has_next=page < total_pages,
                has_previous=page > 1,
            )

            return PaginatedResponse(
                data=[FulfillmentRequestSchema.from_orm(req) for req in requests],
                pagination=pagination,
                links=None,
            )

    async def fulfill_request(self, request_id: uuid.UUID, user_id: str, db: AsyncSession):
        # Step 1: Load FulfillmentRequest with items (locked for update)
        result = await db.execute(
            select(FulfillmentRequest)
            .options(selectinload(FulfillmentRequest.items))
            .where(FulfillmentRequest.id == request_id)
            .with_for_update()
        )
        request_obj = result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(status_code=404, detail="Fulfillment request not found")

        if request_obj.status != FulfillmentRequeestStatusEnum.pending:
            raise HTTPException(status_code=400, detail="Request already fulfilled")

        if request_obj.holder_id != user_id:
            raise HTTPException(status_code=403, detail="You are not authorized to fulfill this request")

        # Step 2: Loop through items and update inventories
        for item in request_obj.items:
            inv_result = await db.execute(
                select(Inventory)
                .where(Inventory.id == item.inventory_id)
                .with_for_update()
            )
            inventory = inv_result.scalar_one_or_none()
            if not inventory:
                raise HTTPException(status_code=404, detail=f"Inventory {item.inventory_id} not found")

            if inventory.reserved_qty < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Reserved quantity mismatch for inventory {inventory.id}"
                )
            if inventory.available_qty < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough inventory for {inventory.id}"
                )

            inventory.available_qty -= item.quantity
            inventory.reserved_qty -= item.quantity
            if inventory.available_qty == 0:
                inventory.status = InventoryStatusEnum.inactive

            db.add(InventoryTransaction(
                inventory_id=inventory.id,
                product_id=inventory.product_id,
                created_by=inventory.owner_id,
                transaction_type=InventoryTransactionTypeEnum.debit,
                quantity=item.quantity,
                source=InventoryTransactionSourceEnum.outbound,
                source_ref_id=str(request_id),
                note="Fulfilled request"
            ))

            # Step 3: Update related Label entities' status to 'shipped'
            for label_id in item.label_urls:  # Assuming label_urls is list of UUIDs or strings
                label_result = await db.execute(
                    select(Label)
                    .where(Label.id == label_id)
                    .with_for_update()
                )
                label = label_result.scalar_one_or_none()
                if label:
                    label.status = LabelStatus.shipped
                else:
                    raise HTTPException(status_code=404, detail=f"Label {label_id} not found")

        # Step 4: Mark FulfillmentRequest as fulfilled
        request_obj.status = FulfillmentRequeestStatusEnum.fulfilled

        await db.commit()

        return {
            "data": {
                "request_id": str(request_id),
                "status": request_obj.status.value,
            }
        }

