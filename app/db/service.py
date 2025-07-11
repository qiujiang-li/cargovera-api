# Core pagination service

from typing import Optional
from sqlalchemy.orm import Session
from app.schemas.pagination import PaginatedResponse, SortOrder, PaginationLinks, PaginationInfo
from app.schemas.pagination import CursorData
from fastapi import HTTPException
import json
import base64
from datetime import datetime
from sqlalchemy import or_, and_, desc, asc, select, func
from typing import Dict, Any, List, TypeVar, Type
from pydantic import BaseModel

# Generic type for the output schema classes
T = TypeVar('T', bound=BaseModel)

# Utility functions
def encode_cursor(cursor_data: CursorData) -> str:
    """Encode cursor data to base64 string"""
    cursor_dict = {
        "id": cursor_data.id,
        "created_at": cursor_data.created_at.isoformat(),
        "sort_field": cursor_data.sort_field,
        "sort_value": cursor_data.sort_value
    }
    cursor_json = json.dumps(cursor_dict)
    return base64.b64encode(cursor_json.encode()).decode()

def decode_cursor(cursor: str) -> CursorData:
    """Decode base64 cursor to cursor data"""
    try:
        cursor_json = base64.b64decode(cursor.encode()).decode()
        cursor_dict = json.loads(cursor_json)
        return CursorData(
            id=cursor_dict["id"],
            created_at=datetime.fromisoformat(cursor_dict["created_at"]),
            sort_field=cursor_dict.get("sort_field"),
            sort_value=cursor_dict.get("sort_value")
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor format")


class PaginationService:
    def __init__(self, db: Session):
        self.db = db
    
    async def paginate(
        self,
        model_class,
        output_schema: Type[T],
        page: Optional[int] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: SortOrder = SortOrder.desc,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PaginatedResponse:
        """
        Generic pagination method that works with any SQLAlchemy model.
        
        Args:
            model_class: SQLAlchemy model class to paginate
            page: Page number for offset-based pagination
            cursor: Cursor for cursor-based pagination
            limit: Number of items per page
            sort_by: Field name to sort by
            sort_order: Sort order (asc/desc)
            filters: Dictionary of field:value filters
            search_fields: List of fields to search in
            search_query: Search term to apply across search_fields
        """
        
        # Build base query
        where_filters = []
        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(model_class, field) and value is not None:
                    column = getattr(model_class, field)
                    if isinstance(value, dict):
                        # Handle range filters like {"gte": 100, "lte": 500}
                        if "gte" in value:
                            where_filters.append(column >= value['gte'])
                        if "lte" in value:
                            where_filters.append(column <= value['lte'])
                        if "eq" in value:
                            where_filters.append(column == value['eq'])
                        if "like" in value:
                            where_filters.append(column.ilike(f"%{value['like']}%"))

                    else:
                        # Direct equality filter
                        where_filters.append(column == value)
        
        # Determine pagination strategy
        if cursor:
            return await self._cursor_paginate(where_filters, model_class, output_schema, cursor, limit, sort_by, sort_order)
        elif page:
            return await self._offset_paginate(where_filters, model_class, output_schema, page, limit, sort_by, sort_order)
        else:
            # Default to cursor-based for better performance
            return await self._offset_paginate(where_filters, model_class, output_schema, None, limit, sort_by, sort_order)

    async def _offset_paginate(
            self, 
            where_filters, 
            model_class,
            output_schema,
            page: int, 
            limit: int, 
            sort_by: str, 
            sort_order: SortOrder
        ) -> PaginatedResponse:
            
            # Apply sorting
            sort_column = getattr(model_class, sort_by, getattr(model_class, "created_at", getattr(model_class, "id")))
            if sort_order == SortOrder.desc:
                query = select(model_class).where(*where_filters).order_by(desc(sort_column))
            else:
                query = select(model_class).where(*where_filters).order_by(asc(sort_column))

            count_query = select(func.count()).select_from(select(model_class).where(*where_filters).subquery())
            total_result = await self.db.execute(count_query)
            total_items = total_result.scalar()
            total_pages = (total_items + limit - 1) // limit
            # Validate page number
            if page is None or page < 1:
                page = 1
            elif page > total_pages and total_pages > 0:
                raise HTTPException(status_code=404, detail="Page not found")

            # Apply offset and limit
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)

            result = await self.db.execute(query)
            items = result.scalars().all()
            # Build response (generic - works with any model)
            data = [output_schema.from_orm(item) for item in items]       
            # Create cursors for hybrid support
            next_cursor = None
            previous_cursor = None
            
            # if items:
            #     if page < total_pages:
            #         last_item = items[-1]
            #         next_cursor = encode_cursor(CursorData(
            #             id=last_item.id,
            #             created_at=getattr(last_item, 'created_at', datetime.utcnow()),
            #             sort_field=sort_by,
            #             sort_value=getattr(last_item, sort_by, None)
            #         ))
                
            #     if page > 1:
            #         first_item = items[0]
            #         previous_cursor = encode_cursor(CursorData(
            #             id=first_item.id,
            #             created_at=getattr(first_item, 'created_at', datetime.utcnow()),
            #             sort_field=sort_by,
            #             sort_value=getattr(first_item, sort_by, None)
            #         ))
            
            pagination = PaginationInfo(
                current_page=page,
                total_pages=total_pages,
                total_items=total_items,
                items_per_page=limit,
                has_next=page < total_pages,
                has_previous=page > 1,
                next_cursor=next_cursor,
                previous_cursor=previous_cursor
            )
            
            links = self._build_offset_links(page, total_pages, limit, sort_by, sort_order)
            
            return PaginatedResponse(data=data, pagination=pagination, links=links)

    def _cursor_paginate(
            self, 
            query, 
            model_class,    
            output_schema,
            cursor: Optional[str], 
            limit: int, 
            sort_by: str, 
            sort_order: SortOrder
        ) -> PaginatedResponse:
            
            # Apply sorting
            sort_column = getattr(model_class, sort_by, getattr(model_class, "created_at", getattr(model_class, "id")))
            
            if cursor:
                cursor_data = decode_cursor(cursor)
                
                # Apply cursor conditions based on sort order
                if sort_order == SortOrder.desc:
                    if sort_by == "created_at":
                        created_at_col = getattr(model_class, "created_at")
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                created_at_col < cursor_data.created_at,
                                and_(
                                    created_at_col == cursor_data.created_at,
                                    id_col < cursor_data.id
                                )
                            )
                        )
                    else:
                        # For other fields, use composite sorting
                        sort_value = cursor_data.sort_value
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                sort_column < sort_value,
                                and_(
                                    sort_column == sort_value,
                                    id_col < cursor_data.id
                                )
                            )
                        )
                    query = query.order_by(desc(sort_column), desc(getattr(model_class, "id")))
                else:
                    if sort_by == "created_at":
                        created_at_col = getattr(model_class, "created_at")
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                created_at_col > cursor_data.created_at,
                                and_(
                                    created_at_col == cursor_data.created_at,
                                    id_col > cursor_data.id
                                )
                            )
                        )
                    else:
                        sort_value = cursor_data.sort_value
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                sort_column > sort_value,
                                and_(
                                    sort_column == sort_value,
                                    id_col > cursor_data.id
                                )
                            )
                        )
                    query = query.order_by(asc(sort_column), asc(getattr(model_class, "id")))
            else:
                # First page
                if sort_order == SortOrder.desc:
                    query = query.order_by(desc(sort_column), desc(getattr(model_class, "id")))
                else:
                    query = query.order_by(asc(sort_column), asc(getattr(model_class, "id")))
            
            # Fetch one extra item to determine if there's a next page
            items = query.limit(limit + 1).all()
            
            has_next = len(items) > limit
            if has_next:
                items = items[:limit]
            
            # Build response (generic - works with any model)
            data = [item.__dict__ for item in items]
            # Remove SQLAlchemy internal attributes
            for item_dict in data:
                item_dict.pop('_sa_instance_state', None)
            
            # Create cursors
            next_cursor = None
            previous_cursor = None
            
            if items:
                if has_next:
                    last_item = items[-1]
                    next_cursor = encode_cursor(CursorData(
                        id=last_item.id,
                        created_at=getattr(last_item, 'created_at', datetime.utcnow()),
                        sort_field=sort_by,
                        sort_value=getattr(last_item, sort_by, None)
                    ))
                
                # For previous cursor, we'd need to implement reverse pagination
                # This is a simplified version
                if cursor:
                    previous_cursor = "prev_" + cursor  # Simplified for demo
            
            pagination = PaginationInfo(
                items_per_page=limit,
                has_next=has_next,
                has_previous=cursor is not None,
                next_cursor=next_cursor,
                previous_cursor=previous_cursor
            )
            
            links = self._build_cursor_links(cursor, next_cursor, limit, sort_by, sort_order)
            
            return PaginatedResponse(data=data, pagination=pagination, links=links)
    
    def _build_offset_links(self, page: int, total_pages: int, limit: int, sort_by: str, sort_order: SortOrder) -> PaginationLinks:
        base_url = "/api/v1/products"
        query_params = f"limit={limit}&sort_by={sort_by}&sort_order={sort_order.value}"
        
        return PaginationLinks(
            first=f"{base_url}?page=1&{query_params}" if total_pages > 0 else None,
            previous=f"{base_url}?page={page-1}&{query_params}" if page > 1 else None,
            next=f"{base_url}?page={page+1}&{query_params}" if page < total_pages else None,
            last=f"{base_url}?page={total_pages}&{query_params}" if total_pages > 0 else None
        )
        
    def _build_cursor_links(self, cursor: Optional[str], next_cursor: Optional[str], limit: int, sort_by: str, sort_order: SortOrder) -> PaginationLinks:
        base_url = "/api/v1/products"
        query_params = f"limit={limit}&sort_by={sort_by}&sort_order={sort_order}"
        
        return PaginationLinks(
            next=f"{base_url}?cursor={next_cursor}&{query_params}" if next_cursor else None,
            previous=f"{base_url}?cursor={cursor}&{query_params}" if cursor else None
        )